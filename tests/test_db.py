import pytest

from dep_leon import db


def test_carga_las_categorias_infantiles_de_la_hoja(conn, infantil_id):
    categorias = conn.execute(
        "SELECT nombre, anio_min, anio_max FROM categorias WHERE liga_id = ? ORDER BY nombre",
        (infantil_id,),
    ).fetchall()
    assert [tuple(c) for c in categorias] == [
        ("2009-2010", 2009, 2010),
        ("2011-2012", 2011, 2012),
        ("2013-2014", 2013, 2014),
        ("2015-2016", 2015, 2016),
        ("2017-2018", 2017, 2018),
        ("2019-2020", 2019, 2020),
    ]


def test_domingo_es_la_unica_liga_de_fut_11(conn):
    filas = conn.execute("SELECT nombre, dias FROM ligas WHERE modalidad = 'Fut 11'").fetchall()
    assert [tuple(f) for f in filas] == [("Fut 11", "Domingo")]


def test_no_recarga_los_datos_iniciales(tmp_path):
    ruta = tmp_path / "liga.db"
    primera = db.conectar(ruta)
    with primera:
        primera.execute("DELETE FROM categorias")
    primera.close()
    segunda = db.conectar(ruta)
    assert segunda.execute("SELECT COUNT(*) FROM categorias").fetchone()[0] == 0
    segunda.close()


def test_respaldo_y_restauracion_con_fotos(conn, tmp_path, torneo_id):
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    (fotos / "a.jpg").write_bytes(b"foto")
    respaldo = tmp_path / "respaldo.zip"
    db.respaldar(conn, respaldo, fotos)

    with conn:
        conn.execute("DELETE FROM torneos")
    (fotos / "a.jpg").unlink()

    db.restaurar(conn, respaldo, fotos)
    assert conn.execute("SELECT COUNT(*) FROM torneos").fetchone()[0] == 1
    assert (fotos / "a.jpg").read_bytes() == b"foto"


def test_restaurar_rechaza_un_archivo_ajeno(conn, tmp_path):
    ajeno = tmp_path / "ajeno.zip"
    ajeno.write_bytes(b"no soy un zip")
    with pytest.raises(ValueError):
        db.restaurar(conn, ajeno, tmp_path)
