"""Comprueba que la ventana arranca y muestra los datos, sin abrir nada en pantalla."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from PySide6.QtCore import QDate, QTime

from dep_leon import updater
from dep_leon.ui import pagina_equipos as pagina_equipos_mod
from dep_leon.ui import pagina_rol as pagina_rol_mod
from dep_leon.ui.tema import ESTILO
from dep_leon.ui.ventana import Ventana


@pytest.fixture(scope="session")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    aplicacion.setStyleSheet(ESTILO)
    return aplicacion


@pytest.fixture
def ventana(app, conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    resultado = Ventana(conn)
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


def test_ligas_y_categorias_infantiles_visibles(ventana):
    ligas = ventana.ligas
    assert ligas.tabla_ligas.rowCount() == 6
    fila = next(
        r for r in range(6) if ligas.tabla_ligas.item(r, 0).text() == "Infantil"
    )
    ligas.tabla_ligas.selectRow(fila)
    assert ligas.tabla_categorias.rowCount() == 6
    assert ligas.tabla_categorias.item(0, 0).text() == "2009-2010"


def test_equipos_abre_en_la_liga_infantil(ventana, conn, torneo_id):
    ventana.equipos.refrescar()
    assert ventana.equipos.liga.currentText() == "Infantil"
    assert ventana.equipos.torneo.currentText() == "Copa de Verano"
    assert ventana.equipos.categoria.count() == 7  # Todas + 6


def test_equipos_muestra_jugadores(ventana, conn, infantil_id, torneo_id):
    categoria = conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? LIMIT 1", (infantil_id,)
    ).fetchone()["id"]
    with conn:
        equipo = conn.execute(
            "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, 'Pegasos')",
            (torneo_id, categoria),
        ).lastrowid
        conn.execute(
            "INSERT INTO jugadores (equipo_id, nombre, fecha_nacimiento, numero) "
            "VALUES (?, 'Ana', '2009-05-01', 4)",
            (equipo,),
        )
    pagina = ventana.equipos
    pagina.refrescar()
    pagina.tabla_equipos.selectRow(0)
    assert pagina.tabla_jugadores.item(0, 1).text() == "Ana"
    assert pagina.tabla_jugadores.item(0, 2).text() == "01/05/2009"


@pytest.fixture
def pagina_rol(ventana, conn, infantil_id, torneo_id, monkeypatch):
    categoria = conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2015-2016'", (infantil_id,)
    ).fetchone()["id"]
    with conn:
        for nombre in ("Halcones", "Pegasos", "Buitres"):
            conn.execute(
                "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
                (torneo_id, categoria, nombre),
            )
    monkeypatch.setattr(pagina_rol_mod, "info", lambda *a: None)
    monkeypatch.setattr(pagina_rol_mod, "confirmar", lambda *a: True)
    ventana.rol.refrescar()
    return ventana.rol


def test_generar_rol_desde_la_pagina_va_a_la_primera_fecha(pagina_rol, conn, monkeypatch):
    monkeypatch.setattr(pagina_rol_mod.DialogoGenerar, "exec", lambda self: True)
    pagina_rol.generar()

    assert conn.execute("SELECT COUNT(*) FROM partidos").fetchone()[0] == 3
    assert pagina_rol.fecha.currentIndex() >= 1
    assert pagina_rol.tabla.rowCount() == 1
    assert pagina_rol.descansan.text().startswith("Descansan:")
    assert "Torneo Copa de Verano" in pagina_rol.titulo.text()
    # Se recuerda el horario para la siguiente vez.
    assert conn.execute("SELECT COUNT(*) FROM config_rol").fetchone()[0] == 1


def test_posponer_mantiene_visible_el_partido_y_todas_no_salta(pagina_rol, conn, monkeypatch):
    monkeypatch.setattr(pagina_rol_mod.DialogoGenerar, "exec", lambda self: True)
    pagina_rol.generar()
    pagina_rol.fecha.setCurrentIndex(0)
    assert pagina_rol.tabla.rowCount() == 3

    pagina_rol.tabla.selectRow(0)
    pagina_rol.posponer()

    assert pagina_rol.fecha.currentIndex() == 0
    assert pagina_rol.tabla.rowCount() == 3
    textos = [pagina_rol.tabla.item(r, 7).text() for r in range(3)]
    assert textos.count("Pospuesto") == 1
    assert pagina_rol.tabla.item(2, 0).text() == "Por definir"


def test_dialogo_de_partido_bloquea_empalme(pagina_rol, conn, monkeypatch):
    monkeypatch.setattr(pagina_rol_mod.DialogoGenerar, "exec", lambda self: True)
    pagina_rol.generar()
    partido = conn.execute("SELECT * FROM partidos ORDER BY fecha LIMIT 1").fetchone()
    otro = conn.execute("SELECT * FROM partidos WHERE id <> ? LIMIT 1", (partido["id"],)).fetchone()
    errores = []
    monkeypatch.setattr(pagina_rol_mod, "error", lambda _, m: errores.append(m))
    categorias = conn.execute("SELECT * FROM categorias").fetchall()
    dialogo = pagina_rol_mod.DialogoPartido(
        pagina_rol, conn, partido["torneo_id"], "Fut 7", categorias, otro
    )
    dialogo.fecha.setDate(QDate.fromString(partido["fecha"], "yyyy-MM-dd"))
    h, m = map(int, partido["hora"].split(":"))
    dialogo.hora.setTime(QTime(h, m))
    dialogo.cancha.setCurrentIndex(dialogo.cancha.findData(partido["cancha"]))
    dialogo._aceptar()
    assert errores and "ocupada" in errores[0]
    assert dialogo.result() == 0


def test_equipo_con_partidos_no_se_borra(ventana, pagina_rol, monkeypatch):
    monkeypatch.setattr(pagina_rol_mod.DialogoGenerar, "exec", lambda self: True)
    pagina_rol.generar()
    errores = []
    monkeypatch.setattr(pagina_equipos_mod, "error", lambda _, m: errores.append(m))
    ventana.equipos.refrescar()
    ventana.equipos.tabla_equipos.selectRow(0)
    ventana.equipos.borrar_equipo()
    assert "partidos en el rol" in errores[0]
