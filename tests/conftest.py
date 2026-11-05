import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from dep_leon import db
from dep_leon.ui.tema import ESTILO


def aplicacion_con_tema() -> QApplication:
    """Una sola aplicación y un solo tema por corrida.

    Volver a aplicar el tema recalcula todas las ventanas vivas, y entre pruebas se acumulan miles.
    Sin pantalla, Qt tampoco carga las fuentes del sistema, y los anchos medidos no serían reales.
    """
    aplicacion = QApplication.instance() or QApplication([])
    if aplicacion.styleSheet() != ESTILO:
        for fuente in ("segoeui", "segoeuib", "seguisb"):
            QFontDatabase.addApplicationFont(f"C:/Windows/Fonts/{fuente}.ttf")
        aplicacion.setFont(QFont("Segoe UI", 10))
        aplicacion.setStyleSheet(ESTILO)
    return aplicacion


@pytest.fixture(scope="session")
def app():
    return aplicacion_con_tema()


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(tmp_path / "prueba.db")
    yield conexion
    conexion.close()


@pytest.fixture
def infantil_id(conn):
    return conn.execute("SELECT id FROM ligas WHERE nombre = 'Infantil'").fetchone()["id"]


@pytest.fixture
def torneo_id(conn, infantil_id):
    with conn:
        return conn.execute(
            "INSERT INTO torneos (liga_id, nombre) VALUES (?, 'Copa de Verano')", (infantil_id,)
        ).lastrowid
