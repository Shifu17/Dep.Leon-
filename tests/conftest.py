import pytest

from dep_leon import db


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
