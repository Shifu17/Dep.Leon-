import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date

import pytest

from dep_leon import cobros, db, recibos, resultados, rol, updater
from dep_leon.ui import pagina_cobros as ui_cobros
from dep_leon.ui import pagina_equipos as ui_equipos
from dep_leon.ui import pagina_resultados as ui_resultados
from dep_leon.ui import pagina_rol as ui_rol
from dep_leon.ui.ventana import Ventana

HOY = date(2026, 11, 4)
SABADO = date(2026, 11, 7)
ARBITRAJE = 15000  # $150.00
INSCRIPCION = 100000  # $1,000.00


@pytest.fixture
def categoria(conn, infantil_id):
    return conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2015-2016'", (infantil_id,)
    ).fetchone()["id"]


@pytest.fixture
def equipos(conn, torneo_id, categoria):
    with conn:
        return tuple(
            conn.execute(
                "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
                (torneo_id, categoria, n),
            ).lastrowid
            for n in ("Pegasos", "Buitres")
        )


@pytest.fixture
def con_tarifa(conn, torneo_id, categoria, equipos):
    cobros.guardar_tarifas(conn, torneo_id, {categoria: (ARBITRAJE, INSCRIPCION)})
    return equipos


def crear_partido(conn, torneo_id, categoria, local, visitante, jornada=1):
    with conn:
        return conn.execute(
            "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, fecha, "
            "hora, minutos, cancha, estado) VALUES (?, ?, ?, ?, ?, ?, '09:00', 50, '1', ?)",
            (torneo_id, categoria, jornada, local, visitante, SABADO.isoformat(), rol.PROGRAMADO),
        ).lastrowid


def arbitrajes(conn, equipo):
    return [c for c in cobros.cargos_de_equipo(conn, equipo) if c.concepto == cobros.ARBITRAJE]


def saldo(conn, torneo_id, equipo):
    return next(a.saldo for a in cobros.adeudos(conn, torneo_id) if a.equipo_id == equipo)


@pytest.mark.parametrize(
    "centavos, texto",
    [(0, "$0.00"), (15000, "$150.00"), (123456, "$1,234.56"), (5, "$0.05")],
)
def test_dinero(centavos, texto):
    assert cobros.dinero(centavos) == texto


def test_a_centavos_no_pierde_por_redondeo():
    assert cobros.a_centavos(19.99) == 1999
    assert cobros.a_centavos(1.1) == 110


def test_tarifas_empiezan_en_cero_y_son_por_categoria(conn, torneo_id, categoria):
    lista = cobros.tarifas(conn, torneo_id)
    assert len(lista) == 6 and all(t.arbitraje == 0 and t.inscripcion == 0 for t in lista)
    cobros.guardar_tarifas(conn, torneo_id, {categoria: (ARBITRAJE, INSCRIPCION)})
    guardadas = {t.categoria: t for t in cobros.tarifas(conn, torneo_id)}
    assert guardadas["2015-2016"].arbitraje == ARBITRAJE
    assert guardadas["2017-2018"].arbitraje == 0


def test_rechaza_montos_negativos(conn, torneo_id, categoria):
    with pytest.raises(ValueError):
        cobros.guardar_tarifas(conn, torneo_id, {categoria: (-1, 0)})


def test_inscripcion_se_carga_una_vez_por_equipo(conn, torneo_id, categoria, con_tarifa):
    a, b = con_tarifa
    assert [c.monto for c in cobros.cargos_de_equipo(conn, a)] == [INSCRIPCION]
    cobros.sincronizar_torneo(conn, torneo_id)
    cobros.guardar_tarifas(conn, torneo_id, {categoria: (ARBITRAJE, INSCRIPCION)})
    assert len(cobros.cargos_de_equipo(conn, a)) == 1


def test_equipo_nuevo_recibe_inscripcion_al_sincronizar(conn, torneo_id, categoria, con_tarifa):
    with conn:
        nuevo = conn.execute(
            "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, 'Nuevo')",
            (torneo_id, categoria),
        ).lastrowid
    cobros.sincronizar_torneo(conn, torneo_id)
    assert cobros.cargos_de_equipo(conn, nuevo)[0].monto == INSCRIPCION


def test_programar_no_cobra_y_capturar_cobra_a_ambos(conn, torneo_id, categoria, con_tarifa):
    a, b = con_tarifa
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    assert arbitrajes(conn, a) == []
    resultados.guardar_resultado(conn, partido, 2, 1)
    assert arbitrajes(conn, a)[0].monto == ARBITRAJE
    assert arbitrajes(conn, b)[0].monto == ARBITRAJE
    assert "contra Buitres" in arbitrajes(conn, a)[0].detalle
    assert arbitrajes(conn, a)[0].fecha == SABADO.isoformat()


def test_pospuesto_no_genera_cobro(conn, torneo_id, categoria, con_tarifa):
    a, b = con_tarifa
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    rol.posponer(conn, partido)
    cobros.sincronizar_torneo(conn, torneo_id)
    assert arbitrajes(conn, a) == [] and arbitrajes(conn, b) == []


def test_corregir_marcador_no_duplica_el_cargo(conn, torneo_id, categoria, con_tarifa):
    a, b = con_tarifa
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    resultados.guardar_resultado(conn, partido, 2, 1)
    resultados.guardar_resultado(conn, partido, 3, 1)
    assert len(arbitrajes(conn, a)) == 1


@pytest.mark.parametrize(
    "paga, pagan_local, pagan_visitante",
    [
        (cobros.PAGA_AUSENTE, True, False),
        (cobros.PAGA_PRESENTE, False, True),
        (cobros.PAGA_AMBOS, True, True),
        (cobros.PAGA_NINGUNO, False, False),
    ],
)
def test_default_cobra_a_quien_se_indica(conn, torneo_id, categoria, con_tarifa, paga, pagan_local, pagan_visitante):
    a, b = con_tarifa  # el local no se presentó
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    resultados.dar_default(conn, partido, a, paga)
    assert bool(arbitrajes(conn, a)) is pagan_local
    assert bool(arbitrajes(conn, b)) is pagan_visitante


def test_borrar_resultado_quita_cargos_sin_pagos(conn, torneo_id, categoria, con_tarifa):
    a, b = con_tarifa
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    resultados.guardar_resultado(conn, partido, 1, 0)
    resultados.borrar_resultado(conn, partido)
    assert arbitrajes(conn, a) == []
    assert conn.execute("SELECT estado FROM partidos").fetchone()[0] == rol.PROGRAMADO


def test_no_se_borra_resultado_con_arbitraje_pagado(conn, torneo_id, categoria, con_tarifa):
    a, b = con_tarifa
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    resultados.guardar_resultado(conn, partido, 1, 0)
    cargo = arbitrajes(conn, a)[0]
    folio = cobros.registrar_pago(conn, a, 100, HOY, primero=cargo.id)
    with pytest.raises(ValueError, match="pagos"):
        resultados.borrar_resultado(conn, partido)
    # Falló de forma atómica: el resultado y el estado siguen igual.
    assert conn.execute("SELECT COUNT(*) FROM resultados").fetchone()[0] == 1
    assert conn.execute("SELECT estado FROM partidos").fetchone()[0] == rol.JUGADO
    cobros.anular_pago(conn, folio)
    resultados.borrar_resultado(conn, partido)
    assert arbitrajes(conn, a) == []


def test_cambiar_a_default_no_quita_cargo_pagado(conn, torneo_id, categoria, con_tarifa):
    a, b = con_tarifa
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    resultados.guardar_resultado(conn, partido, 1, 0)
    cobros.registrar_pago(conn, b, 100, HOY, primero=arbitrajes(conn, b)[0].id)
    with pytest.raises(ValueError, match="pagos"):
        resultados.dar_default(conn, partido, a, cobros.PAGA_AUSENTE)
    assert conn.execute("SELECT estado FROM partidos").fetchone()[0] == rol.JUGADO
    assert conn.execute("SELECT ausente_id FROM resultados").fetchone()[0] is None


def test_poner_monto_despues_cobra_lo_ya_jugado(conn, torneo_id, categoria, equipos):
    a, b = equipos
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    resultados.guardar_resultado(conn, partido, 1, 0)
    assert arbitrajes(conn, a) == []
    cobros.guardar_tarifas(conn, torneo_id, {categoria: (ARBITRAJE, 0)})
    assert arbitrajes(conn, a)[0].monto == ARBITRAJE


def test_cambiar_monto_respeta_cargos_con_pagos(conn, torneo_id, categoria, con_tarifa):
    a, b = con_tarifa
    cobros.registrar_pago(conn, a, 100, HOY)
    cobros.guardar_tarifas(conn, torneo_id, {categoria: (ARBITRAJE, 200000)}, aplicar_a_cargos=True)
    assert cobros.cargos_de_equipo(conn, a)[0].monto == INSCRIPCION  # ya tenía un pago
    assert cobros.cargos_de_equipo(conn, b)[0].monto == 200000


def test_cambiar_monto_sin_aplicar_no_toca_cargos(conn, torneo_id, categoria, con_tarifa):
    a, _ = con_tarifa
    cobros.guardar_tarifas(conn, torneo_id, {categoria: (ARBITRAJE, 200000)})
    assert cobros.cargos_de_equipo(conn, a)[0].monto == INSCRIPCION


def test_abono_parcial_y_saldo(conn, torneo_id, con_tarifa):
    a, _ = con_tarifa
    cobros.registrar_pago(conn, a, 30000, HOY, "efectivo")
    assert saldo(conn, torneo_id, a) == 70000
    cargo = cobros.cargos_de_equipo(conn, a)[0]
    assert (cargo.pagado, cargo.saldo) == (30000, 70000)
    pago = cobros.pagos_de_equipo(conn, a)[0]
    assert (pago["monto"], pago["nota"], pago["fecha"]) == (30000, "efectivo", HOY.isoformat())


def test_pago_cubre_primero_lo_elegido_y_luego_lo_antiguo(conn, torneo_id, categoria, con_tarifa):
    a, b = con_tarifa
    resultados.guardar_resultado(conn, crear_partido(conn, torneo_id, categoria, a, b), 1, 0)
    resultados.guardar_resultado(conn, crear_partido(conn, torneo_id, categoria, a, b, 2), 1, 0)
    segundo = arbitrajes(conn, a)[1]
    cobros.registrar_pago(conn, a, ARBITRAJE + 100, HOY, primero=segundo.id)
    cargos = {c.id: c for c in cobros.cargos_de_equipo(conn, a)}
    assert cargos[segundo.id].saldo == 0
    inscripcion = next(c for c in cargos.values() if c.concepto == cobros.INSCRIPCION)
    assert inscripcion.pagado == 100  # el más antiguo
    assert arbitrajes(conn, a)[0].pagado == 0


def test_sin_cargo_elegido_paga_del_mas_antiguo(conn, torneo_id, categoria, con_tarifa):
    a, b = con_tarifa
    resultados.guardar_resultado(conn, crear_partido(conn, torneo_id, categoria, a, b), 1, 0)
    cobros.registrar_pago(conn, a, 100, HOY)
    assert cobros.cargos_de_equipo(conn, a)[0].concepto == cobros.INSCRIPCION
    assert cobros.cargos_de_equipo(conn, a)[0].pagado == 100


@pytest.mark.parametrize("monto", [0, -5, INSCRIPCION + 1])
def test_pago_invalido_no_registra(conn, con_tarifa, monto):
    a, _ = con_tarifa
    with pytest.raises(ValueError):
        cobros.registrar_pago(conn, a, monto, HOY)
    assert cobros.pagos_de_equipo(conn, a) == []


def test_anular_devuelve_el_saldo_y_conserva_el_folio(conn, torneo_id, con_tarifa):
    a, _ = con_tarifa
    folio = cobros.registrar_pago(conn, a, 30000, HOY)
    cobros.anular_pago(conn, folio)
    assert saldo(conn, torneo_id, a) == INSCRIPCION
    assert cobros.pagos_de_equipo(conn, a)[0]["anulado"] == 1
    # El folio de un pago anulado nunca se reutiliza.
    assert cobros.registrar_pago(conn, a, 100, HOY) == folio + 1


def test_ajustar_cargo_y_perdonar(conn, torneo_id, con_tarifa):
    a, _ = con_tarifa
    cargo = cobros.cargos_de_equipo(conn, a)[0]
    cobros.ajustar_cargo(conn, cargo.id, 0)
    assert saldo(conn, torneo_id, a) == 0
    # Sincronizar no vuelve a crear un cargo perdonado.
    cobros.sincronizar_torneo(conn, torneo_id)
    assert cobros.cargos_de_equipo(conn, a)[0].monto == 0

    cobros.ajustar_cargo(conn, cargo.id, 5000)
    cobros.registrar_pago(conn, a, 3000, HOY)
    with pytest.raises(ValueError, match="pagado"):
        cobros.ajustar_cargo(conn, cargo.id, 2999)


def test_resumen_del_torneo_y_por_categoria(conn, torneo_id, categoria, con_tarifa, infantil_id):
    a, b = con_tarifa
    resultados.guardar_resultado(conn, crear_partido(conn, torneo_id, categoria, a, b), 1, 0)
    cobros.registrar_pago(conn, a, 50000, HOY)
    total = cobros.resumen(conn, torneo_id)
    assert total.cargado == 2 * (INSCRIPCION + ARBITRAJE)
    assert total.cobrado == 50000
    assert total.pendiente == total.cargado - 50000
    otra = conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2017-2018'", (infantil_id,)
    ).fetchone()["id"]
    assert cobros.resumen(conn, torneo_id, otra).cargado == 0


def test_recibo_pdf_con_detalle(conn, torneo_id, categoria, con_tarifa, tmp_path):
    a, b = con_tarifa
    resultados.guardar_resultado(conn, crear_partido(conn, torneo_id, categoria, a, b), 1, 0)
    folio = cobros.registrar_pago(conn, a, INSCRIPCION + 100, HOY, "transferencia")
    detalle = cobros.detalle_de_pago(conn, folio)
    assert detalle == [
        (cobros.INSCRIPCION, INSCRIPCION),
        ("Arbitraje: jornada 1 contra Buitres", 100),
    ]
    destino = tmp_path / "r.pdf"
    recibos.generar(conn, folio, destino)
    assert destino.read_bytes().startswith(b"%PDF")


def test_recibo_con_muchos_conceptos_no_se_sale_de_la_hoja(conn, torneo_id, categoria, con_tarifa, tmp_path):
    a, b = con_tarifa
    for jornada in range(1, 30):
        resultados.guardar_resultado(conn, crear_partido(conn, torneo_id, categoria, a, b, jornada), 1, 0)
    folio = cobros.registrar_pago(conn, a, INSCRIPCION + 29 * ARBITRAJE, HOY)
    recibos.generar(conn, folio, tmp_path / "r.pdf")
    assert (tmp_path / "r.pdf").read_bytes().startswith(b"%PDF")


def test_recibo_de_pago_anulado_se_rechaza(conn, con_tarifa, tmp_path):
    a, _ = con_tarifa
    folio = cobros.registrar_pago(conn, a, 100, HOY)
    cobros.anular_pago(conn, folio)
    with pytest.raises(ValueError):
        recibos.generar(conn, folio, tmp_path / "r.pdf")


def test_respaldo_conserva_pagos_y_anteriores_reciben_tablas(conn, con_tarifa, tmp_path):
    a, _ = con_tarifa
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    cobros.registrar_pago(conn, a, 100, HOY)
    respaldo = tmp_path / "r.zip"
    db.respaldar(conn, respaldo, fotos)
    with conn:
        conn.execute("DELETE FROM aplicaciones")
        conn.execute("DELETE FROM pagos")
    db.restaurar(conn, respaldo, fotos)
    assert cobros.pagos_de_equipo(conn, a)[0]["monto"] == 100

    with conn:
        for tabla in ("aplicaciones", "pagos", "cargos", "tarifas"):
            conn.execute(f"DROP TABLE {tabla}")
    viejo = tmp_path / "viejo.zip"
    db.respaldar(conn, viejo, fotos)
    db.restaurar(conn, viejo, fotos)
    assert conn.execute("SELECT COUNT(*) FROM cargos").fetchone()[0] == 0


# --- Pantallas ---


@pytest.fixture
def ventana(app, conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    resultado = Ventana(conn)
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


def seleccionar(tabla, texto):
    for fila in range(tabla.rowCount()):
        if tabla.item(fila, 0).text() == texto:
            tabla.selectRow(fila)
            return
    raise AssertionError(texto)


def test_flujo_montos_pago_y_anulacion(ventana, conn, torneo_id, categoria, equipos, monkeypatch):
    pagina = ventana.cobros
    pagina.filtros.refrescar()
    assert pagina.pendiente.numero.text() == "$0.00"

    def fijar(dialogo):
        dialogo.campos[categoria][0].setValue(150)
        dialogo.campos[categoria][1].setValue(1000)
        return True

    monkeypatch.setattr(ui_cobros.DialogoTarifas, "exec", fijar)
    pagina.editar_tarifas()
    assert pagina.cargado.numero.text() == "$2,000.00"
    assert pagina.equipos.rowCount() == 2

    seleccionar(pagina.equipos, "Pegasos")
    assert pagina.cargos.item(0, 0).text() == cobros.INSCRIPCION
    assert pagina.cargos.item(0, 5).text() == "$1,000.00"

    def abonar(dialogo):
        dialogo.monto.setValue(250)
        dialogo.nota.setText("efectivo")
        return True

    monkeypatch.setattr(ui_cobros.DialogoPago, "exec", abonar)
    pagina.registrar_pago()
    assert pagina.cobrado.numero.text() == "$250.00"
    assert pagina.pendiente.numero.text() == "$1,750.00"
    assert pagina.pagos.rowCount() == 1 and pagina.pagos.item(0, 3).text() == "efectivo"
    assert pagina.cargos.item(0, 5).text() == "$750.00"

    monkeypatch.setattr(ui_cobros, "confirmar", lambda *a: True)
    pagina.pagos.selectRow(0)
    pagina.anular()
    assert pagina.pendiente.numero.text() == "$2,000.00"
    assert pagina.pagos.item(0, 4).text() == "Anulado"


def test_dialogo_pago_no_permite_mas_que_la_deuda(ventana):
    dialogo = ui_cobros.DialogoPago(ventana, "Pegasos", 100000, 100000)
    dialogo.monto.setValue(5000)
    assert dialogo.monto.value() == 1000
    errores = []
    dialogo.monto.setValue(0)
    import dep_leon.ui.pagina_cobros as modulo
    original = modulo.error
    modulo.error = lambda _, m: errores.append(m)
    try:
        dialogo._aceptar()
    finally:
        modulo.error = original
    assert "mayor a cero" in dialogo.error_monto.text() and dialogo.result() == 0


def test_solo_con_adeudo_filtra(ventana, conn, torneo_id, categoria, con_tarifa):
    a, _ = con_tarifa
    cobros.registrar_pago(conn, a, INSCRIPCION, HOY)
    pagina = ventana.cobros
    pagina.filtros.refrescar()
    assert pagina.equipos.rowCount() == 2
    pagina.solo_adeudo.setChecked(True)
    assert pagina.equipos.rowCount() == 1
    assert pagina.equipos.item(0, 0).text() == "Buitres"


def test_pagina_captura_resultados_previos_al_abrir(ventana, conn, torneo_id, categoria, equipos):
    """Resultados capturados antes de existir montos se cobran al ponerlos."""
    a, b = equipos
    resultados.guardar_resultado(conn, crear_partido(conn, torneo_id, categoria, a, b), 1, 0)
    with conn:
        conn.execute(
            "INSERT INTO tarifas (torneo_id, categoria_id, arbitraje, inscripcion) VALUES (?, ?, ?, 0)",
            (torneo_id, categoria, ARBITRAJE),
        )
    ventana.cobros.filtros.refrescar()
    assert ventana.cobros.cargado.numero.text() == "$300.00"


def test_borrar_resultado_pagado_muestra_error(ventana, conn, torneo_id, categoria, con_tarifa, monkeypatch):
    a, b = con_tarifa
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    resultados.guardar_resultado(conn, partido, 1, 0)
    cobros.registrar_pago(conn, a, 100, HOY, primero=arbitrajes(conn, a)[0].id)
    errores = []
    monkeypatch.setattr(ui_resultados, "error", lambda _, m: errores.append(m))
    monkeypatch.setattr(ui_resultados, "confirmar", lambda *a: True)
    pagina = ventana.resultados
    pagina.filtros.refrescar()
    pagina.ver.setCurrentText(ui_resultados.VER_CAPTURADOS)
    pagina.tabla.selectRow(0)
    pagina.borrar()
    assert "pagos" in errores[0]


def test_eliminar_partido_del_rol_quita_cargos_sin_pagos(ventana, conn, torneo_id, categoria, con_tarifa, monkeypatch):
    a, b = con_tarifa
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    resultados.guardar_resultado(conn, partido, 1, 0)
    monkeypatch.setattr(ui_rol, "confirmar", lambda *a: True)
    pagina = ventana.rol
    pagina.refrescar()
    pagina.fecha.setCurrentIndex(0)
    pagina.tabla.selectRow(0)
    pagina.eliminar()
    assert conn.execute("SELECT COUNT(*) FROM partidos").fetchone()[0] == 0
    assert arbitrajes(conn, a) == []


def test_eliminar_partido_con_pagos_se_bloquea(ventana, conn, torneo_id, categoria, con_tarifa, monkeypatch):
    a, b = con_tarifa
    partido = crear_partido(conn, torneo_id, categoria, a, b)
    resultados.guardar_resultado(conn, partido, 1, 0)
    cobros.registrar_pago(conn, a, 100, HOY, primero=arbitrajes(conn, a)[0].id)
    errores = []
    monkeypatch.setattr(ui_rol, "confirmar", lambda *a: True)
    monkeypatch.setattr(ui_rol, "error", lambda _, m: errores.append(m))
    pagina = ventana.rol
    pagina.refrescar()
    pagina.fecha.setCurrentIndex(0)
    pagina.tabla.selectRow(0)
    pagina.eliminar()
    assert "pagos" in errores[0]
    assert conn.execute("SELECT COUNT(*) FROM partidos").fetchone()[0] == 1
    assert len(arbitrajes(conn, b)) == 1


def test_equipo_con_pagos_no_se_borra_y_sin_pagos_si(ventana, conn, torneo_id, categoria, con_tarifa, monkeypatch):
    a, b = con_tarifa
    cobros.registrar_pago(conn, a, 100, HOY)
    errores = []
    monkeypatch.setattr(ui_equipos, "error", lambda _, m: errores.append(m))
    monkeypatch.setattr(ui_equipos, "confirmar", lambda *x: True)
    pagina = ventana.equipos
    pagina.refrescar()
    seleccionar(pagina.tabla_equipos, "Pegasos")
    pagina.borrar_equipo()
    assert "pagos" in errores[0]

    seleccionar(pagina.tabla_equipos, "Buitres")
    pagina.borrar_equipo()
    assert conn.execute("SELECT COUNT(*) FROM equipos WHERE id = ?", (b,)).fetchone()[0] == 0
    assert cobros.cargos_de_equipo(conn, b) == []
