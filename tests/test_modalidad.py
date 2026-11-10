import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date

import pytest

from dep_leon import db, rol
from dep_leon.ui import pagina_ligas as ui_ligas
from dep_leon.ui import pagina_rol as ui_rol

SABADO = date(2026, 11, 7)


def _categoria(conn, infantil_id, nombre):
    return conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = ?", (infantil_id, nombre)
    ).fetchone()["id"]


def _equipos(conn, torneo_id, categoria, cuantos):
    with conn:
        for n in range(cuantos):
            conn.execute("INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
                         (torneo_id, categoria, f"E{categoria}-{n}"))


def test_reglas_de_cancha():
    assert rol.canchas_de_modalidad("Fut 7") == rol.canchas_de_modalidad("Fut 8") == ["1", "2"]
    assert rol.canchas_de_modalidad("Fut 9") == rol.canchas_de_modalidad("Fut 11") == [rol.CANCHA_FUT_11]
    assert rol.nombre_cancha(rol.CANCHA_FUT_11) == "Completa" and rol.lugar("1") == "Cancha 1"


def test_la_categoria_hereda_o_cambia_la_modalidad(conn, infantil_id):
    chicos = _categoria(conn, infantil_id, "2017-2018")
    grandes = _categoria(conn, infantil_id, "2011-2012")
    assert rol.modalidad_de_categoria(conn, chicos) == "Fut 7"  # la de la liga
    with conn:
        conn.execute("UPDATE categorias SET modalidad = 'Fut 9' WHERE id = ?", (grandes,))
    assert rol.modalidad_de_categoria(conn, grandes) == "Fut 9"


def test_rol_con_fut_7_y_fut_9_sin_empalmes(conn, torneo_id, infantil_id):
    fut7 = _categoria(conn, infantil_id, "2017-2018")
    fut9 = _categoria(conn, infantil_id, "2011-2012")
    with conn:
        conn.execute("UPDATE categorias SET modalidad = 'Fut 9' WHERE id = ?", (fut9,))
    _equipos(conn, torneo_id, fut7, 4)
    _equipos(conn, torneo_id, fut9, 4)
    horario = rol.Horario(SABADO, {5: (540, 1200)}, canchas=("1", "2", rol.CANCHA_FUT_11))
    creados, _ = rol.generar(conn, torneo_id, [fut7, fut9], horario)
    assert creados == 12
    partidos = conn.execute("SELECT * FROM partidos WHERE fecha IS NOT NULL").fetchall()
    for p in partidos:
        esperado = {rol.CANCHA_FUT_11} if p["categoria_id"] == fut9 else {"1", "2"}
        assert p["cancha"] in esperado
    for a in partidos:
        for b in partidos:
            if a["id"] < b["id"] and a["fecha"] == b["fecha"]:
                assert not rol.se_empalman(
                    rol.a_minutos(a["hora"]), a["minutos"], a["cancha"],
                    rol.a_minutos(b["hora"]), b["minutos"], b["cancha"],
                ), (dict(a), dict(b))


def test_sin_la_cancha_que_pide_la_modalidad_avisa(conn, torneo_id, infantil_id):
    fut9 = _categoria(conn, infantil_id, "2011-2012")
    with conn:
        conn.execute("UPDATE categorias SET modalidad = 'Fut 9' WHERE id = ?", (fut9,))
    _equipos(conn, torneo_id, fut9, 2)
    with pytest.raises(ValueError, match="juega Fut 9 y necesita la cancha completa"):
        rol.generar(conn, torneo_id, [fut9], rol.Horario(SABADO, {5: (540, 1200)}, canchas=("1", "2")))


def test_dialogo_de_categoria_guarda_la_modalidad(app, conn, infantil_id, monkeypatch):
    pagina = ui_ligas.PaginaLigas(conn)
    tabla = pagina.tabla_ligas
    tabla.selectRow(next(r for r in range(tabla.rowCount()) if tabla.item(r, 0).text() == "Infantil"))

    def llenar(dialogo):
        dialogo.nombre.setText("2007-2008")
        dialogo._completar_desde_nombre()
        dialogo.modalidad.setCurrentIndex(dialogo.modalidad.findData("Fut 9"))
        return True

    monkeypatch.setattr(ui_ligas.DialogoCategoria, "exec", llenar)
    pagina.nueva_categoria()
    assert conn.execute("SELECT modalidad FROM categorias WHERE nombre = '2007-2008'").fetchone()[0] == "Fut 9"
    fila = next(r for r in range(pagina.tabla_categorias.rowCount())
                if pagina.tabla_categorias.item(r, 0).text() == "2007-2008")
    assert pagina.tabla_categorias.item(fila, 2).text() == "Fut 9"
    otra = next(r for r in range(pagina.tabla_categorias.rowCount())
                if pagina.tabla_categorias.item(r, 0).text() == "2015-2016")
    assert pagina.tabla_categorias.item(otra, 2).text() == "Fut 7"  # hereda la de la liga
    pagina.deleteLater()


def test_partido_a_mano_ofrece_las_canchas_de_su_categoria(app, conn, torneo_id, infantil_id):
    fut7 = _categoria(conn, infantil_id, "2017-2018")
    fut9 = _categoria(conn, infantil_id, "2011-2012")
    with conn:
        conn.execute("UPDATE categorias SET modalidad = 'Fut 9' WHERE id = ?", (fut9,))
    categorias = conn.execute("SELECT * FROM categorias WHERE id IN (?, ?)", (fut7, fut9)).fetchall()
    dialogo = ui_rol.DialogoPartido(None, conn, torneo_id, "Fut 7", categorias, categoria_id=fut7)
    assert [dialogo.cancha.itemData(i) for i in range(dialogo.cancha.count())] == ["1", "2"]
    dialogo.categoria.setCurrentIndex(dialogo.categoria.findData(fut9))
    assert [dialogo.cancha.itemText(i) for i in range(dialogo.cancha.count())] == ["Cancha completa"]
    assert dialogo.modalidad.text() == "Esta categoría juega Fut 9."


def test_base_anterior_recibe_la_columna(tmp_path):
    ruta = tmp_path / "vieja.db"
    vieja = db.conectar(ruta)
    vieja.execute("ALTER TABLE categorias DROP COLUMN modalidad")
    vieja.commit()
    vieja.close()
    conn = db.conectar(ruta)
    assert {r["modalidad"] for r in conn.execute("SELECT modalidad FROM categorias")} == {""}
    conn.close()
