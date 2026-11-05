"""Flujo de trabajo: selección compartida, atrasados, ordenar, buscar y atajos."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, timedelta

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from dep_leon import inicio, resultados, rol, updater
from dep_leon.ui import comun
from dep_leon.ui import pagina_resultados as ui_resultados
from dep_leon.ui.ventana import Ventana


@pytest.fixture
def ventana(app, conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    resultado = Ventana(conn)
    resultado.show()
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


@pytest.fixture
def categorias(conn, infantil_id):
    return {
        c["nombre"]: c["id"]
        for c in conn.execute("SELECT * FROM categorias WHERE liga_id = ?", (infantil_id,))
    }


def crear_equipo(conn, torneo_id, categoria, nombre, jugadores=()):
    with conn:
        equipo = conn.execute(
            "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
            (torneo_id, categoria, nombre),
        ).lastrowid
        for i, jugador in enumerate(jugadores):
            conn.execute(
                "INSERT INTO jugadores (equipo_id, nombre, fecha_nacimiento, numero) VALUES (?, ?, '2015-01-01', ?)",
                (equipo, jugador, i),
            )
    return equipo


def crear_partido(conn, torneo_id, categoria, a, b, fecha, jornada=1):
    with conn:
        return conn.execute(
            "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, fecha, hora, "
            "minutos, cancha, estado) VALUES (?, ?, ?, ?, ?, ?, '09:00', 50, '1', ?)",
            (torneo_id, categoria, jornada, a, b, fecha.isoformat(), rol.PROGRAMADO),
        ).lastrowid


def textos(tabla_, columna=0):
    return [
        tabla_.item(r, columna).text() for r in range(tabla_.rowCount()) if not tabla_.isRowHidden(r)
    ]


# --- Selección compartida


@pytest.fixture
def dos_ligas(conn, infantil_id, torneo_id, categorias):
    femenil = conn.execute("SELECT id FROM ligas WHERE nombre = 'Femenil'").fetchone()["id"]
    with conn:
        conn.execute("INSERT INTO categorias (liga_id, nombre) VALUES (?, 'Libre')", (femenil,))
        otro = conn.execute("INSERT INTO torneos (liga_id, nombre) VALUES (?, 'Apertura')", (femenil,)).lastrowid
    crear_equipo(conn, torneo_id, categorias["2015-2016"], "A")
    return femenil, otro


def _elegir(combo, dato):
    indice = combo.findData(dato)
    combo.setCurrentIndex(indice)
    combo.activated.emit(indice)


def test_la_seleccion_se_conserva_al_cambiar_de_pantalla(ventana, app, dos_ligas):
    femenil, otro = dos_ligas
    ventana._mostrar(ventana.rol)
    _elegir(ventana.rol.filtros.liga, femenil)
    app.processEvents()
    assert ventana.rol.filtros.seleccion()[:2] == (femenil, otro)

    for pagina in (ventana.equipos, ventana.resultados, ventana.cobros, ventana.reportes, ventana.liguilla):
        ventana._mostrar(pagina)
        assert pagina.filtros.seleccion()[:2] == (femenil, otro), type(pagina).__name__


def test_la_categoria_elegida_tambien_viaja(ventana, dos_ligas, categorias, infantil_id, torneo_id):
    ventana._mostrar(ventana.equipos)
    _elegir(ventana.equipos.filtros.categoria, categorias["2017-2018"])
    ventana._mostrar(ventana.estadisticas)
    assert ventana.estadisticas.filtros.categoria.currentText() == "2017-2018"
    ventana._mostrar(ventana.resultados)
    assert ventana.resultados.filtros.categoria.currentText() == "2017-2018"


def test_sin_eleccion_cada_pantalla_conserva_su_vista(ventana, dos_ligas):
    ventana._mostrar(ventana.equipos)
    assert ventana.equipos.filtros.categoria.currentText() == "Todas"
    ventana._mostrar(ventana.estadisticas)
    # Estadísticas abre en una categoría con equipos, y eso no le cambia el filtro a Equipos.
    assert ventana.estadisticas.filtros.categoria.currentText() == "2015-2016"
    ventana._mostrar(ventana.equipos)
    assert ventana.equipos.filtros.categoria.currentText() == "Todas"


def test_aplicar_avisa_una_sola_vez(ventana, dos_ligas):
    femenil, otro = dos_ligas
    avisos = []
    ventana.cobros.filtros.cambiado.connect(lambda: avisos.append(1))
    ventana.cobros.filtros.aplicar(femenil, otro, None)
    assert avisos == [1]


def test_seleccion_de_liga_o_torneo_borrados_no_falla(ventana, dos_ligas):
    ventana.cobros.filtros.aplicar(99999, 88888, 77777)
    assert ventana.cobros.filtros.liga.currentIndex() == 0


# --- Atrasados


HOY = date(2026, 11, 20)


@pytest.fixture
def con_atrasados(conn, torneo_id, categorias, monkeypatch):
    monkeypatch.setattr(rol, "hoy", lambda: HOY)
    cat = categorias["2015-2016"]
    a = crear_equipo(conn, torneo_id, cat, "Águilas")
    b = crear_equipo(conn, torneo_id, cat, "Toros")
    viejo = crear_partido(conn, torneo_id, cat, a, b, HOY - timedelta(days=7))
    crear_partido(conn, torneo_id, cat, b, a, HOY - timedelta(days=14), 2)
    crear_partido(conn, torneo_id, cat, a, b, HOY + timedelta(days=2), 3)
    hecho = crear_partido(conn, torneo_id, cat, b, a, HOY - timedelta(days=21), 4)
    resultados.guardar_resultado(conn, hecho, 1, 0)
    return viejo


def test_resumen_cuenta_atrasados_aparte(conn, con_atrasados):
    infantil = next(r for r in inicio.resumen_por_liga(conn, HOY) if r.nombre == "Infantil")
    assert (infantil.por_jugar, infantil.por_capturar, infantil.jugados) == (1, 2, 1)


def test_partido_de_hoy_no_esta_atrasado(conn, torneo_id, categorias):
    cat = categorias["2015-2016"]
    a, b = crear_equipo(conn, torneo_id, cat, "A"), crear_equipo(conn, torneo_id, cat, "B")
    crear_partido(conn, torneo_id, cat, a, b, HOY)
    infantil = next(r for r in inicio.resumen_por_liga(conn, HOY) if r.nombre == "Infantil")
    assert (infantil.por_jugar, infantil.por_capturar) == (1, 0)


def test_inicio_avisa_y_lleva_a_capturar(ventana, app, conn, con_atrasados, torneo_id, infantil_id):
    pagina = ventana.inicio
    pagina.refrescar()
    app.processEvents()
    assert pagina.por_capturar.numero.text() == "2"
    assert pagina.por_capturar.numero.objectName() == "tarjetaAlerta"
    assert pagina.aviso.isVisible()
    assert pagina.aviso_texto.text() == "2 partidos ya pasaron y no tienen resultado."

    pagina._capturar()
    assert ventana.pila.currentWidget() is ventana.resultados
    assert ventana.resultados.filtros.seleccion()[:2] == (infantil_id, torneo_id)
    assert ventana.resultados.ver.currentText() == ui_resultados.VER_POR_CAPTURAR
    assert textos(ventana.resultados.tabla, 7) == [rol.ATRASADO, rol.ATRASADO, rol.PROGRAMADO]
    # Lo más antiguo primero.
    fechas = textos(ventana.resultados.tabla, 0)
    assert fechas[0] == (HOY - timedelta(days=14)).strftime("%d/%m/%Y")


def test_sin_atrasados_no_hay_aviso(ventana, conn, torneo_id):
    ventana.inicio.refrescar()
    assert not ventana.inicio.aviso.isVisible()
    assert ventana.inicio.por_capturar.numero.objectName() == "tarjetaNumero"
    assert ventana.inicio.por_capturar.numero.text() == "0"


def test_con_resultado_deja_de_estar_atrasado(ventana, conn, con_atrasados):
    resultados.guardar_resultado(conn, con_atrasados, 2, 1)
    ventana.inicio.refrescar()
    assert ventana.inicio.por_capturar.numero.text() == "1"
    assert ventana.inicio.aviso_texto.text() == "1 partido ya pasó y no tiene resultado."


# --- Ordenar


@pytest.mark.parametrize(
    "columna, valores, esperado",
    [
        ("Pts", ["9", "10", "2"], ["2", "9", "10"]),
        ("Saldo", ["$1,000.00", "$200.00", "$0.50"], ["$0.50", "$200.00", "$1,000.00"]),
        ("DG", ["+3", "-1", "0"], ["-1", "0", "+3"]),
        ("Equipo", ["Toros", "Águilas", "Ñandúes"], ["Águilas", "Ñandúes", "Toros"]),
        ("Fecha", ["01/12/2026", "15/11/2026", "Sin fecha", "20/01/2026"],
         ["20/01/2026", "15/11/2026", "01/12/2026", "Sin fecha"]),
        ("Hora", ["09:50", "09:00", "-", "12:20"], ["09:00", "09:50", "12:20", "-"]),
    ],
)
def test_ordena_por_el_valor_real(app, columna, valores, esperado):
    tabla_ = comun.tabla([columna])
    comun.llenar(tabla_, [(i, [v]) for i, v in enumerate(valores)])
    assert textos(tabla_) == valores  # el orden original se respeta hasta pulsar el encabezado
    tabla_.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    assert textos(tabla_) == esperado


def test_rellenar_conserva_orden_y_seleccion(app):
    tabla_ = comun.tabla(["Equipo", "Pts"])
    filas = [(1, ["A", "3"]), (2, ["B", "9"]), (3, ["C", "1"])]
    comun.llenar(tabla_, filas)
    tabla_.sortByColumn(1, Qt.SortOrder.DescendingOrder)
    tabla_.selectRow(2)  # C, con la tabla ya ordenada
    assert comun.id_seleccionado(tabla_) == 3

    comun.llenar(tabla_, filas)
    assert textos(tabla_) == ["B", "A", "C"]
    assert comun.id_seleccionado(tabla_) == 3


def test_tablas_de_inicio_no_se_reordenan(ventana):
    assert not ventana.inicio.proximos.isSortingEnabled()
    assert ventana.estadisticas.clasificacion.isSortingEnabled()


# --- Buscar


def test_buscar_sin_acentos_ni_mayusculas(app):
    tabla_ = comun.tabla(["Equipo"])
    comun.llenar(tabla_, [(1, ["Águilas"]), (2, ["Toros"])])
    comun.filtrar(tabla_, "AGUI")
    assert textos(tabla_) == ["Águilas"]
    comun.filtrar(tabla_, "")
    assert textos(tabla_) == ["Águilas", "Toros"]


def test_busqueda_sobrevive_al_rellenar(app):
    tabla_ = comun.tabla(["Equipo"])
    comun.llenar(tabla_, [(1, ["Águilas"]), (2, ["Toros"])])
    comun.filtrar(tabla_, "tor")
    comun.llenar(tabla_, [(1, ["Águilas"]), (2, ["Toros"]), (3, ["Torito"])])
    assert textos(tabla_) == ["Toros", "Torito"]


def test_ocultar_la_fila_elegida_quita_la_seleccion(app):
    tabla_ = comun.tabla(["Equipo"])
    comun.llenar(tabla_, [(1, ["Águilas"]), (2, ["Toros"])])
    tabla_.selectRow(0)
    comun.filtrar(tabla_, "toros")
    assert comun.id_seleccionado(tabla_) is None  # una acción no debe caer en una fila oculta


def test_buscar_en_equipos_encuentra_jugadores(ventana, app, conn, torneo_id, categorias):
    cat = categorias["2015-2016"]
    crear_equipo(conn, torneo_id, cat, "Águilas", ["Juan Pérez", "Luis Díaz"])
    crear_equipo(conn, torneo_id, cat, "Toros", ["Mateo Ruiz"])
    pagina = ventana.equipos
    ventana._mostrar(pagina)
    pagina.refrescar()

    pagina.busqueda.setText("perez")
    assert textos(pagina.tabla_equipos) == ["Águilas"]
    assert textos(pagina.tabla_jugadores, 1) == ["Juan Pérez"]

    pagina.busqueda.setText("toros")
    assert textos(pagina.tabla_equipos) == ["Toros"]
    assert textos(pagina.tabla_jugadores, 1) == ["Mateo Ruiz"]  # coincide el equipo: se ven todos

    pagina.busqueda.clear()
    assert len(textos(pagina.tabla_equipos)) == 2


def test_buscar_en_rol(ventana, conn, torneo_id, categorias):
    cat = categorias["2015-2016"]
    a, b = crear_equipo(conn, torneo_id, cat, "Águilas"), crear_equipo(conn, torneo_id, cat, "Toros")
    c = crear_equipo(conn, torneo_id, cat, "Linces")
    crear_partido(conn, torneo_id, cat, a, b, date(2030, 1, 5))
    crear_partido(conn, torneo_id, cat, c, b, date(2030, 1, 12), 2)
    pagina = ventana.rol
    pagina.refrescar()
    pagina.fecha.setCurrentIndex(0)
    pagina.busqueda.setText("lince")
    assert textos(pagina.tabla, 2) == ["Linces"]


# --- Atajos


def test_ctrl_numero_cambia_de_pantalla(ventana, app):
    ventana.activateWindow()
    app.processEvents()
    QTest.keyClick(ventana, Qt.Key.Key_4, Qt.KeyboardModifier.ControlModifier)
    assert ventana.pila.currentWidget() is ventana.rol
    QTest.keyClick(ventana, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)
    assert ventana.pila.currentWidget() is ventana.config
    assert ventana._navegacion[ventana.rol].toolTip() == "Ctrl+4"


def test_ctrl_f_va_al_buscador(ventana, app):
    ventana.activateWindow()
    ventana._mostrar(ventana.equipos)
    app.processEvents()
    QTest.keyClick(ventana, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert ventana.equipos.busqueda.hasFocus()


def test_ctrl_f_sin_buscador_no_falla(ventana):
    ventana._mostrar(ventana.config)
    ventana._enfocar_busqueda()


def test_f5_actualiza_la_pantalla(ventana, conn, torneo_id, categorias):
    ventana._mostrar(ventana.equipos)
    crear_equipo(conn, torneo_id, categorias["2015-2016"], "Nuevo")
    assert ventana.equipos.tabla_equipos.rowCount() == 0
    ventana._refrescar_pagina()
    assert ventana.equipos.tabla_equipos.rowCount() == 1


def test_enter_y_doble_clic_activan_la_fila(app):
    llamadas = []
    tabla_ = comun.tabla(["Equipo"])
    comun.al_activar(tabla_, lambda: llamadas.append(1))
    comun.llenar(tabla_, [(1, ["A"])])
    tabla_.show()
    tabla_.activateWindow()
    tabla_.setFocus()
    tabla_.selectRow(0)
    app.processEvents()
    QTest.keyClick(tabla_, Qt.Key.Key_Return)
    assert llamadas == [1]
    tabla_.doubleClicked.emit(tabla_.model().index(0, 0))
    assert llamadas == [1, 1]
    tabla_.close()


def test_buscador_tiene_nombre_accesible(ventana):
    assert ventana.equipos.busqueda.accessibleName() == "Buscar equipo o jugador"
    assert ventana.cobros.busqueda.accessibleName() == "Buscar equipo"


# --- Regresiones de presentación


def _celdas_recortadas(tabla_) -> list[str]:
    mal = []
    for r in range(tabla_.rowCount()):
        for c in range(tabla_.columnCount()):
            celda = tabla_.item(r, c)
            if celda and tabla_.fontMetrics().horizontalAdvance(celda.text()) + 8 > tabla_.columnWidth(c):
                mal.append(celda.text())
    return mal


def _ventana_normal(ventana, app):
    ventana.resize(1200, 760)
    app.processEvents()


def test_ordenar_no_recorta_nombres(ventana, app, conn, torneo_id, categorias):
    for nombre in ("Águilas", "Toros", "Linces", "Ñandúes"):
        crear_equipo(conn, torneo_id, categorias["2015-2016"], nombre)
    _ventana_normal(ventana, app)
    ventana._mostrar(ventana.estadisticas)
    app.processEvents()
    tabla_ = ventana.estadisticas.clasificacion
    assert _celdas_recortadas(tabla_) == []
    tabla_.sortByColumn(6, Qt.SortOrder.DescendingOrder)
    app.processEvents()
    assert _celdas_recortadas(tabla_) == []


def test_columna_ordenada_se_marca_solo_en_esa(app):
    tabla_ = comun.tabla(["Equipo", "Pts"])
    comun.llenar(tabla_, [(1, ["A", "1"])])
    assert tabla_.horizontalHeaderItem(1).icon().isNull()
    tabla_.sortByColumn(1, Qt.SortOrder.DescendingOrder)
    assert not tabla_.horizontalHeaderItem(1).icon().isNull()
    assert tabla_.horizontalHeaderItem(0).icon().isNull()
    assert not tabla_.horizontalHeader().isSortIndicatorShown()
    tabla_.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    assert tabla_.horizontalHeaderItem(1).icon().isNull()


def test_nombres_de_liga_caben_en_inicio(ventana, app):
    _ventana_normal(ventana, app)
    ventana.inicio.refrescar()
    app.processEvents()
    assert _celdas_recortadas(ventana.inicio.ligas) == []


def test_buscador_no_ensancha_la_ventana(ventana, app):
    assert ventana.minimumSizeHint().width() <= 1024
    ventana._mostrar(ventana.cobros)
    app.processEvents()
    assert ventana.cobros.cargos.horizontalScrollBar().maximum() == 0


def test_al_abrir_ningun_boton_del_menu_tiene_foco(app, conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    nueva = Ventana(conn)
    nueva.show()
    nueva.activateWindow()
    app.processEvents()
    assert not any(b.hasFocus() for b in nueva._navegacion.values())
    nueva.temporizador.stop()
    nueva.close()
