import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date

import pytest
from PySide6.QtWidgets import QPushButton

from dep_leon import cobros, db, estadisticas, liguilla, resultados, rol, updater
from dep_leon.ui import pagina_liguilla as ui_liguilla
from dep_leon.ui import pagina_resultados as ui_resultados
from dep_leon.ui import pagina_rol as ui_rol
from dep_leon.ui.ventana import Ventana

SABADO = date(2026, 11, 7)


@pytest.fixture
def categoria(conn, infantil_id):
    return conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2015-2016'", (infantil_id,)
    ).fetchone()["id"]


@pytest.fixture
def equipos(conn, torneo_id, categoria):
    """Ocho equipos cuya tabla queda E1 > E2 > ... > E8, cada uno con un partido ganado de más."""
    return armar_tabla(conn, torneo_id, categoria, 8)


def armar_tabla(conn, torneo_id, categoria, total):
    with conn:
        ids = [
            conn.execute(
                "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
                (torneo_id, categoria, f"E{i}"),
            ).lastrowid
            for i in range(1, total + 1)
        ]
    # Todos contra todos, gana siempre el de mejor número: la tabla queda en ese orden.
    jornada = 1
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            partido = crear_partido(conn, torneo_id, categoria, a, b, jornada)
            resultados.guardar_resultado(conn, partido, 1, 0)
            jornada += 1
    return ids


def crear_partido(conn, torneo_id, categoria, local, visitante, jornada=1):
    with conn:
        return conn.execute(
            "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, fecha, "
            "hora, minutos, cancha, estado) VALUES (?, ?, ?, ?, ?, ?, '09:00', 50, '1', ?)",
            (torneo_id, categoria, jornada, local, visitante, SABADO.isoformat(), rol.PROGRAMADO),
        ).lastrowid


def programar(conn, partido_id, hora="10:00"):
    with conn:
        conn.execute(
            "UPDATE partidos SET fecha = ?, hora = ?, cancha = '1', estado = ? WHERE id = ?",
            (SABADO.isoformat(), hora, rol.PROGRAMADO, partido_id),
        )


def por_ronda(conn, liguilla_id, numero):
    return [v for v in liguilla.vista(conn, liguilla_id) if v.numero_ronda == numero]


def jugar(conn, vista_llave, goles_a=1, goles_b=0, penales=None):
    """Captura el partido de una llave, con goles expresados desde el lado a y el lado b."""
    programar(conn, vista_llave.partido_id)
    partido = conn.execute("SELECT * FROM partidos WHERE id = ?", (vista_llave.partido_id,)).fetchone()
    equipo_a = conn.execute(
        "SELECT equipo_a_id FROM llaves WHERE id = ?", (vista_llave.id,)
    ).fetchone()[0]
    if partido["local_id"] == equipo_a:
        resultados.guardar_resultado(conn, partido["id"], goles_a, goles_b, penales=penales)
    else:
        resultados.guardar_resultado(
            conn, partido["id"], goles_b, goles_a, penales=penales[::-1] if penales else None
        )


@pytest.mark.parametrize(
    "tamano, esperado",
    [
        (2, [1, 2]),
        (4, [1, 4, 2, 3]),
        (8, [1, 8, 4, 5, 2, 7, 3, 6]),
    ],
)
def test_posiciones_de_la_llave(tamano, esperado):
    assert liguilla.posiciones_llave(tamano) == esperado


def test_cuartos_con_ocho_cruzan_primero_contra_octavo(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 8, liguilla.PENALES)
    cuartos = por_ronda(conn, g, 1)
    assert {v.ronda for v in cuartos} == {"Cuartos de final"}
    assert [(v.equipo_a, v.equipo_b) for v in cuartos] == [
        ("E1", "E8"), ("E4", "E5"), ("E2", "E7"), ("E3", "E6"),
    ]
    assert [v.ronda for v in por_ronda(conn, g, 2)] == ["Semifinal"] * 2
    assert [v.ronda for v in por_ronda(conn, g, 3)] == ["Final"]
    assert all(v.partido_id for v in cuartos)
    assert all(v.partido_id is None for v in por_ronda(conn, g, 2))


def test_rango_elegido_toma_esos_lugares(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 3, 6, liguilla.TABLA)
    semis = por_ronda(conn, g, 1)
    assert [(v.equipo_a, v.semilla_a, v.equipo_b, v.semilla_b) for v in semis] == [
        ("E3", 1, "E6", 4), ("E4", 2, "E5", 3),
    ]
    assert semis[0].ronda == "Semifinal"


@pytest.mark.parametrize("desde, hasta", [(0, 4), (1, 9), (3, 3), (5, 2)])
def test_rango_invalido(conn, torneo_id, categoria, equipos, desde, hasta):
    with pytest.raises(ValueError):
        liguilla.crear(conn, torneo_id, categoria, desde, hasta, liguilla.PENALES)
    assert liguilla.obtener(conn, torneo_id, categoria) is None


def test_clasificados_impares_dan_pase_directo_a_los_mejores(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 5, liguilla.PENALES)
    cuartos = por_ronda(conn, g, 1)
    directos = [v for v in cuartos if v.pasa_directo]
    assert sorted(v.ganador for v in directos) == ["E1", "E2", "E3"]
    jugados = [v for v in cuartos if not v.pasa_directo]
    assert [(v.equipo_a, v.equipo_b) for v in jugados] == [("E4", "E5")]
    # E2 y E3 ya se cruzan en semifinal; E1 espera al ganador de E4 contra E5.
    semis = por_ronda(conn, g, 2)
    con_partido = [v for v in semis if v.partido_id]
    assert len(con_partido) == 1
    assert {con_partido[0].equipo_a, con_partido[0].equipo_b} == {"E2", "E3"}


def test_flujo_completo_hasta_el_campeon(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.PENALES)
    assert liguilla.campeon(conn, g) == ""
    semis = por_ronda(conn, g, 1)
    jugar(conn, semis[0], 2, 0)  # E1 le gana a E4
    assert por_ronda(conn, g, 2)[0].equipo_a == "E1"
    assert por_ronda(conn, g, 2)[0].partido_id is None  # falta el otro finalista
    jugar(conn, semis[1], 0, 1)  # E3 le gana a E2
    final = por_ronda(conn, g, 2)[0]
    assert {final.equipo_a, final.equipo_b} == {"E1", "E3"}
    assert final.partido_id
    partido = conn.execute("SELECT * FROM partidos WHERE id = ?", (final.partido_id,)).fetchone()
    assert partido["estado"] == rol.POR_PROGRAMAR and partido["fecha"] is None
    assert rol.nombre_jornada(partido["jornada"]) == "Final"
    jugar(conn, final, 3, 1)
    assert liguilla.campeon(conn, g) == "E1"


def test_empate_con_penales_exige_ganador(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.PENALES)
    semi = por_ronda(conn, g, 1)[0]
    programar(conn, semi.partido_id)
    with pytest.raises(ValueError, match="penales"):
        resultados.guardar_resultado(conn, semi.partido_id, 1, 1)
    with pytest.raises(ValueError, match="penales"):
        resultados.guardar_resultado(conn, semi.partido_id, 1, 1, penales=(3, 3))
    # El fallo no dejó nada a medias.
    assert conn.execute(
        "SELECT estado FROM partidos WHERE id = ?", (semi.partido_id,)
    ).fetchone()[0] == rol.PROGRAMADO
    assert conn.execute(
        "SELECT 1 FROM resultados WHERE partido_id = ?", (semi.partido_id,)
    ).fetchone() is None

    # Visitante (E4) gana en penales.
    resultados.guardar_resultado(conn, semi.partido_id, 1, 1, penales=(3, 4))
    vista = por_ronda(conn, g, 1)[0]
    assert vista.ganador == "E4"
    assert (vista.penales_a, vista.penales_b) == (3, 4)


def test_empate_por_tabla_avanza_el_mejor_lugar(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.TABLA)
    semi = por_ronda(conn, g, 1)[0]
    programar(conn, semi.partido_id)
    resultados.guardar_resultado(conn, semi.partido_id, 2, 2)
    assert por_ronda(conn, g, 1)[0].ganador == "E1"


def test_cambiar_desempate_aplica_a_lo_que_sigue(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.PENALES)
    liguilla.cambiar_desempate(conn, g, liguilla.TABLA)
    semi = por_ronda(conn, g, 1)[1]
    programar(conn, semi.partido_id)
    resultados.guardar_resultado(conn, semi.partido_id, 0, 0)
    assert por_ronda(conn, g, 1)[1].ganador == "E2"
    with pytest.raises(ValueError):
        liguilla.cambiar_desempate(conn, g, "volado")


def test_corregir_resultado_cambia_al_finalista_y_conserva_la_fecha(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.PENALES)
    semis = por_ronda(conn, g, 1)
    jugar(conn, semis[0], 2, 0)
    jugar(conn, semis[1], 2, 0)
    final = por_ronda(conn, g, 2)[0]
    programar(conn, final.partido_id, "12:00")

    # Se corrige: en realidad ganó E4.
    resultados.guardar_resultado(conn, semis[0].partido_id, 0, 3)
    final = por_ronda(conn, g, 2)[0]
    assert {final.equipo_a, final.equipo_b} == {"E4", "E2"}
    assert final.hora == "12:00"
    # El mejor lugar de los que quedan es local.
    partido = conn.execute("SELECT * FROM partidos WHERE id = ?", (final.partido_id,)).fetchone()
    nombre = conn.execute("SELECT nombre FROM equipos WHERE id = ?", (partido["local_id"],)).fetchone()[0]
    assert nombre == "E2"


def test_no_se_cambia_quien_avanza_si_la_siguiente_ronda_ya_se_jugo(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.PENALES)
    semis = por_ronda(conn, g, 1)
    jugar(conn, semis[0], 2, 0)
    jugar(conn, semis[1], 2, 0)
    jugar(conn, por_ronda(conn, g, 2)[0], 1, 0)

    with pytest.raises(ValueError, match="siguiente ronda"):
        resultados.guardar_resultado(conn, semis[0].partido_id, 0, 3)
    with pytest.raises(ValueError, match="siguiente ronda"):
        resultados.borrar_resultado(conn, semis[0].partido_id)
    # Un marcador corregido sin cambiar al ganador sí se permite.
    resultados.guardar_resultado(conn, semis[0].partido_id, 5, 0)
    assert por_ronda(conn, g, 1)[0].goles_a == 5
    assert liguilla.campeon(conn, g) == por_ronda(conn, g, 2)[0].ganador


def test_borrar_resultado_quita_el_partido_siguiente(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.PENALES)
    semis = por_ronda(conn, g, 1)
    jugar(conn, semis[0], 2, 0)
    jugar(conn, semis[1], 2, 0)
    final = por_ronda(conn, g, 2)[0]
    resultados.borrar_resultado(conn, semis[0].partido_id)
    despues = por_ronda(conn, g, 2)[0]
    assert despues.partido_id is None
    assert conn.execute("SELECT 1 FROM partidos WHERE id = ?", (final.partido_id,)).fetchone() is None
    assert por_ronda(conn, g, 1)[0].ganador == ""
    # Se puede volver a capturar y la final se recrea.
    jugar(conn, por_ronda(conn, g, 1)[0], 0, 1)
    assert por_ronda(conn, g, 2)[0].partido_id


def test_default_en_liguilla_avanza_el_presente(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.PENALES)
    semi = por_ronda(conn, g, 1)[0]
    programar(conn, semi.partido_id)
    partido = conn.execute("SELECT * FROM partidos WHERE id = ?", (semi.partido_id,)).fetchone()
    resultados.dar_default(conn, semi.partido_id, partido["local_id"], cobros.PAGA_AUSENTE)
    assert por_ronda(conn, g, 1)[0].ganador == "E4"


def test_partido_sin_programar_no_admite_resultado(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.PENALES)
    semi = por_ronda(conn, g, 1)[0]
    with pytest.raises(ValueError, match="fecha"):
        resultados.guardar_resultado(conn, semi.partido_id, 1, 0)
    partido = conn.execute("SELECT * FROM partidos WHERE id = ?", (semi.partido_id,)).fetchone()
    with pytest.raises(ValueError, match="fecha"):
        resultados.dar_default(conn, semi.partido_id, partido["local_id"], cobros.PAGA_AUSENTE)


def test_liguilla_no_suma_a_la_tabla_pero_si_al_goleo(conn, torneo_id, categoria, equipos):
    with conn:
        goleador = conn.execute(
            "INSERT INTO jugadores (equipo_id, nombre, fecha_nacimiento, numero) "
            "VALUES (?, 'Goleador', '2015-01-01', 9)",
            (equipos[0],),
        ).lastrowid
    antes = {f.nombre: (f.pj, f.pts, f.gf) for f in estadisticas.tabla_posiciones(conn, torneo_id, categoria)}
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.PENALES)
    semi = por_ronda(conn, g, 1)[0]
    programar(conn, semi.partido_id)
    resultados.guardar_resultado(conn, semi.partido_id, 5, 0, {goleador: 5})
    despues = {f.nombre: (f.pj, f.pts, f.gf) for f in estadisticas.tabla_posiciones(conn, torneo_id, categoria)}
    assert antes == despues
    assert estadisticas.goleadores(conn, torneo_id, categoria)[0]["goles"] == 5


def test_liguilla_cobra_arbitraje_con_nombre_de_ronda(conn, torneo_id, categoria, equipos):
    cobros.guardar_tarifas(conn, torneo_id, {categoria: (15000, 0)})
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.PENALES)
    semi = por_ronda(conn, g, 1)[0]
    programar(conn, semi.partido_id)
    resultados.guardar_resultado(conn, semi.partido_id, 1, 0)
    cargo = [c for c in cobros.cargos_de_equipo(conn, equipos[0]) if "Semifinal" in c.detalle]
    assert cargo and cargo[0].detalle == "Semifinal contra E4"
    folio = cobros.registrar_pago(conn, equipos[0], 15000, SABADO, primero=cargo[0].id)
    assert cobros.detalle_de_pago(conn, folio)[0][0] == "Arbitraje: semifinal contra E4"


def test_regenerar_rol_no_borra_nada_si_hay_liguilla(conn, torneo_id, categoria, equipos):
    liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.PENALES)
    horario = rol.Horario(SABADO, {5: (540, 800)})
    total = conn.execute("SELECT COUNT(*) FROM partidos").fetchone()[0]
    with pytest.raises(ValueError):
        rol.generar(conn, torneo_id, [categoria], horario)
    assert conn.execute("SELECT COUNT(*) FROM partidos").fetchone()[0] == total


def test_no_regenera_rol_con_liguilla_sin_resultados(conn, torneo_id, infantil_id):
    categoria = conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2017-2018'", (infantil_id,)
    ).fetchone()["id"]
    with conn:
        for n in ("A", "B", "C", "D"):
            conn.execute(
                "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
                (torneo_id, categoria, n),
            )
    liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.TABLA)
    with pytest.raises(ValueError, match="liguilla"):
        rol.generar(conn, torneo_id, [categoria], rol.Horario(SABADO, {5: (540, 800)}))


def test_descansos_ignoran_partidos_de_liguilla(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.TABLA)
    semi = por_ronda(conn, g, 1)[0]
    with conn:
        conn.execute(
            "UPDATE partidos SET fecha = '2030-01-05', hora = '09:00', cancha = '1', estado = ? WHERE id = ?",
            (rol.PROGRAMADO, semi.partido_id),
        )
    assert rol.descansos(conn, torneo_id, "2030-01-05") == []


def test_eliminar_liguilla(conn, torneo_id, categoria, equipos):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.PENALES)
    semi = por_ronda(conn, g, 1)[0]
    programar(conn, semi.partido_id)
    resultados.guardar_resultado(conn, semi.partido_id, 1, 0)
    with pytest.raises(ValueError, match="resultados"):
        liguilla.eliminar(conn, g)
    resultados.borrar_resultado(conn, semi.partido_id)
    regulares = conn.execute("SELECT COUNT(*) FROM resultados").fetchone()[0]
    liguilla.eliminar(conn, g)
    assert liguilla.obtener(conn, torneo_id, categoria) is None
    assert conn.execute("SELECT COUNT(*) FROM llaves").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM resultados").fetchone()[0] == regulares
    assert conn.execute(
        "SELECT COUNT(*) FROM partidos WHERE jornada > ?", (rol.BASE_LIGUILLA,)
    ).fetchone()[0] == 0
    # Se puede crear otra.
    assert liguilla.crear(conn, torneo_id, categoria, 1, 2, liguilla.TABLA)


def test_una_liguilla_por_categoria(conn, torneo_id, categoria, equipos):
    liguilla.crear(conn, torneo_id, categoria, 1, 4, liguilla.TABLA)
    with pytest.raises(ValueError, match="ya tiene"):
        liguilla.crear(conn, torneo_id, categoria, 1, 2, liguilla.TABLA)


@pytest.mark.parametrize(
    "jornada, nombre",
    [(3, "Jornada 3"), (101, "Final"), (102, "Semifinal"), (103, "Cuartos de final"),
     (104, "Octavos de final"), (106, "Ronda de 64")],
)
def test_nombre_jornada(jornada, nombre):
    assert rol.nombre_jornada(jornada) == nombre


def test_respaldo_anterior_recibe_tablas_de_liguilla(conn, tmp_path):
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    with conn:
        conn.execute("DROP TABLE llaves")
        conn.execute("DROP TABLE liguillas")
    viejo = tmp_path / "viejo.zip"
    db.respaldar(conn, viejo, fotos)
    db.restaurar(conn, viejo, fotos)
    assert conn.execute("SELECT COUNT(*) FROM llaves").fetchone()[0] == 0


# --- Pantallas ---


@pytest.fixture
def ventana(app, conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    resultado = Ventana(conn)
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


def test_pagina_crear_y_ver_llave(ventana, conn, torneo_id, categoria, equipos, monkeypatch):
    ventana.show()
    pagina = ventana.liguilla
    ventana.pila.setCurrentWidget(pagina)
    pagina.filtros.refrescar()
    assert pagina.filtros.categoria.currentText() == "2015-2016"
    assert pagina.crear_panel.isVisible() and not pagina.llave_panel.isVisible()
    assert pagina.hasta.value() == 8
    assert pagina.tabla_clasificados.rowCount() == 8
    assert "Todos juegan" in pagina.nota_llave.text()

    pagina.hasta.setValue(5)
    assert pagina.tabla_clasificados.rowCount() == 5
    assert "3 mejores pasan directo" in pagina.nota_llave.text()
    pagina.desde.setValue(2)
    pagina.hasta.setValue(5)
    assert pagina.tabla_clasificados.item(0, 1).text() == "E2"
    assert pagina.tabla_clasificados.item(0, 0).text() == "2"
    assert "mejor lugar pasa directo" not in pagina.nota_llave.text()

    pagina.desde.setValue(1)
    pagina.hasta.setValue(4)
    pagina.desempate_nuevo.setCurrentIndex(pagina.desempate_nuevo.findData(liguilla.TABLA))
    pagina.crear()
    assert not pagina.crear_panel.isVisible() and pagina.llave_panel.isVisible()
    obtenida = liguilla.obtener(conn, torneo_id, categoria)
    assert (obtenida["desde"], obtenida["hasta"], obtenida["desempate"]) == (1, 4, liguilla.TABLA)
    tarjetas = pagina.lienzo.findChildren(QPushButton, "llave")
    assert len(tarjetas) == 3
    assert any("(1) E1" in t.text() and "(4) E4" in t.text() for t in tarjetas)


def test_pagina_pide_confirmar_si_falta_fase_regular(ventana, conn, torneo_id, categoria, monkeypatch):
    with conn:
        ids = [
            conn.execute(
                "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
                (torneo_id, categoria, n),
            ).lastrowid
            for n in ("A", "B")
        ]
    crear_partido(conn, torneo_id, categoria, ids[0], ids[1])
    pagina = ventana.liguilla
    pagina.filtros.refrescar()
    assert "Faltan 1" in pagina.aviso.text()
    preguntas = []
    monkeypatch.setattr(ui_liguilla, "confirmar", lambda _, m: preguntas.append(m) or False)
    pagina.crear()
    assert preguntas and liguilla.obtener(conn, torneo_id, categoria) is None


def test_pagina_programar_capturar_y_campeon(ventana, conn, torneo_id, categoria, equipos, monkeypatch):
    ventana.show()
    pagina = ventana.liguilla
    ventana.pila.setCurrentWidget(pagina)
    pagina.filtros.refrescar()
    pagina.desde.setValue(1)
    pagina.hasta.setValue(2)
    pagina.crear()
    final = liguilla.vista(conn, pagina.liguilla_id)[0]

    errores = []
    monkeypatch.setattr(ui_liguilla, "error", lambda _, m: errores.append(m))
    pagina.capturar()
    assert "selecciona" in errores[0]

    pagina._elegir(final.id)

    def fijar_fecha(dialogo):
        assert not dialogo.local.isEnabled() and not dialogo.jornada.isEnabled()
        dialogo.fecha.setDate(SABADO)
        return True

    monkeypatch.setattr(ui_rol.DialogoPartido, "exec", fijar_fecha)
    pagina.programar()
    partido = conn.execute("SELECT * FROM partidos WHERE id = ?", (final.partido_id,)).fetchone()
    assert partido["estado"] == rol.PROGRAMADO and partido["fecha"] == SABADO.isoformat()

    def capturar(dialogo):
        dialogo.marcador_local.setValue(1)
        dialogo.marcador_visitante.setValue(1)
        dialogo.penales_local.setValue(5)
        dialogo.penales_visitante.setValue(4)
        dialogo._aceptar()
        return dialogo.result()

    monkeypatch.setattr(ui_resultados.DialogoResultado, "exec", capturar)
    pagina.capturar()
    assert pagina.campeon.isVisible() and pagina.campeon.text() == "Campeón: E1"
    assert liguilla.campeon(conn, pagina.liguilla_id) == "E1"


def test_dialogo_resultado_pide_penales_solo_si_aplica(ventana, conn, torneo_id, categoria, equipos):
    partido_regular = conn.execute("SELECT * FROM partidos LIMIT 1").fetchone()
    regular = ui_resultados.DialogoResultado(ventana, conn, partido_regular, "A", "B")
    assert not regular.pide_penales

    g = liguilla.crear(conn, torneo_id, categoria, 1, 2, liguilla.PENALES)
    partido = conn.execute(
        "SELECT * FROM partidos WHERE id = ?", (liguilla.vista(conn, g)[0].partido_id,)
    ).fetchone()
    assert ui_resultados.DialogoResultado(ventana, conn, partido, "A", "B").pide_penales
    liguilla.cambiar_desempate(conn, g, liguilla.TABLA)
    assert not ui_resultados.DialogoResultado(ventana, conn, partido, "A", "B").pide_penales


def test_rol_no_deja_eliminar_partido_de_liguilla(ventana, conn, torneo_id, categoria, equipos, monkeypatch):
    g = liguilla.crear(conn, torneo_id, categoria, 1, 2, liguilla.TABLA)
    errores = []
    monkeypatch.setattr(ui_rol, "error", lambda _, m: errores.append(m))
    monkeypatch.setattr(ui_rol, "confirmar", lambda *a: True)
    pagina = ventana.rol
    pagina.refrescar()
    pagina.fecha.setCurrentIndex(0)
    ultimo = pagina.tabla.rowCount() - 1
    assert pagina.tabla.item(ultimo, 6).text() == "Final"
    pagina.tabla.selectRow(ultimo)
    pagina.eliminar()
    assert "liguilla" in errores[0]
    assert liguilla.vista(conn, g)[0].partido_id


def test_pagina_sin_datos_no_falla(ventana):
    ventana.show()
    ventana.pila.setCurrentWidget(ventana.liguilla)
    assert ventana.liguilla.crear_panel.isVisible()
    assert "al menos 2 equipos" in ventana.liguilla.aviso.text()
