import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication

from dep_leon import db, estadisticas, resultados, rol, updater
from dep_leon.ui import pagina_equipos as ui_equipos
from dep_leon.ui import pagina_resultados as ui_resultados
from dep_leon.ui import pagina_rol as ui_rol
from dep_leon.ui.ventana import Ventana

SABADO = date(2026, 11, 7)
HORARIO = rol.Horario(SABADO, {5: (540, 800)})


@pytest.fixture
def categoria(conn, infantil_id):
    return conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2015-2016'", (infantil_id,)
    ).fetchone()["id"]


def crear_equipo(conn, torneo_id, categoria_id, nombre, jugadores=0):
    with conn:
        equipo = conn.execute(
            "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
            (torneo_id, categoria_id, nombre),
        ).lastrowid
        ids = [
            conn.execute(
                "INSERT INTO jugadores (equipo_id, nombre, fecha_nacimiento, numero) VALUES (?, ?, ?, ?)",
                (equipo, f"{nombre} {n}", "2015-05-05", n),
            ).lastrowid
            for n in range(jugadores)
        ]
    return equipo, ids


def crear_partido(conn, torneo_id, categoria_id, local, visitante, hora="09:00", jornada=1):
    with conn:
        return conn.execute(
            "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, fecha, "
            "hora, minutos, cancha, estado) VALUES (?, ?, ?, ?, ?, ?, ?, 50, '1', ?)",
            (torneo_id, categoria_id, jornada, local, visitante, SABADO.isoformat(), hora, rol.PROGRAMADO),
        ).lastrowid


@pytest.fixture
def liga4(conn, torneo_id, categoria):
    """Cuatro equipos y sus partidos, sin resultados."""
    return {n: crear_equipo(conn, torneo_id, categoria, n)[0] for n in ("A", "B", "C", "D")}


def jugar(conn, torneo_id, categoria, equipos, local, visitante, gl, gv):
    partido = crear_partido(conn, torneo_id, categoria, equipos[local], equipos[visitante])
    resultados.guardar_resultado(conn, partido, gl, gv)
    return partido


def orden(conn, torneo_id, categoria):
    return [f.nombre for f in estadisticas.tabla_posiciones(conn, torneo_id, categoria)]


def test_tabla_cuenta_todas_las_columnas(conn, torneo_id, categoria, liga4):
    jugar(conn, torneo_id, categoria, liga4, "A", "B", 2, 1)
    jugar(conn, torneo_id, categoria, liga4, "C", "A", 1, 1)
    tabla = {f.nombre: f for f in estadisticas.tabla_posiciones(conn, torneo_id, categoria)}
    a = tabla["A"]
    assert (a.pj, a.pg, a.pe, a.pp, a.gf, a.gc, a.dg, a.pts) == (2, 1, 1, 0, 3, 2, 1, 4)
    b = tabla["B"]
    assert (b.pj, b.pg, b.pe, b.pp, b.gf, b.gc, b.dg, b.pts) == (1, 0, 0, 1, 1, 2, -1, 0)
    assert tabla["D"].pj == 0


def test_desempata_por_diferencia_y_luego_goles_a_favor(conn, torneo_id, categoria, liga4):
    jugar(conn, torneo_id, categoria, liga4, "A", "D", 1, 0)
    jugar(conn, torneo_id, categoria, liga4, "B", "D", 3, 0)
    jugar(conn, torneo_id, categoria, liga4, "C", "D", 4, 1)
    # Misma cantidad de puntos: B y C tienen DG +3 pero C más goles; A queda con DG +1.
    assert orden(conn, torneo_id, categoria)[:3] == ["C", "B", "A"]


def test_empate_total_lo_define_el_duelo_directo(conn, torneo_id, categoria, liga4):
    jugar(conn, torneo_id, categoria, liga4, "B", "A", 2, 0)
    jugar(conn, torneo_id, categoria, liga4, "A", "C", 3, 0)
    jugar(conn, torneo_id, categoria, liga4, "D", "B", 2, 1)
    tabla = estadisticas.tabla_posiciones(conn, torneo_id, categoria)
    # A y B quedan idénticos (3 pts, DG +1, GF 3): B va arriba porque le ganó a A.
    a, b = (next(f for f in tabla if f.nombre == n) for n in "AB")
    assert (a.pts, a.dg, a.gf) == (b.pts, b.dg, b.gf) == (3, 1, 3)
    assert [f.nombre for f in tabla] == ["B", "A", "D", "C"]


def test_sin_diferencia_en_el_duelo_define_el_nombre(conn, torneo_id, categoria, liga4):
    jugar(conn, torneo_id, categoria, liga4, "B", "A", 1, 1)
    assert orden(conn, torneo_id, categoria) == ["A", "B", "C", "D"]


def test_reglas_de_puntos_recalculan(conn, torneo_id, categoria, liga4):
    jugar(conn, torneo_id, categoria, liga4, "A", "B", 1, 0)
    jugar(conn, torneo_id, categoria, liga4, "C", "D", 1, 1)
    resultados.guardar_reglas(conn, torneo_id, resultados.Reglas(victoria=2, empate=2, derrota=1, default_goles=5))
    tabla = {f.nombre: f.pts for f in estadisticas.tabla_posiciones(conn, torneo_id, categoria)}
    assert tabla == {"A": 2, "B": 1, "C": 2, "D": 2}


def test_goleadores_y_porteria(conn, torneo_id, categoria):
    a, (a0, a1) = crear_equipo(conn, torneo_id, categoria, "A", 2)
    b, (b0,) = crear_equipo(conn, torneo_id, categoria, "B", 1)
    uno = crear_partido(conn, torneo_id, categoria, a, b)
    dos = crear_partido(conn, torneo_id, categoria, b, a, jornada=2)
    resultados.guardar_resultado(conn, uno, 3, 1, {a0: 2, a1: 1, b0: 1})
    resultados.guardar_resultado(conn, dos, 0, 1, {a0: 1})

    anotadores = estadisticas.goleadores(conn, torneo_id, categoria)
    assert [(g["nombre"], g["equipo"], g["goles"]) for g in anotadores] == [
        ("A 0", "A", 3), ("A 1", "A", 1), ("B 0", "B", 1),
    ]
    tabla = estadisticas.tabla_posiciones(conn, torneo_id, categoria)
    assert [(f.nombre, f.gc) for f in estadisticas.menos_goleados(tabla)] == [("A", 1), ("B", 4)]


def test_corregir_resultado_reemplaza_los_goles(conn, torneo_id, categoria):
    a, (a0, a1) = crear_equipo(conn, torneo_id, categoria, "A", 2)
    b, _ = crear_equipo(conn, torneo_id, categoria, "B")
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    resultados.guardar_resultado(conn, partido, 2, 0, {a0: 2})
    resultados.guardar_resultado(conn, partido, 1, 0, {a1: 1})
    assert [g["nombre"] for g in estadisticas.goleadores(conn, torneo_id, categoria)] == ["A 1"]
    assert estadisticas.tabla_posiciones(conn, torneo_id, categoria)[0].gf == 1


@pytest.mark.parametrize(
    "gl, gv, goles, mensaje",
    [
        (1, 0, "dos", "más goles"),
        (-1, 0, None, "negativo"),
        (1, 0, "ajeno", "no pertenece"),
    ],
)
def test_datos_invalidos_no_cambian_nada(conn, torneo_id, categoria, gl, gv, goles, mensaje):
    a, (a0,) = crear_equipo(conn, torneo_id, categoria, "A", 1)
    b, _ = crear_equipo(conn, torneo_id, categoria, "B")
    _, (ajeno,) = crear_equipo(conn, torneo_id, categoria, "C", 1)
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    valor = {"dos": {a0: 2}, "ajeno": {ajeno: 1}, None: None}[goles]
    with pytest.raises(ValueError, match=mensaje):
        resultados.guardar_resultado(conn, partido, gl, gv, valor)
    assert conn.execute("SELECT COUNT(*) FROM resultados").fetchone()[0] == 0
    assert conn.execute("SELECT estado FROM partidos").fetchone()[0] == rol.PROGRAMADO


def test_goles_sin_jugador_son_validos(conn, torneo_id, categoria):
    a, (a0,) = crear_equipo(conn, torneo_id, categoria, "A", 1)
    b, _ = crear_equipo(conn, torneo_id, categoria, "B")
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    resultados.guardar_resultado(conn, partido, 3, 0, {a0: 1})
    assert estadisticas.goleadores(conn, torneo_id, categoria)[0]["goles"] == 1


@pytest.mark.parametrize("ausente_es_local, marcador", [(True, (0, 3)), (False, (3, 0))])
def test_default_da_marcador_y_guarda_quien_paga(conn, torneo_id, categoria, ausente_es_local, marcador):
    a, _ = crear_equipo(conn, torneo_id, categoria, "A")
    b, _ = crear_equipo(conn, torneo_id, categoria, "B")
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    ausente = a if ausente_es_local else b
    resultados.dar_default(conn, partido, ausente, resultados.PAGA_AMBOS)
    fila = conn.execute("SELECT * FROM resultados").fetchone()
    assert (fila["goles_local"], fila["goles_visitante"]) == marcador
    assert (fila["ausente_id"], fila["paga"]) == (ausente, resultados.PAGA_AMBOS)
    assert conn.execute("SELECT estado FROM partidos").fetchone()[0] == rol.DEFAULT
    presente = "B" if ausente_es_local else "A"
    assert estadisticas.tabla_posiciones(conn, torneo_id, categoria)[0].nombre == presente


def test_default_usa_las_reglas_y_valida(conn, torneo_id, categoria):
    a, _ = crear_equipo(conn, torneo_id, categoria, "A")
    b, _ = crear_equipo(conn, torneo_id, categoria, "B")
    c, _ = crear_equipo(conn, torneo_id, categoria, "C")
    resultados.guardar_reglas(conn, torneo_id, resultados.Reglas(default_goles=5))
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    with pytest.raises(ValueError):
        resultados.dar_default(conn, partido, c, resultados.PAGA_AUSENTE)
    with pytest.raises(ValueError):
        resultados.dar_default(conn, partido, a, "nadie")
    resultados.dar_default(conn, partido, a, resultados.PAGA_AUSENTE)
    assert conn.execute("SELECT goles_visitante FROM resultados").fetchone()[0] == 5


def test_borrar_resultado_devuelve_a_programado(conn, torneo_id, categoria):
    a, (a0,) = crear_equipo(conn, torneo_id, categoria, "A", 1)
    b, _ = crear_equipo(conn, torneo_id, categoria, "B")
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    resultados.guardar_resultado(conn, partido, 1, 0, {a0: 1})
    resultados.borrar_resultado(conn, partido)
    assert conn.execute("SELECT estado FROM partidos").fetchone()[0] == rol.PROGRAMADO
    assert conn.execute("SELECT COUNT(*) FROM goles").fetchone()[0] == 0
    assert estadisticas.tabla_posiciones(conn, torneo_id, categoria)[0].pj == 0


def test_pospuesto_no_admite_resultado_ni_con_resultado_se_pospone(conn, torneo_id, categoria):
    a, _ = crear_equipo(conn, torneo_id, categoria, "A")
    b, _ = crear_equipo(conn, torneo_id, categoria, "B")
    uno = crear_partido(conn, torneo_id, categoria, a, b)
    rol.posponer(conn, uno)
    with pytest.raises(ValueError, match="pospuesto"):
        resultados.guardar_resultado(conn, uno, 1, 0)
    with pytest.raises(ValueError, match="pospuesto"):
        resultados.dar_default(conn, uno, a, resultados.PAGA_AUSENTE)
    dos = crear_partido(conn, torneo_id, categoria, a, b, jornada=2)
    resultados.guardar_resultado(conn, dos, 1, 0)
    with pytest.raises(ValueError, match="resultado"):
        rol.posponer(conn, dos)


def test_no_se_regenera_rol_con_resultados(conn, torneo_id, categoria):
    crear_equipo(conn, torneo_id, categoria, "A")
    crear_equipo(conn, torneo_id, categoria, "B")
    rol.generar(conn, torneo_id, [categoria], HORARIO)
    partido = conn.execute("SELECT id FROM partidos").fetchone()["id"]
    resultados.guardar_resultado(conn, partido, 1, 0)
    with pytest.raises(ValueError, match="resultados"):
        rol.generar(conn, torneo_id, [categoria], HORARIO)
    assert conn.execute("SELECT COUNT(*) FROM resultados").fetchone()[0] == 1


def test_lideres_solo_categorias_con_resultados(conn, torneo_id, categoria, infantil_id):
    a, (a0,) = crear_equipo(conn, torneo_id, categoria, "A", 1)
    b, _ = crear_equipo(conn, torneo_id, categoria, "B")
    assert estadisticas.lideres(conn) == []
    resultados.guardar_resultado(conn, crear_partido(conn, torneo_id, categoria, a, b), 2, 0, {a0: 2})
    lider = estadisticas.lideres(conn, infantil_id)[0]
    assert (lider.categoria, lider.equipo, lider.puntos, lider.goleador, lider.goles) == (
        "2015-2016", "A", 3, "A 0", 2,
    )
    otra = conn.execute("SELECT id FROM ligas WHERE nombre = 'Femenil'").fetchone()["id"]
    assert estadisticas.lideres(conn, otra) == []


def test_respaldo_anterior_recibe_tablas_de_resultados(conn, tmp_path):
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    with conn:
        for tabla in ("goles", "resultados", "reglas_torneo"):
            conn.execute(f"DROP TABLE {tabla}")
    respaldo = tmp_path / "viejo.zip"
    db.respaldar(conn, respaldo, fotos)
    db.restaurar(conn, respaldo, fotos)
    assert conn.execute("SELECT COUNT(*) FROM resultados").fetchone()[0] == 0


# --- Pantallas ---


@pytest.fixture
def ventana(conn, monkeypatch, tmp_path):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    resultado = Ventana(conn)
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


@pytest.fixture
def partido_ui(conn, torneo_id, categoria):
    a, (a0, a1) = crear_equipo(conn, torneo_id, categoria, "Pegasos", 2)
    b, (b0,) = crear_equipo(conn, torneo_id, categoria, "Buitres", 1)
    return crear_partido(conn, torneo_id, categoria, a, b), a, b, a0, b0


def test_flujo_capturar_y_ver_en_estadisticas(ventana, conn, partido_ui, monkeypatch):
    partido, _, _, a0, b0 = partido_ui
    pagina = ventana.resultados
    pagina.filtros.refrescar()
    assert pagina.tabla.rowCount() == 1
    pagina.tabla.selectRow(0)

    fila = pagina._partido()
    dialogo = ui_resultados.DialogoResultado(pagina, conn, fila, fila["local"], fila["visitante"])
    dialogo.marcador_local.setValue(2)
    dialogo.marcador_visitante.setValue(1)
    dialogo.goles[a0].setValue(2)
    dialogo.goles[b0].setValue(1)
    dialogo._aceptar()
    assert dialogo.result() == 1

    pagina.refrescar_partidos()
    assert pagina.tabla.rowCount() == 0  # ya no está por capturar
    pagina.ver.setCurrentText(ui_resultados.VER_CAPTURADOS)
    assert pagina.tabla.item(0, 3).text() == "2 - 1"

    estad = ventana.estadisticas
    estad.filtros.refrescar()
    assert estad.filtros.categoria.currentText() == "2015-2016"
    assert estad.clasificacion.item(0, 1).text() == "Pegasos"
    assert estad.clasificacion.item(0, 9).text() == "3"
    assert estad.clasificacion.item(0, 8).text() == "+1"
    assert estad.goleadores.item(0, 3).text() == "2"
    assert estad.porteria.item(0, 3).text() == "1"


def test_dialogo_resultado_precarga_lo_guardado(ventana, conn, partido_ui):
    partido, _, _, a0, _ = partido_ui
    resultados.guardar_resultado(conn, partido, 3, 0, {a0: 2})
    fila = conn.execute("SELECT * FROM partidos").fetchone()
    dialogo = ui_resultados.DialogoResultado(ventana, conn, fila, "A", "B")
    assert dialogo.marcador_local.value() == 3 and dialogo.goles[a0].value() == 2


def test_dialogo_resultado_muestra_error_si_no_cuadra(ventana, conn, partido_ui, monkeypatch):
    _, _, _, a0, _ = partido_ui
    errores = []
    monkeypatch.setattr(ui_resultados, "error", lambda _, m: errores.append(m))
    fila = conn.execute("SELECT * FROM partidos").fetchone()
    dialogo = ui_resultados.DialogoResultado(ventana, conn, fila, "A", "B")
    dialogo.goles[a0].setValue(1)
    dialogo._aceptar()
    assert "más goles" in errores[0] and dialogo.result() == 0


@pytest.mark.parametrize("posponer", [True, False])
def test_no_se_presento_posponer_o_default(ventana, conn, partido_ui, monkeypatch, posponer):
    partido, a, b, *_ = partido_ui
    pagina = ventana.resultados
    pagina.filtros.refrescar()
    pagina.tabla.selectRow(0)

    def exec_(dialogo):
        dialogo.ausente.setCurrentIndex(1)
        dialogo.paga.setCurrentIndex(dialogo.paga.findData(resultados.PAGA_PRESENTE))
        if posponer:
            dialogo.posponer.setChecked(True)
        return True

    monkeypatch.setattr(ui_resultados.DialogoNoSePresento, "exec", exec_)
    pagina.no_se_presento()
    fila = conn.execute("SELECT * FROM partidos").fetchone()
    if posponer:
        assert fila["estado"] == rol.POSPUESTO
        assert conn.execute("SELECT COUNT(*) FROM resultados").fetchone()[0] == 0
    else:
        assert fila["estado"] == rol.DEFAULT
        r = conn.execute("SELECT * FROM resultados").fetchone()
        assert (r["ausente_id"], r["paga"], r["goles_local"]) == (b, resultados.PAGA_PRESENTE, 3)


def test_editar_horario_conserva_el_resultado(ventana, conn, partido_ui, monkeypatch):
    partido, *_ = partido_ui
    resultados.guardar_resultado(conn, partido, 1, 0)
    monkeypatch.setattr(ui_rol.DialogoPartido, "exec", lambda self: True)
    pagina = ventana.rol
    pagina.refrescar()
    pagina.fecha.setCurrentIndex(0)
    pagina.tabla.selectRow(0)
    pagina.editar()
    assert conn.execute("SELECT estado FROM partidos").fetchone()[0] == rol.JUGADO
    assert conn.execute("SELECT COUNT(*) FROM resultados").fetchone()[0] == 1


def test_editar_partido_con_resultado_no_deja_cambiar_equipos(ventana, conn, partido_ui):
    partido, *_ = partido_ui
    resultados.guardar_resultado(conn, partido, 1, 0)
    fila = conn.execute("SELECT * FROM partidos").fetchone()
    categorias = conn.execute("SELECT * FROM categorias").fetchall()
    dialogo = ui_rol.DialogoPartido(ventana, conn, fila["torneo_id"], "Fut 7", categorias, fila)
    assert not dialogo.local.isEnabled() and not dialogo.visitante.isEnabled()


def test_jugador_con_goles_no_se_borra(ventana, conn, partido_ui, monkeypatch):
    partido, *_, a0, _ = partido_ui
    resultados.guardar_resultado(conn, partido, 1, 0, {a0: 1})
    errores = []
    monkeypatch.setattr(ui_equipos, "error", lambda _, m: errores.append(m))
    monkeypatch.setattr(ui_equipos, "id_seleccionado", lambda _: a0)
    ventana.equipos.borrar_jugador()
    assert "goles" in errores[0]
    assert conn.execute("SELECT 1 FROM jugadores WHERE id = ?", (a0,)).fetchone()


def test_estadisticas_sin_datos_no_falla(ventana):
    ventana.estadisticas.filtros.refrescar()
    assert ventana.estadisticas.clasificacion.rowCount() == 0


def test_no_se_presento_no_borra_un_resultado_existente(ventana, conn, partido_ui, monkeypatch):
    partido, *_ = partido_ui
    resultados.guardar_resultado(conn, partido, 2, 1)
    errores = []
    monkeypatch.setattr(ui_resultados, "error", lambda _, m: errores.append(m))
    pagina = ventana.resultados
    pagina.filtros.refrescar()
    pagina.ver.setCurrentText(ui_resultados.VER_CAPTURADOS)
    pagina.tabla.selectRow(0)
    pagina.no_se_presento()
    assert "ya tiene resultado" in errores[0]
    assert conn.execute("SELECT goles_local FROM resultados").fetchone()[0] == 2
