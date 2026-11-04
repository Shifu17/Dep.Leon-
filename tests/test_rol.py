import random
from collections import Counter
from datetime import date, timedelta
from itertools import combinations

import pytest

from dep_leon import db, rol

SABADO = date(2026, 10, 31)
VIERNES = date(2026, 10, 30)
HORARIO_SABADO = rol.Horario(SABADO, {5: (540, 800)})  # 9:00 a 13:20


@pytest.mark.parametrize("total", range(2, 15))
def test_todos_contra_todos(total):
    equipos = list(range(total))
    jornadas = rol.jornadas_todos_contra_todos(equipos)

    assert len(jornadas) == (total - 1 if total % 2 == 0 else total)
    parejas = [frozenset(p) for j in jornadas for p in j]
    assert Counter(parejas) == Counter(frozenset(p) for p in combinations(equipos, 2))
    for jornada in jornadas:
        presentes = [e for p in jornada for e in p]
        assert len(presentes) == len(set(presentes))
    locales = Counter(p[0] for j in jornadas for p in j)
    visitas = Counter(p[1] for j in jornadas for p in j)
    assert all(abs(locales[e] - visitas[e]) <= 1 for e in equipos)


def test_impar_descansa_un_equipo_por_jornada_y_una_vez_cada_uno():
    equipos = list(range(5))
    jornadas = rol.jornadas_todos_contra_todos(equipos)
    descansos = [set(equipos) - {e for p in j for e in p} for j in jornadas]
    assert all(len(d) == 1 for d in descansos)
    assert Counter(next(iter(d)) for d in descansos) == Counter(equipos)


def test_ida_y_vuelta_invierte_localia():
    ida_y_vuelta = rol.jornadas_todos_contra_todos([1, 2, 3, 4], ida_y_vuelta=True)
    assert len(ida_y_vuelta) == 6
    equipos = [1, 2, 3, 4]
    esperados = Counter((a, b) for a in equipos for b in equipos if a != b)
    assert Counter(p for j in ida_y_vuelta for p in j) == esperados


def test_menos_de_dos_equipos_no_genera():
    assert rol.jornadas_todos_contra_todos([1]) == []


def test_horario_como_la_hoja_cada_50_minutos_y_dos_canchas():
    jornadas = {1: [[(i, i + 100) for i in range(10)]]}
    plan, avisos = rol.programar(jornadas, HORARIO_SABADO, [])
    assert avisos == []
    espacios = {(rol.a_hora(p.hora), p.cancha) for p in plan}
    assert espacios == {
        (h, c) for h in ("09:00", "09:50", "10:40", "11:30", "12:20") for c in ("1", "2")
    }
    assert {p.fecha for p in plan} == {SABADO}


def test_cada_jornada_va_en_su_semana_y_respeta_el_dia():
    jornadas = {1: [[(1, 2)], [(3, 4)], [(5, 6)]]}
    plan, _ = rol.programar(jornadas, HORARIO_SABADO, [])
    assert [p.fecha for p in plan] == [SABADO + timedelta(days=7 * i) for i in range(3)]
    assert all(p.fecha.weekday() == 5 for p in plan)


def test_viernes_y_sabado_con_horarios_distintos():
    horario = rol.Horario(VIERNES, {4: (1020, 1070), 5: (540, 590)}, canchas=("1",))
    plan, _ = rol.programar({1: [[(1, 2), (3, 4)]]}, horario, [])
    assert [(p.fecha, rol.a_hora(p.hora)) for p in plan] == [
        (VIERNES, "17:00"), (SABADO, "09:00"),
    ]


def test_no_programa_antes_de_la_fecha_de_inicio():
    horario = rol.Horario(SABADO, {4: (540, 800), 5: (540, 800)})
    plan, _ = rol.programar({1: [[(1, 2)]]}, horario, [])
    assert plan[0].fecha == SABADO


def test_jornada_que_no_cabe_pasa_a_la_semana_siguiente_con_aviso():
    horario = rol.Horario(SABADO, {5: (540, 590)}, canchas=("1",))
    plan, avisos = rol.programar({1: [[(1, 2), (3, 4)], [(5, 6)]]}, horario, [])
    assert [p.fecha for p in plan] == [SABADO, SABADO + timedelta(7), SABADO + timedelta(14)]
    assert "jornada 1" in avisos[0]


@pytest.mark.parametrize(
    "cancha_ocupada, cancha_nueva, empalma",
    [("1", "1", True), ("1", "2", False), ("11", "1", True), ("2", "11", True), ("11", "11", True)],
)
def test_fut_11_ocupa_el_terreno_completo(cancha_ocupada, cancha_nueva, empalma):
    assert rol.se_empalman(540, 50, cancha_ocupada, 560, 50, cancha_nueva) is empalma
    assert rol.se_empalman(540, 50, cancha_ocupada, 590, 50, cancha_nueva) is False


def test_programar_evita_lo_ocupado():
    ocupado = [rol.Ocupado(SABADO, 540, 50, "1")]
    plan, _ = rol.programar({1: [[(1, 2)]]}, HORARIO_SABADO, ocupado)
    assert (rol.a_hora(plan[0].hora), plan[0].cancha) == ("09:00", "2")


def test_sin_espacio_da_error_claro_sin_ciclo_infinito():
    horario = rol.Horario(SABADO, {5: (540, 560)})
    with pytest.raises(ValueError, match="no caben"):
        rol.programar({1: [[(1, 2)]]}, horario, [])


def test_dias_de_texto():
    assert rol.dias_de_texto("Viernes y sábado") == [4, 5]
    assert rol.dias_de_texto("MIERCOLES") == [2]
    assert rol.dias_de_texto("") == []


def test_fecha_larga():
    assert rol.fecha_larga(SABADO) == "Sábado 31 de octubre del 2026"


# --- Con base de datos ---


@pytest.fixture
def categorias(conn, infantil_id):
    return {
        c["nombre"]: c["id"]
        for c in conn.execute("SELECT * FROM categorias WHERE liga_id = ?", (infantil_id,))
    }


def crear_equipos(conn, torneo_id, categoria_id, total, prefijo="E"):
    with conn:
        return [
            conn.execute(
                "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
                (torneo_id, categoria_id, f"{prefijo}{i}"),
            ).lastrowid
            for i in range(total)
        ]


def partidos(conn):
    return conn.execute("SELECT * FROM partidos").fetchall()


def test_generar_varias_categorias_sin_empalmes(conn, torneo_id, categorias):
    crear_equipos(conn, torneo_id, categorias["2015-2016"], 6)
    crear_equipos(conn, torneo_id, categorias["2017-2018"], 5)
    creados, avisos = rol.generar(
        conn, torneo_id, [categorias["2015-2016"], categorias["2017-2018"]], HORARIO_SABADO,
        azar=random.Random(1),
    )
    assert creados == 15 + 10 and avisos == []
    filas = partidos(conn)
    espacios = Counter((f["fecha"], f["hora"], f["cancha"]) for f in filas)
    assert max(espacios.values()) == 1
    por_fecha = Counter()
    for f in filas:
        for equipo in (f["local_id"], f["visitante_id"]):
            por_fecha[(f["fecha"], equipo)] += 1
    assert max(por_fecha.values()) == 1


def test_generar_respeta_otras_ligas_en_el_mismo_terreno(conn, torneo_id, categorias):
    """Un Fut 11 ya programado bloquea las canchas de Fut 7 a esa hora."""
    equipos = crear_equipos(conn, torneo_id, categorias["2015-2016"], 2, "F")
    with conn:
        conn.execute(
            "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, fecha, "
            "hora, minutos, cancha, estado) VALUES (?, ?, 1, ?, ?, ?, '09:00', 50, '11', ?)",
            (torneo_id, categorias["2015-2016"], equipos[0], equipos[1], SABADO.isoformat(), rol.PROGRAMADO),
        )
    crear_equipos(conn, torneo_id, categorias["2017-2018"], 2)
    rol.generar(conn, torneo_id, [categorias["2017-2018"]], HORARIO_SABADO)
    nuevo = conn.execute(
        "SELECT * FROM partidos WHERE categoria_id = ?", (categorias["2017-2018"],)
    ).fetchone()
    assert nuevo["hora"] == "09:50"


def test_regenerar_reemplaza_solo_esa_categoria(conn, torneo_id, categorias):
    crear_equipos(conn, torneo_id, categorias["2015-2016"], 4, "A")
    crear_equipos(conn, torneo_id, categorias["2017-2018"], 2, "B")
    todas = [categorias["2015-2016"], categorias["2017-2018"]]
    rol.generar(conn, torneo_id, todas, HORARIO_SABADO)
    assert len(partidos(conn)) == 7
    rol.generar(conn, torneo_id, [categorias["2015-2016"]], HORARIO_SABADO)
    assert len(partidos(conn)) == 7
    assert max(Counter((f["fecha"], f["hora"], f["cancha"]) for f in partidos(conn)).values()) == 1


def test_generar_omite_categoria_con_un_equipo_y_avisa(conn, torneo_id, categorias):
    crear_equipos(conn, torneo_id, categorias["2015-2016"], 2)
    crear_equipos(conn, torneo_id, categorias["2017-2018"], 1, "S")
    creados, avisos = rol.generar(
        conn, torneo_id, [categorias["2015-2016"], categorias["2017-2018"]], HORARIO_SABADO
    )
    assert creados == 1 and "2017-2018" in avisos[0]


def test_generar_sin_equipos_da_error_y_conserva_el_rol(conn, torneo_id, categorias):
    with pytest.raises(ValueError):
        rol.generar(conn, torneo_id, [categorias["2015-2016"]], HORARIO_SABADO)


def test_si_no_cabe_conserva_el_rol_anterior(conn, torneo_id, categorias):
    crear_equipos(conn, torneo_id, categorias["2015-2016"], 2)
    rol.generar(conn, torneo_id, [categorias["2015-2016"]], HORARIO_SABADO)
    imposible = rol.Horario(SABADO, {5: (540, 550)})
    with pytest.raises(ValueError):
        rol.generar(conn, torneo_id, [categorias["2015-2016"]], imposible)
    assert len(partidos(conn)) == 1


def test_conflictos_de_cancha_y_de_equipo(conn, torneo_id, categorias):
    a, b, c, d = crear_equipos(conn, torneo_id, categorias["2015-2016"], 4)
    with conn:
        partido = conn.execute(
            "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, fecha, "
            "hora, minutos, cancha, estado) VALUES (?, ?, 1, ?, ?, ?, '09:00', 50, '1', ?)",
            (torneo_id, categorias["2015-2016"], a, b, SABADO.isoformat(), rol.PROGRAMADO),
        ).lastrowid
    assert "cancha" in rol.buscar_conflicto(conn, SABADO, 540, 50, "1", c, d)
    assert "equipo" in rol.buscar_conflicto(conn, SABADO, 540, 50, "2", a, c)
    assert rol.buscar_conflicto(conn, SABADO, 540, 50, "2", c, d) is None
    assert rol.buscar_conflicto(conn, SABADO, 590, 50, "1", a, c) is None
    assert rol.buscar_conflicto(conn, SABADO, 540, 50, "1", a, b, partido) is None


def test_posponer_libera_la_cancha(conn, torneo_id, categorias):
    a, b, c, d = crear_equipos(conn, torneo_id, categorias["2015-2016"], 4)
    with conn:
        partido = conn.execute(
            "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, fecha, "
            "hora, minutos, cancha, estado) VALUES (?, ?, 1, ?, ?, ?, '09:00', 50, '1', ?)",
            (torneo_id, categorias["2015-2016"], a, b, SABADO.isoformat(), rol.PROGRAMADO),
        ).lastrowid
    rol.posponer(conn, partido)
    fila = conn.execute("SELECT * FROM partidos").fetchone()
    assert (fila["estado"], fila["fecha"], fila["cancha"]) == (rol.POSPUESTO, None, None)
    assert rol.buscar_conflicto(conn, SABADO, 540, 50, "1", c, d) is None


def test_descansos(conn, torneo_id, categorias):
    crear_equipos(conn, torneo_id, categorias["2015-2016"], 3)
    rol.generar(conn, torneo_id, [categorias["2015-2016"]], HORARIO_SABADO)
    primera = conn.execute("SELECT MIN(fecha) FROM partidos").fetchone()[0]
    lista = rol.descansos(conn, torneo_id, primera)
    assert len(lista) == 1 and lista[0][0] == "2015-2016"


def test_configuracion_se_recuerda(conn, torneo_id):
    assert rol.configuracion_guardada(conn, torneo_id) is None
    rol.guardar_configuracion(conn, torneo_id, rol.Horario(SABADO, {5: (540, 800)}, 45, ("2",)), True)
    guardada = rol.configuracion_guardada(conn, torneo_id)
    assert guardada["dias"] == {5: (540, 800)}
    assert (guardada["minutos"], guardada["canchas"], guardada["ida_y_vuelta"]) == (45, ["2"], True)


def test_base_de_la_etapa_1_recibe_las_tablas_nuevas(tmp_path):
    ruta = tmp_path / "vieja.db"
    vieja = db.conectar(ruta)
    with vieja:
        vieja.execute("DROP TABLE partidos")
        vieja.execute("DROP TABLE config_rol")
    vieja.close()
    actualizada = db.conectar(ruta)
    assert actualizada.execute("SELECT COUNT(*) FROM partidos").fetchone()[0] == 0
    actualizada.close()


def test_restaurar_respaldo_de_la_etapa_1(conn, tmp_path, torneo_id):
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    with conn:
        conn.execute("DROP TABLE partidos")
        conn.execute("DROP TABLE config_rol")
    respaldo = tmp_path / "viejo.zip"
    db.respaldar(conn, respaldo, fotos)
    db.restaurar(conn, respaldo, fotos)
    assert conn.execute("SELECT COUNT(*) FROM partidos").fetchone()[0] == 0
