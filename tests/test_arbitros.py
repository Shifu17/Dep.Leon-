import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sqlite3

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from dep_leon import arbitros, db, resultados, updater
from dep_leon.ui import pagina_arbitros as ui_arbitros
from dep_leon.ui import pagina_resultados as ui_resultados
from dep_leon.ui.estrellas import Estrellas, avatar, pixmap_estrellas
from dep_leon.ui.ventana import Ventana

from test_resultados import categoria, crear_equipo, crear_partido  # noqa: F401 (fixture)


@pytest.fixture
def partido(conn, torneo_id, categoria):  # noqa: F811
    a, (a0,) = crear_equipo(conn, torneo_id, categoria, "Halcones", 1)
    b, _ = crear_equipo(conn, torneo_id, categoria, "Zorros", 1)
    return crear_partido(conn, torneo_id, categoria, a, b)


@pytest.fixture
def ventana(app, conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    resultado = Ventana(conn)
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


def test_registrar_y_validar_nombre(conn):
    uno = arbitros.guardar(conn, "  Árbitro   Uno ", "8440000001")
    assert conn.execute("SELECT nombre FROM arbitros WHERE id = ?", (uno,)).fetchone()[0] == "Árbitro Uno"
    with pytest.raises(ValueError, match="Ya hay"):
        arbitros.guardar(conn, "Árbitro Uno")
    with pytest.raises(ValueError, match="nombre"):
        arbitros.guardar(conn, "   ")


def test_asignar_calificar_y_promediar(conn, partido, torneo_id, categoria):  # noqa: F811
    uno = arbitros.guardar(conn, "Árbitro Uno")
    arbitros.asignar(conn, partido, uno, 4)
    otro_partido = crear_partido(
        conn, torneo_id, categoria,
        *[e["id"] for e in conn.execute("SELECT id FROM equipos ORDER BY id")], hora="10:00",
    )
    arbitros.asignar(conn, otro_partido, uno, 5)
    fila = next(f for f in arbitros.resumen(conn) if f["id"] == uno)
    assert (fila["partidos"], fila["calificados"], fila["promedio"]) == (2, 2, 4.5)
    assert [p["calificacion"] for p in arbitros.historial(conn, uno)] in ([5, 4], [4, 5])


@pytest.mark.parametrize("estrellas", [0, 6])
def test_calificacion_fuera_de_rango(conn, partido, estrellas):
    uno = arbitros.guardar(conn, "Árbitro Uno")
    with pytest.raises(ValueError, match="1 a 5"):
        arbitros.asignar(conn, partido, uno, estrellas)
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("INSERT INTO arbitrajes VALUES (?, ?, ?)", (partido, uno, estrellas))


def test_cambiar_de_arbitro_quita_la_calificacion(conn, partido):
    uno, dos = arbitros.guardar(conn, "Árbitro Uno"), arbitros.guardar(conn, "Árbitro Dos")
    arbitros.asignar(conn, partido, uno, 3)
    arbitros.asignar(conn, partido, uno, conservar_calificacion=True)
    assert arbitros.de_partido(conn, partido)["calificacion"] == 3
    arbitros.asignar(conn, partido, dos, conservar_calificacion=True)
    assert arbitros.de_partido(conn, partido)["calificacion"] is None
    arbitros.asignar(conn, partido, None)
    assert arbitros.de_partido(conn, partido) is None
    with pytest.raises(ValueError, match="elige al árbitro"):
        arbitros.asignar(conn, partido, None, 4)


def test_con_partidos_no_se_borra_pero_se_da_de_baja(conn, partido):
    uno = arbitros.guardar(conn, "Árbitro Uno", foto="foto.jpg")
    arbitros.asignar(conn, partido, uno)
    with pytest.raises(ValueError, match="partidos"):
        arbitros.borrar(conn, uno)
    arbitros.dar_de_baja(conn, uno)
    assert arbitros.para_elegir(conn) == []
    assert [a["id"] for a in arbitros.para_elegir(conn, incluir=uno)] == [uno]
    arbitros.asignar(conn, partido, None)
    assert arbitros.borrar(conn, uno) == "foto.jpg"


def test_borrar_el_partido_borra_su_arbitraje(conn, partido):
    uno = arbitros.guardar(conn, "Árbitro Uno")
    arbitros.asignar(conn, partido, uno, 5)
    with conn:
        conn.execute("DELETE FROM partidos WHERE id = ?", (partido,))
    assert arbitros.partidos_dirigidos(conn, uno) == 0


def test_base_anterior_recibe_las_tablas(tmp_path):
    ruta = tmp_path / "vieja.db"
    vieja = db.conectar(ruta)
    with vieja:
        vieja.execute("DROP TABLE arbitrajes")
        vieja.execute("DROP TABLE arbitros")
    vieja.close()
    conn = db.conectar(ruta)
    assert arbitros.resumen(conn) == []
    conn.close()


def test_respaldo_conserva_arbitros_y_su_foto(conn, partido, tmp_path):
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    Image.new("RGB", (30, 40), "white").save(fotos / "arbitro.jpg")
    uno = arbitros.guardar(conn, "Árbitro Uno", foto="arbitro.jpg")
    arbitros.asignar(conn, partido, uno, 4)
    db.respaldar(conn, tmp_path / "r.zip", fotos)
    otra = db.conectar(tmp_path / "otra.db")
    destino = tmp_path / "fotos2"
    destino.mkdir()
    db.restaurar(otra, tmp_path / "r.zip", destino)
    assert arbitros.de_partido(otra, partido)["calificacion"] == 4
    assert (destino / "arbitro.jpg").exists()
    otra.close()


# --- Interfaz -------------------------------------------------------------------------------------


def test_estrellas_con_mouse_y_teclado(app):
    control = Estrellas()
    control.resize(control.sizeHint())
    cambios = []
    control.cambiada.connect(cambios.append)
    paso = 30 + 8
    QTest.mouseClick(control, Qt.MouseButton.LeftButton, pos=QPoint(4 + paso * 3 + 15, 15))
    assert control.valor() == 4 and control.accessibleDescription() == "4 de 5: Muy bueno"
    QTest.mouseClick(control, Qt.MouseButton.LeftButton, pos=QPoint(4 + paso * 3 + 15, 15))
    assert control.valor() == 0  # tocar la misma la quita
    QTest.keyClick(control, Qt.Key.Key_5)
    QTest.keyClick(control, Qt.Key.Key_Left)
    assert control.valor() == 4
    QTest.keyClick(control, Qt.Key.Key_Delete)
    assert control.valor() == 0 and cambios == [4, 0, 5, 4, 0]


def test_dibujos_no_fallan(app, tmp_path):
    assert not pixmap_estrellas(3.5).isNull()
    assert not avatar(None, "Árbitro Uno").isNull()
    Image.new("RGB", (60, 80), "red").save(tmp_path / "f.jpg")
    assert not avatar(tmp_path / "f.jpg", "Árbitro Uno", 40).isNull()


def test_capturar_resultado_califica_al_arbitro(ventana, conn, partido):
    uno = arbitros.guardar(conn, "Árbitro Uno")
    fila = ui_resultados._partido_completo(conn, partido)
    dialogo = ui_resultados.DialogoResultado(ventana, conn, fila, fila["local"], fila["visitante"])
    assert not dialogo.calificacion.isEnabled()  # sin árbitro no se califica
    dialogo.arbitro.setCurrentIndex(dialogo.arbitro.findData(uno))
    assert dialogo.calificacion.isEnabled()
    dialogo.calificacion.estrellas.setValor(5)
    dialogo.marcador_local.setValue(1)
    dialogo._aceptar()
    assert dialogo.result() == 1
    assert arbitros.de_partido(conn, partido)["calificacion"] == 5

    # Al volver a abrirlo, aparece lo guardado; al quitar el árbitro se borra su calificación.
    otra = ui_resultados.DialogoResultado(ventana, conn, fila, fila["local"], fila["visitante"])
    assert otra.arbitro.currentData() == uno and otra.calificacion.valor() == 5
    otra.arbitro.setCurrentIndex(0)
    assert otra.calificacion.valor() is None
    otra._aceptar()
    assert arbitros.de_partido(conn, partido) is None

    ventana.resultados.filtros.refrescar()
    ventana.resultados.ver.setCurrentText(ui_resultados.VER_CAPTURADOS)
    assert ventana.resultados.tabla.item(0, 8).text() == "-"


def test_asignar_desde_el_rol(ventana, conn, partido, monkeypatch):
    uno = arbitros.guardar(conn, "Árbitro Uno")

    def elegir(dialogo):
        dialogo.arbitro.setCurrentIndex(dialogo.arbitro.findData(uno))
        return True

    monkeypatch.setattr(ui_arbitros.DialogoAsignar, "exec", elegir)
    rol = ventana.rol
    rol.filtros.refrescar()
    rol.fecha.setCurrentIndex(0)
    rol.tabla.selectRow(0)
    rol.asignar_arbitro()
    assert arbitros.de_partido(conn, partido)["id"] == uno
    assert rol.tabla.item(0, 8).text() == "Árbitro Uno"


def test_pagina_muestra_promedio_y_partidos(ventana, conn, partido):
    uno = arbitros.guardar(conn, "Árbitro Uno", "8440000001")
    arbitros.asignar(conn, partido, uno, 4)
    resultados.guardar_resultado(conn, partido, 2, 1)
    pagina = ventana.arbitros
    pagina.refrescar()
    assert pagina.tabla.item(0, 0).text() == "Árbitro Uno"
    assert pagina.tabla.item(0, 2).text() == "4.0 de 5"
    assert pagina.ficha.nombre.text() == "Árbitro Uno"
    assert pagina.ficha.valores["partidos"].text() == "1"
    assert pagina.partidos.item(0, 1).text() == "Halcones vs Zorros"
    assert pagina.partidos.item(0, 2).text() == "2 - 1"
    assert pagina.partidos.item(0, 4).text() == "4 de 5"


def test_eliminar_con_partidos_lo_da_de_baja(ventana, conn, partido, monkeypatch):
    uno = arbitros.guardar(conn, "Árbitro Uno")
    arbitros.asignar(conn, partido, uno)
    monkeypatch.setattr(ui_arbitros, "confirmar", lambda *_: True)
    pagina = ventana.arbitros
    pagina.refrescar()
    pagina.tabla.selectRow(0)
    pagina.borrar()
    assert conn.execute("SELECT activo FROM arbitros WHERE id = ?", (uno,)).fetchone()[0] == 0
    assert pagina.tabla.item(0, 3).text() == "De baja"


def test_guardar_con_foto(ventana, conn, tmp_path, monkeypatch):
    origen = tmp_path / "origen.png"
    Image.new("RGB", (300, 400), "blue").save(origen)

    def llenar(dialogo):
        dialogo.nombre.setText("Árbitro Nuevo")
        dialogo.ruta_foto = origen
        return True

    monkeypatch.setattr(ui_arbitros.DialogoArbitro, "exec", llenar)
    ventana.arbitros.nuevo()
    fila = conn.execute("SELECT * FROM arbitros").fetchone()
    assert fila["nombre"] == "Árbitro Nuevo" and fila["foto"].endswith(".jpg")
    assert (tmp_path / "fotos" / fila["foto"]).exists()


def test_menu_tiene_arbitros_y_atajos_sin_repetir(ventana):
    atajos = [b.toolTip() for b in ventana._navegacion.values() if b.toolTip()]
    assert len(atajos) == len(set(atajos))
    assert ventana._navegacion[ventana.arbitros].text() == "Árbitros"
    assert ventana._navegacion[ventana.config].toolTip() == "Ctrl+0"
