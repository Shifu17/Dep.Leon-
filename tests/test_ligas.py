import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from dep_leon import rol
from dep_leon.ui import pagina_ligas as ui_ligas
from dep_leon.ui.chips import separar_dias


@pytest.mark.parametrize(
    "texto, esperado",
    [("2026-2027", "2026-2027"), ("2026-27", "2026-2027"), (" 2026 / 2027 ", "2026-2027"),
     ("2026 – 2027", "2026-2027"), ("2099-00", "2099-2100")],
)
def test_temporada_se_escribe_igual(texto, esperado):
    assert rol.nombre_torneo(texto) == esperado


@pytest.mark.parametrize("texto", ["2026", "2026-2028", "Copa de Verano", "1990-1991", ""])
def test_temporada_invalida(texto):
    with pytest.raises(ValueError):
        rol.nombre_torneo(texto)


@pytest.mark.parametrize(
    "desde, hasta, esperado",
    [(2012, 2012, "2012"), (2009, 2010, "2009–2010"), (None, None, "Sin límite")],
)
def test_rango_de_anios(desde, hasta, esperado):
    assert ui_ligas._rango({"anio_min": desde, "anio_max": hasta}) == esperado


def test_dias_en_chips():
    assert separar_dias("Viernes y sábado") == ["Viernes", "Sábado"]
    assert separar_dias("Lunes, miércoles / viernes") == ["Lunes", "Miércoles", "Viernes"]
    assert separar_dias("") == []


@pytest.fixture
def pagina(app, conn):
    resultado = ui_ligas.PaginaLigas(conn)
    yield resultado
    resultado.close()
    resultado.deleteLater()
    app.processEvents()


def _elegir(pagina, liga):
    tabla = pagina.tabla_ligas
    tabla.selectRow(next(r for r in range(tabla.rowCount()) if tabla.item(r, 0).text() == liga))


def test_ligas_cuentan_categorias_y_equipos(pagina, conn, torneo_id, infantil_id):
    categoria = conn.execute("SELECT id FROM categorias WHERE liga_id = ? LIMIT 1", (infantil_id,)).fetchone()[0]
    with conn:
        for nombre in ("A", "B"):
            conn.execute("INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
                         (torneo_id, categoria, nombre))
    pagina.refrescar()
    _elegir(pagina, "Infantil")
    fila = pagina.tabla_ligas.currentRow()
    assert [pagina.tabla_ligas.item(fila, c).text() for c in (3, 4)] == ["6", "2"]
    assert pagina.titulo_categorias.text() == "Categorías de Infantil"
    assert pagina.titulo_torneos.text() == "Torneos de Infantil"


def test_lista_vacia_ofrece_crear(pagina, conn, monkeypatch):
    _elegir(pagina, "Femenil")
    assert pagina.tabla_torneos.rowCount() == 0
    assert not pagina.tabla_torneos._vacio_boton.isHidden()
    assert pagina.tabla_torneos._vacio.text() == "Esta liga no tiene torneos."
    llamado = []
    monkeypatch.setattr(pagina, "nuevo_torneo", lambda: llamado.append(True))
    _elegir(pagina, "Infantil")
    assert pagina.tabla_categorias._vacio_boton.isHidden()  # Infantil sí tiene categorías


def test_dialogo_torneo_valida_y_unifica(app):
    dialogo = ui_ligas.DialogoTorneo(None)
    dialogo.nombre.setText("2026")
    dialogo._aceptar()
    assert dialogo.result() == 0 and "2026-2027" in dialogo.error_nombre.text()
    dialogo.nombre.setText("2026-27")
    dialogo._aceptar()
    assert dialogo.result() == 1 and dialogo.temporada == "2026-2027"


def test_agregar_torneo_guarda_la_temporada_unificada(pagina, conn, monkeypatch):
    def llenar(dialogo):
        dialogo.nombre.setText("2027 / 28")
        dialogo._aceptar()
        return True

    monkeypatch.setattr(ui_ligas.DialogoTorneo, "exec", llenar)
    _elegir(pagina, "Femenil")
    pagina.nuevo_torneo()
    assert conn.execute("SELECT nombre FROM torneos").fetchone()[0] == "2027-2028"
    assert pagina.tabla_torneos.item(0, 0).text() == "2027-2028"


def test_clic_derecho_tiene_editar_y_eliminar(pagina):
    from PySide6.QtCore import Qt

    assert pagina.tabla_categorias.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_estado_del_torneo(conn, torneo_id, infantil_id):
    from dep_leon import resultados
    from test_resultados import crear_equipo, crear_partido

    categoria = conn.execute("SELECT id FROM categorias WHERE liga_id = ? LIMIT 1", (infantil_id,)).fetchone()[0]
    assert rol.estado_torneo(conn, torneo_id) == rol.TORNEO_PROXIMO  # sin partidos
    a, _ = crear_equipo(conn, torneo_id, categoria, "A")
    b, _ = crear_equipo(conn, torneo_id, categoria, "B")
    uno = crear_partido(conn, torneo_id, categoria, a, b)
    dos = crear_partido(conn, torneo_id, categoria, b, a, hora="10:00")
    assert rol.estado_torneo(conn, torneo_id) == rol.TORNEO_PROXIMO
    resultados.guardar_resultado(conn, uno, 1, 0)
    assert rol.estado_torneo(conn, torneo_id) == rol.TORNEO_ACTIVO
    resultados.guardar_resultado(conn, dos, 2, 2)
    assert rol.estado_torneo(conn, torneo_id) == rol.TORNEO_FINALIZADO


def test_torneos_de_un_anio_pasan_a_temporada(tmp_path):
    from dep_leon import db

    ruta = tmp_path / "vieja.db"
    conn = db.conectar(ruta)
    ligas = [f["id"] for f in conn.execute("SELECT id FROM ligas ORDER BY id")]
    with conn:
        conn.execute("INSERT INTO torneos (liga_id, nombre) VALUES (?, '2026')", (ligas[0],))
        conn.execute("INSERT INTO torneos (liga_id, nombre) VALUES (?, 'Copa de Verano')", (ligas[0],))
        # En esta liga ya existe la temporada completa: no se juntan.
        conn.execute("INSERT INTO torneos (liga_id, nombre) VALUES (?, '2026')", (ligas[1],))
        conn.execute("INSERT INTO torneos (liga_id, nombre) VALUES (?, '2026-2027')", (ligas[1],))
    conn.close()
    conn = db.conectar(ruta)
    nombres = sorted((f["liga_id"], f["nombre"]) for f in conn.execute("SELECT liga_id, nombre FROM torneos"))
    assert nombres == sorted([
        (ligas[0], "2026-2027"), (ligas[0], "Copa de Verano"), (ligas[1], "2026"), (ligas[1], "2026-2027"),
    ])
    conn.close()
