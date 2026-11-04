import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from dep_leon import inicio, rol, updater
from dep_leon.ui.ventana import Ventana

HOY = date(2026, 11, 4)


@pytest.fixture
def datos(conn, infantil_id, torneo_id):
    """Dos equipos con un jugador, y partidos pasado, hoy, futuro y pospuesto."""
    categoria = conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2015-2016'", (infantil_id,)
    ).fetchone()["id"]
    with conn:
        a = conn.execute(
            "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, 'Pegasos')",
            (torneo_id, categoria),
        ).lastrowid
        b = conn.execute(
            "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, 'Buitres')",
            (torneo_id, categoria),
        ).lastrowid
        conn.execute(
            "INSERT INTO jugadores (equipo_id, nombre, fecha_nacimiento, numero) "
            "VALUES (?, 'Ana', '2015-01-01', 1)",
            (a,),
        )

        def partido(jornada, fecha, hora, cancha, estado=rol.PROGRAMADO):
            conn.execute(
                "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, "
                "fecha, hora, minutos, cancha, estado) VALUES (?, ?, ?, ?, ?, ?, ?, 50, ?, ?)",
                (torneo_id, categoria, jornada, a, b, fecha, hora, cancha, estado),
            )

        partido(1, (HOY - timedelta(days=1)).isoformat(), "09:00", "1")
        partido(2, (HOY + timedelta(days=3)).isoformat(), "10:00", "2")
        partido(3, HOY.isoformat(), "17:00", "1")
        partido(4, None, None, None, rol.POSPUESTO)
    return infantil_id


def test_resumen_cuenta_por_liga(conn, datos):
    resumen = {r.nombre: r for r in inicio.resumen_por_liga(conn, HOY)}
    infantil = resumen["Infantil"]
    assert (infantil.categorias, infantil.equipos, infantil.jugadores) == (6, 2, 1)
    # El partido de ayer no cuenta como por jugar.
    assert (infantil.por_jugar, infantil.pospuestos) == (2, 1)
    assert resumen["Femenil"].equipos == 0


def test_proximos_en_orden_sin_pasados_ni_pospuestos(conn, datos):
    partidos = inicio.proximos_partidos(conn, HOY)
    assert [p["fecha"] for p in partidos] == [
        HOY.isoformat(), (HOY + timedelta(days=3)).isoformat(),
    ]
    assert inicio.proximos_partidos(conn, HOY, limite=1)[0]["hora"] == "17:00"


def test_filtrar_por_otra_liga_queda_vacio(conn, datos):
    femenil = conn.execute("SELECT id FROM ligas WHERE nombre = 'Femenil'").fetchone()["id"]
    assert inicio.proximos_partidos(conn, HOY, femenil) == []
    assert inicio.equipos_proxima_fecha(conn, HOY, femenil) == (None, [])


def test_equipos_del_proximo_dia_con_su_rival(conn, datos):
    fecha, equipos = inicio.equipos_proxima_fecha(conn, HOY)
    assert fecha == HOY
    assert [(e["equipo"], e["rival"]) for e in equipos] == [
        ("Buitres", "Pegasos"), ("Pegasos", "Buitres"),
    ]


@pytest.mark.parametrize(
    "fecha, esperado",
    [(HOY, "Hoy"), (HOY + timedelta(days=1), "Mañana"), (date(2026, 11, 7), "Sáb 07/11")],
)
def test_dia_corto(fecha, esperado):
    assert inicio.dia_corto(fecha, HOY) == esperado


@pytest.fixture
def ventana(conn, monkeypatch, tmp_path):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    monkeypatch.setattr(rol, "hoy", lambda: HOY)
    resultado = Ventana(conn)
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


def test_el_programa_abre_en_inicio(ventana):
    assert ventana.pila.currentWidget() is ventana.inicio


def test_pantalla_vacia_orienta_a_crear_el_rol(ventana):
    ventana.show()
    pagina = ventana.inicio
    assert pagina.por_jugar.numero.text() == "0"
    assert pagina.sin_proximos.isVisible() and not pagina.proximos.isVisible()


def test_pantalla_muestra_datos_y_filtra(ventana, datos):
    ventana.show()
    pagina = ventana.inicio
    pagina.refrescar()
    assert pagina.equipos.numero.text() == "2"
    assert pagina.por_jugar.numero.text() == "2"
    assert pagina.pospuestos.numero.text() == "1"
    assert pagina.proximos.isVisible() and pagina.proximos.rowCount() == 2
    assert pagina.proximos.item(0, 0).text() == "Hoy"
    assert "Miércoles 4 de noviembre" in pagina.titulo_equipos.text()
    assert pagina.equipos_jugar.rowCount() == 2
    assert pagina.ligas.rowCount() == 6

    pagina.liga.setCurrentIndex(pagina.liga.findText("Femenil"))
    assert pagina.equipos.numero.text() == "0"
    assert pagina.proximos.rowCount() == 0
    assert pagina.titulo_equipos.text() == "Equipos por jugar"
    # El resumen por liga siempre muestra todas.
    assert pagina.ligas.rowCount() == 6


def test_al_volver_a_inicio_se_actualiza(ventana, datos, conn):
    ventana.show()
    ventana.pila.setCurrentWidget(ventana.rol)
    with conn:
        conn.execute("DELETE FROM partidos WHERE estado = ?", (rol.POSPUESTO,))
    ventana.pila.setCurrentWidget(ventana.inicio)
    assert ventana.inicio.pospuestos.numero.text() == "0"
