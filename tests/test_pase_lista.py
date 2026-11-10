import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from dep_leon import asistencia, resultados, updater
from dep_leon.ui import pagina_lista as ui_lista
from dep_leon.ui.ventana import Ventana

from test_resultados import categoria, crear_equipo, crear_partido  # noqa: F401 (fixture)


@pytest.fixture
def liga(conn, torneo_id, categoria):  # noqa: F811
    """Dos equipos con 2 jugadores, tres partidos jugados; se pasó lista en dos."""
    a, (a1, a2) = crear_equipo(conn, torneo_id, categoria, "Halcones", 2)
    b, (b1, b2) = crear_equipo(conn, torneo_id, categoria, "Zorros", 2)
    partidos = [crear_partido(conn, torneo_id, categoria, a, b, hora=h, jornada=j)
                for j, h in ((1, "09:00"), (2, "10:00"), (3, "11:00"))]
    for p in partidos:
        resultados.guardar_resultado(conn, p, 0, 0)
    asistencia.guardar(conn, partidos[0], {a1, a2, b1})
    asistencia.guardar(conn, partidos[1], {a1, b1})
    return {"a": a, "b": b, "a1": a1, "a2": a2, "b1": b1, "b2": b2, "partidos": partidos}


def test_estadisticas_generales(conn, torneo_id, liga):
    datos = asistencia.estadisticas(conn, torneo_id)
    equipos = {e.nombre: e for e in datos.equipos}
    assert (equipos["Halcones"].con_lista, equipos["Halcones"].asistencias, equipos["Halcones"].porcentaje) == (2, 3, 75)
    assert (equipos["Zorros"].con_lista, equipos["Zorros"].porcentaje) == (2, 50)
    assert (datos.partidos_jugados, datos.partidos_con_lista) == (3, 2)
    assert datos.porcentaje == 62  # 5 asistencias de 8 posibles
    assert datos.perfectos == 2  # a1 y b1
    faltas = {j.jugador_id: j.faltas for j in datos.jugadores}
    assert faltas[liga["b2"]] == 2 and faltas[liga["a2"]] == 1
    assert datos.con_muchas_faltas == []  # nadie llega a 3


def test_sin_lista_no_cuenta_como_falta(conn, torneo_id, categoria):  # noqa: F811
    crear_equipo(conn, torneo_id, categoria, "Nuevos", 3)
    datos = asistencia.estadisticas(conn, torneo_id)
    assert datos.porcentaje is None and datos.perfectos == 0 and datos.con_muchas_faltas == []


@pytest.fixture
def ventana(app, conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    resultado = Ventana(conn)
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


def test_pagina_muestra_cifras_y_cuadricula(ventana, liga):
    pagina = ventana.lista
    pagina.filtros.refrescar()
    assert pagina.general.numero.text() == "62%"
    assert pagina.partidos.numero.text() == "2" and pagina.partidos.detalle.text() == "de 3 partidos jugados"
    assert pagina.tabla_equipos.item(0, 3).text() == "75%"
    assert pagina.cuadricula is not None and pagina.titulo_cuadricula.text() == "Lista de Halcones"
    assert pagina.tabla_partidos.rowCount() == 3


def test_guardar_lista_del_equipo(ventana, conn, liga):
    pagina = ventana.lista
    pagina.filtros.refrescar()
    rejilla = pagina.cuadricula.rejilla
    fila = next(r for r in range(rejilla.rowCount()) if rejilla.item(r, 0).text().endswith("Halcones 1"))
    pagina.cuadricula.alternar(fila, 3)  # J3: ahora sí vino
    assert pagina.aviso_cambios.text() == "Hay cambios sin guardar."
    pagina.guardar()
    assert liga["a2"] in asistencia.presentes(conn, liga["partidos"][2])
    assert pagina.aviso_cambios.text() == ""


def test_cambiar_de_equipo_con_cambios_pregunta(ventana, conn, liga, monkeypatch):
    preguntas = []
    monkeypatch.setattr(ui_lista, "confirmar", lambda _, m: preguntas.append(m) or True)
    pagina = ventana.lista
    pagina.filtros.refrescar()
    pagina.cuadricula.alternar(0, 3)
    pagina.tabla_equipos.selectRow(1)
    assert preguntas == ["No guardaste la lista de «Halcones». ¿Guardarla ahora?"]
    assert pagina.titulo_cuadricula.text() == "Lista de Zorros"
    assert len(asistencia.presentes(conn, liga["partidos"][2])) == 1


def test_por_partido(ventana, liga, monkeypatch):
    abiertos = []
    monkeypatch.setattr(ui_lista, "pasar_lista", lambda _p, _c, partido: abiertos.append(partido["id"]) or True)
    pagina = ventana.lista
    pagina.filtros.refrescar()
    pagina.vista.setCurrentText(ui_lista.POR_PARTIDO)
    assert pagina.pila.currentIndex() == 1
    pagina.tabla_partidos.selectRow(0)
    pagina.pasar_lista_partido()
    assert abiertos and abiertos[0] in liga["partidos"]


def test_ya_no_esta_en_equipos_ni_resultados(ventana):
    assert not hasattr(ventana.equipos, "pase_de_lista")
    assert not hasattr(ventana.resultados, "pase_de_lista")
    assert ventana._navegacion[ventana.lista].text() == "Pase de lista"
