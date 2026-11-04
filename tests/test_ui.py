"""Comprueba que la ventana arranca y muestra los datos, sin abrir nada en pantalla."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from dep_leon import updater
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
