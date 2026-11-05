import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import re
from datetime import date

import pytest
from PySide6.QtGui import QColor, QGuiApplication, QImage

from dep_leon import cobros, liguilla, lienzo, reportes, resultados, rol, updater
from dep_leon.ui import pagina_reportes as ui_reportes
from dep_leon.ui.ventana import Ventana

SABADO = date(2026, 11, 7)


@pytest.fixture(autouse=True)
def _aplicacion(app):
    return app


@pytest.fixture
def categoria(conn, infantil_id):
    return conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2015-2016'", (infantil_id,)
    ).fetchone()["id"]


def crear_equipo(conn, torneo_id, categoria, nombre):
    with conn:
        return conn.execute(
            "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
            (torneo_id, categoria, nombre),
        ).lastrowid


def crear_partido(conn, torneo_id, categoria, local, visitante, hora="09:00", jornada=1, cancha="1", fecha=SABADO):
    with conn:
        return conn.execute(
            "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, fecha, "
            "hora, minutos, cancha, estado) VALUES (?, ?, ?, ?, ?, ?, ?, 50, ?, ?)",
            (torneo_id, categoria, jornada, local, visitante, fecha.isoformat(), hora, cancha, rol.PROGRAMADO),
        ).lastrowid


@pytest.fixture
def datos(conn, torneo_id, categoria):
    a = crear_equipo(conn, torneo_id, categoria, "Pegasos")
    b = crear_equipo(conn, torneo_id, categoria, "Buitres")
    c = crear_equipo(conn, torneo_id, categoria, "Halcones")
    with conn:
        goleador = conn.execute(
            "INSERT INTO jugadores (equipo_id, nombre, fecha_nacimiento, numero) "
            "VALUES (?, 'Ana López', '2015-01-01', 9)",
            (a,),
        ).lastrowid
    uno = crear_partido(conn, torneo_id, categoria, a, b, "09:50", 1, "2")
    crear_partido(conn, torneo_id, categoria, b, c, "09:00", 2, "1", date(2026, 11, 14))
    crear_partido(conn, torneo_id, categoria, a, c, "09:00", 1, "1")
    resultados.guardar_resultado(conn, uno, 2, 1, {goleador: 2})
    return a, b, c


def paginas_pdf(ruta) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", open(ruta, "rb").read()))


def hay_tinta(imagen: QImage) -> bool:
    return any(
        imagen.pixelColor(x, y) != QColor("#FFFFFF")
        for x in range(0, imagen.width(), 37)
        for y in range(0, imagen.height(), 37)
    )


def test_rol_por_dia_con_columnas_de_la_hoja(conn, torneo_id, datos):
    hoja = reportes.hoja_rol(conn, torneo_id)
    assert [s.titulo for s in hoja.secciones] == [
        "Sábado 7 de noviembre del 2026", "Sábado 14 de noviembre del 2026",
    ]
    primera = hoja.secciones[0]
    assert [c.titulo for c in primera.columnas] == ["Hora", "Equipo", "Equipo", "Categoría", "Cancha"]
    # Como la hoja: primero toda la cancha 1 y luego la 2.
    assert [f[4] for f in primera.filas] == ["1", "2"]
    assert primera.filas[0][:3] == ["09:00", "Pegasos", "Halcones"]
    assert hoja.subtitulo == "Torneo Copa de Verano"


def test_rol_de_una_fecha_y_descansos(conn, torneo_id, datos):
    hoja = reportes.hoja_rol(conn, torneo_id, fecha=date(2026, 11, 14).isoformat())
    assert len(hoja.secciones) == 1
    assert "Descansan: Pegasos (2015-2016)" == hoja.secciones[0].nota


def test_rol_omite_pospuestos_y_muestra_ronda_de_liguilla(conn, torneo_id, categoria):
    a = crear_equipo(conn, torneo_id, categoria, "A")
    b = crear_equipo(conn, torneo_id, categoria, "B")
    pospuesto = crear_partido(conn, torneo_id, categoria, a, b)
    rol.posponer(conn, pospuesto)
    assert reportes.hoja_rol(conn, torneo_id).vacia

    g = liguilla.crear(conn, torneo_id, categoria, 1, 2, liguilla.PENALES)
    final = liguilla.vista(conn, g)[0]
    with conn:
        conn.execute(
            "UPDATE partidos SET fecha = ?, hora = '10:00', cancha = '1', estado = ? WHERE id = ?",
            (SABADO.isoformat(), rol.PROGRAMADO, final.partido_id),
        )
    assert reportes.hoja_rol(conn, torneo_id).secciones[0].filas[0][3] == "2015-2016 · Final"


def test_tabla_por_categoria(conn, torneo_id, categoria, datos, infantil_id):
    otra = conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2017-2018'", (infantil_id,)
    ).fetchone()["id"]
    crear_equipo(conn, torneo_id, otra, "Otro")
    hoja = reportes.hoja_tabla(conn, torneo_id)
    assert [s.titulo for s in hoja.secciones] == ["Categoría 2015-2016", "Categoría 2017-2018"]
    assert hoja.secciones[0].filas[0] == ["1", "Pegasos", "1", "1", "0", "0", "2", "1", "+1", "3"]
    solo = reportes.hoja_tabla(conn, torneo_id, otra)
    assert len(solo.secciones) == 1 and solo.secciones[0].filas[0][1] == "Otro"


def test_goleadores_y_porteria(conn, torneo_id, datos):
    hoja = reportes.hoja_goleadores(conn, torneo_id)
    assert hoja.secciones[0].filas == [["1", "Ana López", "Pegasos", "2"]]
    assert hoja.secciones[1].titulo == "Portería menos goleada: 2015-2016"
    assert hoja.secciones[1].filas[0] == ["1", "Pegasos", "1", "1", "1.00"]


def test_goleadores_sin_resultados_esta_vacio(conn, torneo_id, categoria):
    crear_equipo(conn, torneo_id, categoria, "A")
    assert reportes.hoja_goleadores(conn, torneo_id).vacia


def test_adeudos_con_total(conn, torneo_id, categoria, datos):
    a, *_ = datos
    assert reportes.hoja_adeudos(conn, torneo_id).vacia
    cobros.guardar_tarifas(conn, torneo_id, {categoria: (10000, 50000)})
    cobros.registrar_pago(conn, a, 20000, SABADO)
    hoja = reportes.hoja_adeudos(conn, torneo_id)
    filas = {f[0]: f for f in hoja.secciones[0].filas}
    assert filas["Pegasos"][1:] == ["$600.00", "$200.00", "$400.00"]
    assert hoja.secciones[-1].titulo == "Total"
    assert hoja.secciones[-1].filas[0] == ["$1,700.00", "$200.00", "$1,500.00"]


def test_llave(conn, torneo_id, categoria):
    for n in ("A", "B", "C", "D"):
        crear_equipo(conn, torneo_id, categoria, n)
    assert reportes.hoja_llave(conn, torneo_id, categoria).vacia
    liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.TABLA)
    hoja = reportes.hoja_llave(conn, torneo_id, categoria)
    assert [nombre for nombre, _ in hoja.rondas] == ["Semifinal", "Final"]
    assert len(hoja.rondas[0][1]) == 2 and hoja.campeon == ""
    assert hoja.titulo == "Liguilla: 2015-2016"


@pytest.mark.parametrize(
    "crear",
    [
        lambda c, t, k: reportes.hoja_rol(c, t),
        lambda c, t, k: reportes.hoja_tabla(c, t),
        lambda c, t, k: reportes.hoja_goleadores(c, t),
    ],
)
def test_dibuja_pdf_e_imagen(conn, torneo_id, categoria, datos, tmp_path, crear):
    hoja = crear(conn, torneo_id, categoria)
    pdf, png = tmp_path / "r.pdf", tmp_path / "r.png"
    lienzo.guardar_pdf(hoja, pdf)
    assert pdf.read_bytes().startswith(b"%PDF") and paginas_pdf(pdf) == 1
    lienzo.guardar_imagen(hoja, png)
    imagen = QImage(str(png))
    assert imagen.width() == int((lienzo.ANCHO + 2 * lienzo.MARGEN_IMAGEN) * lienzo.ESCALA_IMAGEN)
    assert hay_tinta(imagen)


def test_tabla_larga_continua_en_otra_hoja_y_la_imagen_crece(tmp_path):
    columnas = [reportes.Columna("A", 1), reportes.Columna("B", 1)]
    filas = [[str(i), "x"] for i in range(90)]
    hoja = reportes.Hoja("Larga", "Torneo", [reportes.Seccion("S", columnas, filas)])
    pdf = tmp_path / "r.pdf"
    lienzo.guardar_pdf(hoja, pdf)
    assert paginas_pdf(pdf) >= 3
    corta = reportes.Hoja("Corta", "Torneo", [reportes.Seccion("S", columnas, filas[:3])])
    assert lienzo.a_imagen(hoja).height() > lienzo.a_imagen(corta).height()
    # Todo cabe: la última fila no queda fuera de la imagen.
    alto = lienzo.altura_hoja(hoja) * lienzo.ESCALA_IMAGEN
    assert lienzo.a_imagen(hoja).height() >= alto


@pytest.mark.parametrize("total", [2, 3, 4, 8, 16, 32])
def test_llave_de_cualquier_tamano_cabe_en_una_hoja(conn, torneo_id, categoria, tmp_path, total):
    for i in range(total):
        crear_equipo(conn, torneo_id, categoria, f"Equipo con nombre largo {i}")
    liguilla.crear(conn, torneo_id, categoria, 1, total, liguilla.PENALES)
    hoja = reportes.hoja_llave(conn, torneo_id, categoria)
    pdf, png = tmp_path / "l.pdf", tmp_path / "l.png"
    lienzo.guardar_pdf(hoja, pdf)
    assert paginas_pdf(pdf) == 1
    lienzo.guardar_imagen(hoja, png)
    assert hay_tinta(QImage(str(png)))


def test_pdf_en_ruta_imposible_avisa(tmp_path):
    hoja = reportes.Hoja("x", "y", [])
    with pytest.raises(OSError):
        lienzo.guardar_pdf(hoja, tmp_path / "no" / "existe" / "r.pdf")
    with pytest.raises(OSError):
        lienzo.guardar_imagen(hoja, tmp_path / "no" / "existe" / "r.png")


@pytest.mark.parametrize(
    "texto, esperado", [('Rol: a/b?', "Rol ab"), ("  Normal 2026-11-07 ", "Normal 2026-11-07")]
)
def test_nombre_archivo(texto, esperado):
    assert reportes.nombre_archivo(texto) == esperado


# --- Pantalla ---


@pytest.fixture
def ventana(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    resultado = Ventana(conn)
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


def elegir(pagina, tipo):
    pagina.reporte.setCurrentText(tipo)


def test_pagina_vista_previa_y_botones_segun_reporte(ventana, conn, torneo_id, datos):
    pagina = ventana.reportes
    pagina.filtros.refrescar()
    assert pagina.reporte.currentText() == ui_reportes.ROL
    assert pagina.hoja is not None and not pagina.vista.pixmap().isNull()
    assert pagina.boton_imagen.isEnabled() and pagina.boton_copiar.isEnabled()
    assert pagina.fecha.count() == 3

    pagina.fecha.setCurrentIndex(1)
    assert len(pagina.hoja.secciones) == 1

    elegir(pagina, ui_reportes.GOLEADORES)
    assert pagina.boton_pdf.isEnabled() and not pagina.boton_imagen.isEnabled()
    elegir(pagina, ui_reportes.TABLA)
    assert pagina.boton_imagen.isEnabled()


def test_adeudos_solo_en_pdf(ventana, conn, torneo_id, categoria, datos):
    cobros.guardar_tarifas(conn, torneo_id, {categoria: (10000, 0)})
    pagina = ventana.reportes
    pagina.filtros.refrescar()
    elegir(pagina, ui_reportes.ADEUDOS)
    assert pagina.boton_pdf.isEnabled()
    assert not pagina.boton_imagen.isEnabled() and not pagina.boton_copiar.isEnabled()


def test_llave_pide_categoria_y_avisa_si_no_hay(ventana, conn, torneo_id, categoria, datos):
    pagina = ventana.reportes
    pagina.filtros.refrescar()
    elegir(pagina, ui_reportes.LLAVE)
    assert pagina.hoja is None and "categoría" in pagina.aviso.text()
    assert not pagina.boton_pdf.isEnabled()
    pagina.filtros.categoria.setCurrentText("2015-2016")
    assert pagina.hoja is None and "Todavía no hay datos" in pagina.aviso.text()
    liguilla.crear(conn, torneo_id, categoria, 1, 2, liguilla.TABLA)
    pagina.actualizar_vista()
    assert pagina.hoja is not None and pagina.boton_imagen.isEnabled()


def test_guardar_y_copiar(ventana, conn, torneo_id, datos, tmp_path, monkeypatch):
    pagina = ventana.reportes
    pagina.filtros.refrescar()
    abiertos = []
    monkeypatch.setattr(ui_reportes.os, "startfile", abiertos.append, raising=False)

    destino = tmp_path / "rol.pdf"
    monkeypatch.setattr(ui_reportes.QFileDialog, "getSaveFileName", lambda *a: (str(destino), ""))
    pagina.guardar_pdf()
    assert destino.read_bytes().startswith(b"%PDF") and abiertos == [str(destino)]

    destino_png = tmp_path / "rol.png"
    monkeypatch.setattr(ui_reportes.QFileDialog, "getSaveFileName", lambda *a: (str(destino_png), ""))
    pagina.guardar_imagen()
    assert not QImage(str(destino_png)).isNull()

    monkeypatch.setattr(ui_reportes.QFileDialog, "getSaveFileName", lambda *a: ("", ""))
    pagina.guardar_pdf()
    assert len(abiertos) == 2  # cancelar no abre nada

    monkeypatch.setattr(ui_reportes, "info", lambda *a: None)
    pagina.copiar_imagen()
    assert not QGuiApplication.clipboard().image().isNull()


def test_nombre_sugerido_incluye_el_contexto(ventana, conn, torneo_id, datos):
    pagina = ventana.reportes
    pagina.filtros.refrescar()
    pagina.filtros.categoria.setCurrentText("2015-2016")
    pagina.fecha.setCurrentIndex(1)
    assert pagina._sugerido("pdf").endswith(
        "Rol de juegos - Copa de Verano - 2015-2016 - 2026-11-07.pdf"
    )


def test_pagina_sin_torneo_no_falla(ventana):
    ventana.reportes.filtros.refrescar()
    assert ventana.reportes.hoja is None
    assert "torneo" in ventana.reportes.aviso.text()
