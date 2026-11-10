"""Paquete C: errores junto al campo, menos botones, pantallas vacías e Inicio renovado."""

from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QPushButton

from dep_leon import cobros, inicio, resultados, rol, updater
from dep_leon.ui import comun
from dep_leon.ui import pagina_cobros as ui_cobros
from dep_leon.ui import pagina_equipos as ui_equipos
from dep_leon.ui import pagina_ligas as ui_ligas
from dep_leon.ui.ventana import Ventana

HOY = date(2026, 11, 20)


@pytest.fixture
def ventana(app, conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    monkeypatch.setattr(rol, "hoy", lambda: HOY)
    resultado = Ventana(conn)
    resultado.resize(1200, 760)
    resultado.show()
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


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


def crear_partido(conn, torneo_id, categoria, a, b, fecha, estado=rol.PROGRAMADO, jornada=1):
    with conn:
        return conn.execute(
            "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, fecha, hora, "
            "minutos, cancha, estado) VALUES (?, ?, ?, ?, ?, ?, ?, 50, ?, ?)",
            (
                torneo_id, categoria, jornada, a, b, fecha.isoformat() if fecha else None,
                "09:00" if fecha else None, "1" if fecha else None, estado,
            ),
        ).lastrowid


# --- Errores junto al campo


def test_error_aparece_junto_al_campo_y_se_borra_al_corregir(app):
    dialogo = ui_ligas.DialogoLiga(None)
    dialogo.show()
    dialogo._aceptar()
    assert dialogo.result() == 0
    assert dialogo.error_nombre.isVisible()
    assert dialogo.error_nombre.text() == "Escribe el nombre de la liga."
    assert dialogo.nombre.property("invalido") is True
    assert dialogo.nombre.accessibleDescription() == "Escribe el nombre de la liga."

    dialogo.nombre.textEdited.emit("Liga nueva")
    assert not dialogo.error_nombre.isVisible()
    assert dialogo.nombre.property("invalido") is False
    dialogo.close()


def test_edad_fuera_de_categoria_se_marca_en_la_fecha(app):
    categoria = {"anio_min": 2015, "anio_max": 2016}
    dialogo = ui_equipos.DialogoJugador(None, categoria)
    dialogo.show()
    dialogo.nombre.setText("Ana")
    dialogo.fecha.setDate(date(2012, 1, 1))
    dialogo._aceptar()
    assert dialogo.result() == 0
    assert "2012" in dialogo.error_fecha.text() and dialogo.error_fecha.isVisible()
    assert not dialogo.error_nombre.isVisible()
    dialogo.close()


def test_monto_en_cero_se_marca_en_el_monto(app):
    dialogo = ui_cobros.DialogoPago(None, "Águilas", 10000, 0)
    dialogo.show()
    dialogo._aceptar()
    assert dialogo.error_monto.isVisible() and dialogo.result() == 0
    dialogo.monto.setValue(50)
    assert not dialogo.error_monto.isVisible()
    dialogo.close()


# --- Menos botones


def _botones_visibles(pagina):
    return [b for b in pagina.findChildren(QPushButton) if b.isVisible() and b.objectName() != "llave"]


def test_equipos_deja_a_la_vista_lo_frecuente(ventana, app):
    ventana._mostrar(ventana.equipos)
    app.processEvents()
    botones = _botones_visibles(ventana.equipos)
    textos = [b.text() for b in botones]
    assert len(botones) <= 10, textos
    assert sum(b.objectName() == "" for b in botones) <= 2  # solo los dos «Agregar» son principales
    for visible in ("Importar Excel", "Exportar Excel", "Credenciales PDF", "Pase de lista"):
        assert visible in textos, textos
    menus = {b.text(): [a.text() for a in b.menu().actions()] for b in botones if b.menu()}
    assert "Eliminar equipo" in menus["Más opciones"]
    assert "Descargar plantilla de Excel vacía" in menus["Más opciones"]


def test_menu_ejecuta_la_accion(app):
    llamadas = []
    mas = comun.boton_mas("Más", [("Uno", lambda: llamadas.append(1))])
    mas.menu().actions()[0].trigger()
    assert llamadas == [1]


def test_rol_y_liguilla_esconden_lo_destructivo(ventana, app):
    for pagina in (ventana.rol, ventana.liguilla):
        textos = [a.text() for b in pagina.findChildren(QPushButton) if b.menu() for a in b.menu().actions()]
        assert any("Eliminar" in t for t in textos), type(pagina).__name__
        sueltos = [b.text() for b in pagina.findChildren(QPushButton) if not b.menu()]
        assert not any(t.startswith("Eliminar") for t in sueltos), sueltos


# --- Pantallas vacías


def _vacio(tabla_):
    return tabla_._vacio.text() if tabla_._vacio.isVisibleTo(tabla_) else ""


def test_sin_torneo_orienta_a_crearlo(ventana, app):
    ventana._mostrar(ventana.equipos)
    app.processEvents()
    assert "crea un torneo" in _vacio(ventana.equipos.tabla_equipos)


def test_tablas_vacias_explican_que_hacer(ventana, app, conn, torneo_id, categoria):
    ventana._mostrar(ventana.equipos)
    ventana.equipos.refrescar()
    assert "Pulsa «Agregar equipo»" in _vacio(ventana.equipos.tabla_equipos)
    assert "Selecciona un equipo" in _vacio(ventana.equipos.tabla_jugadores)

    crear_equipo(conn, torneo_id, categoria, "Águilas")
    ventana.equipos.refrescar()
    assert _vacio(ventana.equipos.tabla_equipos) == ""
    ventana.equipos.tabla_equipos.selectRow(0)
    assert "no tiene jugadores" in _vacio(ventana.equipos.tabla_jugadores)

    ventana._mostrar(ventana.rol)
    assert "Generar rol" in _vacio(ventana.rol.tabla)


def test_busqueda_sin_resultados_lo_dice(app):
    tabla_ = comun.tabla(["Equipo"])
    comun.poner_vacio(tabla_, "No hay equipos.")
    comun.llenar(tabla_, [(1, ["Águilas"])])
    tabla_.show()
    comun.filtrar(tabla_, "zzz")
    assert _vacio(tabla_) == "Ninguna fila coincide con la búsqueda."
    comun.filtrar(tabla_, "")
    assert _vacio(tabla_) == ""
    comun.llenar(tabla_, [])
    assert _vacio(tabla_) == "No hay equipos."
    tabla_.close()


# --- Inicio


def test_inicio_muestra_la_fecha_de_hoy(ventana):
    assert ventana.inicio.titulo.text() == "Viernes 20 de noviembre del 2026"


def test_primeros_pasos_guian_desde_cero(ventana, app, conn, infantil_id, categoria):
    pagina = ventana.inicio
    pagina.refrescar()
    assert pagina.pendiente_paso.isVisibleTo(pagina)
    assert "crea un torneo" in pagina.pendiente_paso.texto.text()
    pagina._ir("paso")
    assert ventana.pila.currentWidget() is ventana.ligas

    with conn:
        torneo = conn.execute(
            "INSERT INTO torneos (liga_id, nombre) VALUES (?, 'Copa')", (infantil_id,)
        ).lastrowid
    pagina.refrescar()
    assert "registra los equipos" in pagina.pendiente_paso.texto.text()
    a, b = crear_equipo(conn, torneo, categoria, "A"), crear_equipo(conn, torneo, categoria, "B")
    pagina.refrescar()
    assert "genera el rol" in pagina.pendiente_paso.texto.text()
    crear_partido(conn, torneo, categoria, a, b, HOY + timedelta(days=2))
    pagina.refrescar()
    assert not pagina.pendiente_paso.isVisibleTo(pagina)
    assert pagina.al_dia.isVisibleTo(pagina)


def test_pendientes_llevan_a_resolverlos(ventana, app, conn, torneo_id, categoria, infantil_id):
    a, b = crear_equipo(conn, torneo_id, categoria, "A"), crear_equipo(conn, torneo_id, categoria, "B")
    crear_partido(conn, torneo_id, categoria, a, b, HOY - timedelta(days=3))
    crear_partido(conn, torneo_id, categoria, b, a, None, rol.POR_PROGRAMAR, 2)
    cobros.guardar_tarifas(conn, torneo_id, {categoria: (0, 50000)})
    pagina = ventana.inicio
    pagina.refrescar()

    assert pagina.aviso.isVisibleTo(pagina)
    assert pagina.pendiente_fecha.texto.text().startswith("1 partido no tiene fecha")
    assert pagina.pendiente_cobro.texto.text() == "Hay $1,000.00 por cobrar en inscripciones y arbitrajes."
    assert not pagina.al_dia.isVisibleTo(pagina)

    pagina._ir("rol")
    assert ventana.pila.currentWidget() is ventana.rol
    assert ventana.rol.fecha.currentIndex() == 0
    estados = [ventana.rol.tabla.item(r, 7).text() for r in range(ventana.rol.tabla.rowCount())]
    assert rol.POR_PROGRAMAR in estados

    ventana._mostrar(ventana.inicio)
    pagina._ir("cobros")
    assert ventana.pila.currentWidget() is ventana.cobros
    assert ventana.cobros.filtros.seleccion()[:2] == (infantil_id, torneo_id)


def test_datos_de_pendientes(conn, torneo_id, categoria):
    a, b = crear_equipo(conn, torneo_id, categoria, "A"), crear_equipo(conn, torneo_id, categoria, "B")
    assert inicio.sin_fecha(conn) == (0, None)
    partido = crear_partido(conn, torneo_id, categoria, a, b, HOY)
    rol.posponer(conn, partido)
    assert inicio.sin_fecha(conn)[0] == 1
    assert inicio.por_cobrar(conn) == (0, None)
    cobros.guardar_tarifas(conn, torneo_id, {categoria: (0, 10000)})
    total, destino = inicio.por_cobrar(conn)
    assert total == 20000 and destino[1] == torneo_id


def test_resumen_solo_ligas_con_equipos_y_franja_compacta(ventana, app, conn, torneo_id, categoria):
    crear_equipo(conn, torneo_id, categoria, "A")
    ventana.inicio.refrescar()
    assert ventana.inicio.ligas.rowCount() == 1
    assert ventana.inicio.ligas.item(0, 0).text() == "Infantil"
    assert ventana.inicio.equipos.numero.objectName() == "datoNumero"


def test_inicio_cabe_en_1024_con_datos(ventana, app, conn, torneo_id, categoria):
    a, b = crear_equipo(conn, torneo_id, categoria, "Deportivo León Blanco"), crear_equipo(conn, torneo_id, categoria, "Valle Arizpe")
    crear_partido(conn, torneo_id, categoria, a, b, HOY + timedelta(days=1))
    crear_partido(conn, torneo_id, categoria, b, a, HOY - timedelta(days=1), jornada=2)
    ventana._mostrar(ventana.inicio)
    ventana.inicio.refrescar()
    app.processEvents()
    for i in range(ventana.pila.count()):
        ventana.pila.setCurrentIndex(i)
        app.processEvents()
        assert ventana.minimumSizeHint().width() <= 1024, type(ventana.pila.currentWidget()).__name__


def test_resumen_por_liga_solo_cuando_compara(ventana, app, conn, torneo_id, categoria):
    crear_equipo(conn, torneo_id, categoria, "A")
    pagina = ventana.inicio
    pagina.refrescar()
    assert not pagina.ligas.isVisibleTo(pagina)  # una sola liga: la franja ya lo dice
    femenil = conn.execute("SELECT id FROM ligas WHERE nombre = 'Femenil'").fetchone()["id"]
    with conn:
        cat = conn.execute("INSERT INTO categorias (liga_id, nombre) VALUES (?, 'Libre')", (femenil,)).lastrowid
        otro = conn.execute("INSERT INTO torneos (liga_id, nombre) VALUES (?, 'Apertura')", (femenil,)).lastrowid
    crear_equipo(conn, otro, cat, "B")
    pagina.refrescar()
    assert pagina.ligas.isVisibleTo(pagina) and pagina.ligas.rowCount() == 2
    pagina.liga.setCurrentIndex(pagina.liga.findData(femenil))
    assert not pagina.ligas.isVisibleTo(pagina)
