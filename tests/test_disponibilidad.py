import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections import Counter
from datetime import date

import pytest
from PySide6.QtCore import QDate, QTime

from dep_leon import db, rol, updater
from dep_leon.ui import pagina_equipos as ui_equipos
from dep_leon.ui import pagina_rol as ui_rol
from dep_leon.ui.ventana import Ventana

VIERNES = date(2026, 11, 6)
SABADO = date(2026, 11, 7)
VIE, SAB = 4, 5
# Viernes 16:00-19:00 y sábado 9:00-14:00.
HORARIO = rol.Horario(VIERNES, {VIE: (960, 1140), SAB: (540, 840)})


@pytest.fixture
def categoria(conn, infantil_id):
    return conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2015-2016'", (infantil_id,)
    ).fetchone()["id"]


def crear_equipos(conn, torneo_id, categoria, *nombres):
    with conn:
        return [
            conn.execute(
                "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
                (torneo_id, categoria, n),
            ).lastrowid
            for n in nombres
        ]


def test_sin_restricciones_reparte_entre_los_dias():
    partidos = [(i, i + 100) for i in range(6)]
    plan, _ = rol.programar({1: [partidos]}, HORARIO, [])
    dias = Counter(p.fecha for p in plan)
    assert dias == {VIERNES: 3, SABADO: 3}


def test_el_reparto_cuenta_lo_ya_ocupado():
    ocupados = [rol.Ocupado(VIERNES, 960, 50, "1"), rol.Ocupado(VIERNES, 960, 50, "2")]
    plan, _ = rol.programar({1: [[(1, 2), (3, 4)]]}, HORARIO, ocupados)
    assert [p.fecha for p in plan] == [SABADO, SABADO]


def test_equipo_solo_sabado_nunca_juega_viernes():
    disponibilidad = {1: {SAB: (540, 840)}}
    plan, _ = rol.programar({1: [[(1, 2), (3, 4)]]}, HORARIO, [], disponibilidad)
    por_equipo = {p.local_id: p for p in plan}
    assert por_equipo[1].fecha == SABADO
    assert por_equipo[3].fecha == VIERNES  # el otro partido se reparte al otro día


def test_respeta_las_horas_del_equipo_incluyendo_el_final_del_partido():
    # Puede el sábado de 10:00 a 11:00: un partido de 50 minutos solo cabe a las 10:30 o antes.
    disponibilidad = {1: {SAB: (600, 660)}}
    horario = rol.Horario(SABADO, {SAB: (540, 840)}, canchas=("1",))
    plan, _ = rol.programar({1: [[(1, 2)]]}, horario, [], disponibilidad)
    # Horarios del día: 9:00, 9:50, 10:40...; ninguno cabe entre 10:00 y 11:00 completo.
    assert plan[0].fecha is None


def test_hora_exacta_dentro_del_rango():
    disponibilidad = {1: {SAB: (590, 640)}}  # 9:50 a 10:40
    horario = rol.Horario(SABADO, {SAB: (540, 840)}, canchas=("1",))
    plan, _ = rol.programar({1: [[(1, 2)]]}, horario, [], disponibilidad)
    assert rol.a_hora(plan[0].hora) == "09:50"


def test_ambos_equipos_deben_poder():
    disponibilidad = {1: {VIE: (960, 1140)}, 2: {VIE: (960, 1010), SAB: (540, 840)}}
    plan, _ = rol.programar({1: [[(1, 2)]]}, HORARIO, [], disponibilidad)
    assert (plan[0].fecha, rol.a_hora(plan[0].hora)) == (VIERNES, "16:00")


def test_si_no_coinciden_queda_sin_fecha_y_no_rompe_a_los_demas():
    disponibilidad = {1: {VIE: (960, 1140)}, 2: {SAB: (540, 840)}}
    plan, _ = rol.programar({1: [[(1, 2), (3, 4)]]}, HORARIO, [], disponibilidad)
    sin_fecha = [p for p in plan if p.fecha is None]
    assert [(p.local_id, p.visitante_id) for p in sin_fecha] == [(1, 2)]
    assert len(plan) == 2


def test_lugar_lleno_esta_semana_pasa_a_la_siguiente():
    # El equipo 1 solo puede a una hora, y esa semana ya está ocupada.
    disponibilidad = {1: {SAB: (540, 590)}}
    horario = rol.Horario(SABADO, {SAB: (540, 840)}, canchas=("1",))
    ocupados = [rol.Ocupado(SABADO, 540, 50, "1")]
    plan, avisos = rol.programar({1: [[(1, 2)]]}, horario, ocupados, disponibilidad)
    assert plan[0].fecha == date(2026, 11, 14)
    assert avisos == []


def test_generar_guarda_sin_fecha_y_avisa_con_nombres(conn, torneo_id, categoria):
    a, b = crear_equipos(conn, torneo_id, categoria, "Pegasos", "Buitres")
    rol.guardar_disponibilidad(conn, a, {VIE: (960, 1140)})
    rol.guardar_disponibilidad(conn, b, {SAB: (540, 840)})
    creados, avisos = rol.generar(conn, torneo_id, [categoria], HORARIO)
    assert creados == 1
    assert "no coinciden" in avisos[0]
    assert "Pegasos" in avisos[0] and "Buitres" in avisos[0]
    partido = conn.execute("SELECT * FROM partidos").fetchone()
    assert (partido["fecha"], partido["hora"], partido["cancha"], partido["estado"]) == (
        None, None, None, rol.POR_PROGRAMAR,
    )


def test_generar_respeta_disponibilidad_del_torneo(conn, torneo_id, categoria):
    a, b, c, d = crear_equipos(conn, torneo_id, categoria, "A", "B", "C", "D")
    rol.guardar_disponibilidad(conn, a, {SAB: (540, 840)})
    rol.generar(conn, torneo_id, [categoria], HORARIO)
    jugados_por_a = conn.execute(
        "SELECT fecha FROM partidos WHERE local_id = ? OR visitante_id = ?", (a, a)
    ).fetchall()
    assert len(jugados_por_a) == 3
    assert all(date.fromisoformat(f["fecha"]).weekday() == SAB for f in jugados_por_a)


def test_guardar_leer_y_resumir(conn, torneo_id, categoria):
    a, = crear_equipos(conn, torneo_id, categoria, "A")
    assert rol.disponibilidad_de_equipo(conn, a) == {}
    assert rol.resumen_disponibilidad({}) == "Siempre"
    rol.guardar_disponibilidad(conn, a, {SAB: (540, 840), VIE: (960, 1140)})
    dias = rol.disponibilidad_de_equipo(conn, a)
    assert dias == {SAB: (540, 840), VIE: (960, 1140)}
    assert rol.resumen_disponibilidad(dias) == "Vie, Sáb"
    with pytest.raises(ValueError):
        rol.guardar_disponibilidad(conn, a, {SAB: (840, 540)})
    assert rol.disponibilidad_de_equipo(conn, a) == dias  # el error no borró nada
    rol.guardar_disponibilidad(conn, a, {})
    assert rol.disponibilidad_de_equipo(conn, a) == {}


def test_equipos_no_disponibles(conn, torneo_id, categoria):
    a, b = crear_equipos(conn, torneo_id, categoria, "A", "B")
    rol.guardar_disponibilidad(conn, a, {SAB: (540, 840)})
    assert rol.equipos_no_disponibles(conn, VIERNES, 960, 50, [a, b]) == ["A"]
    assert rol.equipos_no_disponibles(conn, SABADO, 540, 50, [a, b]) == []


def test_borrar_equipo_borra_su_disponibilidad(conn, torneo_id, categoria):
    a, = crear_equipos(conn, torneo_id, categoria, "A")
    rol.guardar_disponibilidad(conn, a, {SAB: (540, 840)})
    with conn:
        conn.execute("DELETE FROM equipos WHERE id = ?", (a,))
    assert conn.execute("SELECT COUNT(*) FROM disponibilidad").fetchone()[0] == 0


def test_respaldo_anterior_recibe_la_tabla(conn, tmp_path):
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    with conn:
        conn.execute("DROP TABLE disponibilidad")
    viejo = tmp_path / "v.zip"
    db.respaldar(conn, viejo, fotos)
    db.restaurar(conn, viejo, fotos)
    assert conn.execute("SELECT COUNT(*) FROM disponibilidad").fetchone()[0] == 0


# --- Pantallas ---


@pytest.fixture
def ventana(app, conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    resultado = Ventana(conn)
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


def test_dialogo_disponibilidad(ventana):
    dialogo = ui_equipos.DialogoDisponibilidad(ventana, "A", {})
    assert dialogo.siempre.isChecked() and dialogo.valores() == {}
    assert not dialogo.filas[0][1].isEnabled()

    dialogo.siempre.setChecked(False)
    assert dialogo.filas[VIE][1].isEnabled() and not dialogo.filas[VIE][2].isEnabled()
    errores = []
    original = ui_equipos.error
    ui_equipos.error = lambda _, m: errores.append(m)
    try:
        dialogo._aceptar()
        assert "al menos un día" in dialogo.aviso.text() and dialogo.result() == 0

        dialogo.filas[VIE][1].setChecked(True)
        dialogo.filas[VIE][2].setTime(QTime(16, 0))
        dialogo.filas[VIE][3].setTime(QTime(15, 0))
        dialogo._aceptar()
        assert "menor" in dialogo.aviso.text() and dialogo.result() == 0

        dialogo.filas[VIE][3].setTime(QTime(19, 0))
        dialogo._aceptar()
        assert dialogo.result() == 1
        assert dialogo.valores() == {VIE: (960, 1140)}
    finally:
        ui_equipos.error = original


def test_dialogo_precarga_lo_guardado(ventana):
    dialogo = ui_equipos.DialogoDisponibilidad(ventana, "A", {SAB: (600, 720)})
    assert not dialogo.siempre.isChecked()
    assert dialogo.filas[SAB][1].isChecked()
    assert dialogo.valores() == {SAB: (600, 720)}


def test_pagina_equipos_edita_y_muestra_disponibilidad(ventana, conn, torneo_id, categoria, monkeypatch):
    a, = crear_equipos(conn, torneo_id, categoria, "Pegasos")
    pagina = ventana.equipos
    pagina.refrescar()
    pagina.tabla_equipos.selectRow(0)
    assert pagina.datos_equipo.valores["disponible"].text() == "Siempre"

    def elegir(dialogo):
        dialogo.siempre.setChecked(False)
        dialogo.filas[SAB][1].setChecked(True)
        return True

    monkeypatch.setattr(ui_equipos.DialogoDisponibilidad, "exec", elegir)
    pagina.editar_disponibilidad()
    assert rol.disponibilidad_de_equipo(conn, a) == {SAB: (480, 1320)}
    assert pagina.datos_equipo.valores["disponible"].text() == "Sáb"


def test_formulario_de_partido_avisa_y_permite_guardar_de_todos_modos(ventana, conn, torneo_id, categoria, monkeypatch):
    a, b = crear_equipos(conn, torneo_id, categoria, "Pegasos", "Buitres")
    rol.guardar_disponibilidad(conn, a, {SAB: (540, 840)})
    categorias = conn.execute("SELECT * FROM categorias WHERE id = ?", (categoria,)).fetchall()
    dialogo = ui_rol.DialogoPartido(ventana, conn, torneo_id, "Fut 7", categorias, categoria_id=categoria)
    dialogo.local.setCurrentIndex(dialogo.local.findData(a))
    dialogo.visitante.setCurrentIndex(dialogo.visitante.findData(b))
    dialogo.fecha.setDate(QDate(2026, 11, 6))  # viernes
    dialogo.hora.setTime(QTime(16, 0))

    preguntas = []
    monkeypatch.setattr(ui_rol, "confirmar", lambda _, m: preguntas.append(m) or False)
    dialogo._aceptar()
    assert "Pegasos no tiene disponibilidad" in preguntas[0] and dialogo.result() == 0

    monkeypatch.setattr(ui_rol, "confirmar", lambda _, m: True)
    dialogo._aceptar()
    assert dialogo.result() == 1
