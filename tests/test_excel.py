from datetime import datetime

import pytest
from openpyxl import load_workbook
from PIL import Image

from dep_leon import excel


@pytest.fixture
def plantilla(conn, infantil_id, tmp_path):
    ruta = tmp_path / "plantilla.xlsx"
    excel.crear_plantilla(conn, infantil_id, ruta)
    return ruta


def capturar(ruta, renglones):
    libro = load_workbook(ruta)
    hoja = libro[excel.HOJA]
    for r, valores in enumerate(renglones, start=2):
        for c, valor in enumerate(valores, start=1):
            hoja.cell(row=r, column=c).value = valor
    libro.save(ruta)


FECHA = datetime(2015, 3, 15)


def test_plantilla_trae_instrucciones_y_listas(plantilla):
    libro = load_workbook(plantilla)
    assert libro.sheetnames == ["Instrucciones", "Jugadores", "Listas"]
    assert libro["Listas"].sheet_state == "hidden"
    assert [c.value for c in libro["Jugadores"][1]] == list(excel.COLUMNAS.values())
    formulas = {v.formula1 for v in libro["Jugadores"].data_validations.dataValidation}
    assert formulas == {"=Listas!$A$1:$A$6", "=Listas!$B$1:$B$4"}
    textos = " ".join(str(c.value) for f in libro["Instrucciones"].iter_rows() for c in f if c.value)
    assert "2009-2010" in textos and "Importar Excel" in textos


def test_importa_jugadores_con_foto_y_crea_equipo(conn, plantilla, torneo_id, tmp_path):
    Image.new("RGB", (900, 900), "red").save(tmp_path / "juan.png")
    capturar(plantilla, [
        ["2015-2016", "Pegasos", "Juan Pérez", FECHA, 10, "Delantero", "juan"],
        ["2015-2016", "Pegasos", "Luis Díaz", "16/04/2016", "7", "portero", None],
    ])
    fotos = tmp_path / "almacen"
    fotos.mkdir()

    filas = excel.analizar(conn, plantilla, torneo_id)
    assert [f.errores for f in filas] == [[], []]
    assert excel.importar(conn, filas, torneo_id, fotos) == (2, 0, 1)

    juan, luis = conn.execute("SELECT * FROM jugadores ORDER BY numero DESC").fetchall()
    assert (juan["nombre"], juan["fecha_nacimiento"], juan["posicion"]) == (
        "Juan Pérez", "2015-03-15", "Delantero",
    )
    with Image.open(fotos / juan["foto"]) as guardada:
        assert max(guardada.size) == 600
    assert (luis["numero"], luis["posicion"], luis["foto"]) == (7, "Portero", "")


def test_reimportar_actualiza_sin_duplicar(conn, plantilla, torneo_id, tmp_path):
    capturar(plantilla, [["2015-2016", "Pegasos", "Juan Pérez", FECHA, 10, None, None]])
    excel.importar(conn, excel.analizar(conn, plantilla, torneo_id), torneo_id, tmp_path)

    # Mismo jugador y equipo, con otra escritura y otro número.
    capturar(plantilla, [["2015-2016", "PEGASOS", "juan perez", FECHA, 11, "Medio", None]])
    filas = excel.analizar(conn, plantilla, torneo_id)
    assert excel.importar(conn, filas, torneo_id, tmp_path) == (0, 1, 0)

    jugador = conn.execute("SELECT * FROM jugadores").fetchone()
    assert (jugador["numero"], jugador["posicion"]) == (11, "Medio")
    assert conn.execute("SELECT COUNT(*) FROM equipos").fetchone()[0] == 1


@pytest.mark.parametrize(
    "renglon, mensaje",
    [
        (["2015-2016", "Pegasos", "Ana", datetime(2012, 1, 1), 1, None, None], "admite desde 2015"),
        (["2015-2016", "Pegasos", "Ana", datetime(2018, 1, 1), 1, None, None], "admite hasta 2016"),
        (["2015-2016", "Pegasos", "Ana", "ayer", 1, None, None], "Fecha de nacimiento"),
        (["2015-2016", "Pegasos", "Ana", FECHA, 100, None, None], "Número de playera"),
        (["2015-2016", "Pegasos", "Ana", FECHA, 1.5, None, None], "Número de playera"),
        (["Libre", "Pegasos", "Ana", FECHA, 1, None, None], "Categoría no válida"),
        (["2015-2016", None, "Ana", FECHA, 1, None, None], "Falta el equipo"),
        (["2015-2016", "Pegasos", None, FECHA, 1, None, None], "Falta el nombre"),
        (["2015-2016", "Pegasos", "Ana", FECHA, 1, "Arquero", None], "Posición no válida"),
    ],
)
def test_renglon_invalido_se_reporta(conn, plantilla, torneo_id, renglon, mensaje):
    capturar(plantilla, [renglon])
    fila = excel.analizar(conn, plantilla, torneo_id)[0]
    assert not fila.valida
    assert mensaje in " ".join(fila.errores)


def test_numero_repetido_en_archivo_y_en_sistema(conn, plantilla, torneo_id, tmp_path):
    capturar(plantilla, [
        ["2015-2016", "Pegasos", "Ana", FECHA, 5, None, None],
        ["2015-2016", "Pegasos", "Eva", FECHA, 5, None, None],
    ])
    filas = excel.analizar(conn, plantilla, torneo_id)
    assert filas[0].valida and "renglón 2" in filas[1].errores[0]
    excel.importar(conn, filas, torneo_id, tmp_path)

    capturar(plantilla, [
        ["2015-2016", "Pegasos", "Sol", FECHA, 5, None, None],
        [None, None, None, None, None, None, None],
    ])
    filas = excel.analizar(conn, plantilla, torneo_id)
    assert len(filas) == 1
    assert "otro jugador" in filas[0].errores[0]


def test_mismo_numero_en_otro_equipo_es_valido(conn, plantilla, torneo_id):
    capturar(plantilla, [
        ["2015-2016", "Pegasos", "Ana", FECHA, 5, None, None],
        ["2015-2016", "Buitres", "Eva", FECHA, 5, None, None],
    ])
    assert all(f.valida for f in excel.analizar(conn, plantilla, torneo_id))


def test_solo_importa_los_renglones_validos(conn, plantilla, torneo_id, tmp_path):
    capturar(plantilla, [
        ["2015-2016", "Pegasos", "Ana", FECHA, 5, None, None],
        ["2015-2016", "Pegasos", "Eva", "mal", 6, None, None],
    ])
    assert excel.importar(conn, excel.analizar(conn, plantilla, torneo_id), torneo_id, tmp_path) == (1, 0, 1)


def test_foto_faltante_avisa_sin_bloquear(conn, plantilla, torneo_id):
    capturar(plantilla, [["2015-2016", "Pegasos", "Ana", FECHA, 5, None, "no-existe.jpg"]])
    fila = excel.analizar(conn, plantilla, torneo_id)[0]
    assert fila.valida and "no-existe.jpg" in fila.avisos[0]


def test_foto_no_sale_de_la_carpeta_del_excel(conn, plantilla, torneo_id, tmp_path):
    fuera = tmp_path.parent / "secreto.jpg"
    Image.new("RGB", (5, 5)).save(fuera)
    try:
        capturar(plantilla, [["2015-2016", "Pegasos", "Ana", FECHA, 5, None, r"..\secreto.jpg"]])
        assert excel.analizar(conn, plantilla, torneo_id)[0].foto is None
    finally:
        fuera.unlink()


def test_archivo_ajeno_da_mensaje_claro(conn, torneo_id, tmp_path):
    ajeno = tmp_path / "ajeno.xlsx"
    libro = load_workbook(_vacio(tmp_path))
    libro.save(ajeno)
    with pytest.raises(ValueError, match="hoja"):
        excel.analizar(conn, ajeno, torneo_id)

    texto = tmp_path / "texto.xlsx"
    texto.write_text("hola")
    with pytest.raises(ValueError, match="abrir"):
        excel.analizar(conn, texto, torneo_id)


def _vacio(carpeta):
    from openpyxl import Workbook

    ruta = carpeta / "vacio.xlsx"
    Workbook().save(ruta)
    return ruta
