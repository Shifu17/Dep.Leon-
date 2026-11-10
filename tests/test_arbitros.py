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
from dep_leon.ui.avatar import avatar
from dep_leon.ui.estrellas import Estrellas, pixmap_estrellas
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


def _equipos(conn, partido):
    fila = conn.execute("SELECT local_id, visitante_id FROM partidos WHERE id = ?", (partido,)).fetchone()
    return fila["local_id"], fila["visitante_id"]


def test_cada_equipo_califica_con_su_comentario(conn, partido):
    uno = arbitros.guardar(conn, "Árbitro Uno")
    local, visitante = _equipos(conn, partido)
    arbitros.asignar(conn, partido, uno)
    arbitros.calificar(conn, partido, {local: (5, "  Muy   buen control "), visitante: (2, "Llegó tarde")})
    notas = arbitros.notas_de_partido(conn, partido)
    assert (notas[local]["estrellas"], notas[local]["comentario"]) == (5, "Muy buen control")
    assert (notas[visitante]["estrellas"], notas[visitante]["comentario"]) == (2, "Llegó tarde")
    fila = next(f for f in arbitros.resumen(conn) if f["id"] == uno)
    assert (fila["partidos"], fila["calificados"], fila["promedio"]) == (1, 2, 3.5)
    historial = arbitros.historial(conn, uno)
    assert [h["equipo_id"] for h in historial] == [local, visitante]

    # Solo comentario, sin estrellas; y quitar todo borra la opinión de ese equipo.
    arbitros.calificar(conn, partido, {local: (None, "Sin queja"), visitante: (None, "")})
    notas = arbitros.notas_de_partido(conn, partido)
    assert notas[local]["estrellas"] is None and visitante not in notas


def test_calificar_valida(conn, partido, torneo_id, categoria):  # noqa: F811
    uno = arbitros.guardar(conn, "Árbitro Uno")
    local, _ = _equipos(conn, partido)
    with pytest.raises(ValueError, match="elige al árbitro"):
        arbitros.calificar(conn, partido, {local: (4, "")})
    arbitros.asignar(conn, partido, uno)
    ajeno, _ = crear_equipo(conn, torneo_id, categoria, "Ajeno")
    with pytest.raises(ValueError, match="dos equipos"):
        arbitros.calificar(conn, partido, {ajeno: (4, "")})
    with pytest.raises(ValueError, match="200"):
        arbitros.calificar(conn, partido, {local: (4, "x" * 201)})
    for estrellas in (0, 6):
        with pytest.raises(ValueError, match="1 a 5"):
            arbitros.calificar(conn, partido, {local: (estrellas, "")})
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("INSERT INTO calificaciones_arbitro VALUES (?, ?, 6, '')", (partido, local))


def test_cambiar_de_arbitro_quita_las_calificaciones(conn, partido):
    uno, dos = arbitros.guardar(conn, "Árbitro Uno"), arbitros.guardar(conn, "Árbitro Dos")
    local, _ = _equipos(conn, partido)
    arbitros.asignar(conn, partido, uno)
    arbitros.calificar(conn, partido, {local: (3, "Bien")})
    arbitros.asignar(conn, partido, uno)  # el mismo: se conserva
    assert arbitros.notas_de_partido(conn, partido)[local]["estrellas"] == 3
    arbitros.asignar(conn, partido, dos)
    assert arbitros.notas_de_partido(conn, partido) == {}
    arbitros.calificar(conn, partido, {local: (4, "")})
    arbitros.asignar(conn, partido, None)
    assert arbitros.de_partido(conn, partido) is None and arbitros.notas_de_partido(conn, partido) == {}


def test_calificacion_de_la_099_pasa_a_los_dos_equipos(conn, partido):
    uno = arbitros.guardar(conn, "Árbitro Uno")
    arbitros.asignar(conn, partido, uno)
    with conn:  # como quedaba una base de la 0.9.9
        conn.execute("DROP TABLE calificaciones_arbitro")
        conn.execute("ALTER TABLE arbitrajes ADD COLUMN calificacion INTEGER")
        conn.execute("UPDATE arbitrajes SET calificacion = 4")
    ruta = conn.execute("PRAGMA database_list").fetchone()["file"]
    nueva = db.conectar(ruta)
    notas = arbitros.notas_de_partido(nueva, partido)
    assert sorted(n["estrellas"] for n in notas.values()) == [4, 4]
    assert "calificacion" not in {c["name"] for c in nueva.execute("PRAGMA table_info(arbitrajes)")}
    nueva.close()


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
    arbitros.asignar(conn, partido, uno)
    arbitros.calificar(conn, partido, {_equipos(conn, partido)[0]: (5, "")})
    with conn:
        conn.execute("DELETE FROM partidos WHERE id = ?", (partido,))
    assert conn.execute("SELECT COUNT(*) FROM calificaciones_arbitro").fetchone()[0] == 0
    assert arbitros.partidos_dirigidos(conn, uno) == 0


def test_base_anterior_recibe_las_tablas(tmp_path):
    ruta = tmp_path / "vieja.db"
    vieja = db.conectar(ruta)
    with vieja:
        vieja.execute("DROP TABLE calificaciones_arbitro")
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
    arbitros.asignar(conn, partido, uno)
    arbitros.calificar(conn, partido, {_equipos(conn, partido)[0]: (4, "Bien")})
    db.respaldar(conn, tmp_path / "r.zip", fotos)
    otra = db.conectar(tmp_path / "otra.db")
    destino = tmp_path / "fotos2"
    destino.mkdir()
    db.restaurar(otra, tmp_path / "r.zip", destino)
    assert arbitros.notas_de_partido(otra, partido)[_equipos(otra, partido)[0]]["comentario"] == "Bien"
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


def test_capturar_resultado_califica_cada_equipo(ventana, conn, partido):
    uno = arbitros.guardar(conn, "Árbitro Uno")
    local, visitante = _equipos(conn, partido)
    fila = ui_resultados._partido_completo(conn, partido)
    dialogo = ui_resultados.DialogoResultado(ventana, conn, fila, fila["local"], fila["visitante"])
    assert not dialogo.notas[local].isEnabled()  # sin árbitro no se califica
    assert dialogo.notas[local].titulo.text() == "Calificación de Halcones"
    dialogo.arbitro.setCurrentIndex(dialogo.arbitro.findData(uno))
    assert dialogo.notas[local].isEnabled()
    dialogo.notas[local].poner(5, "Muy bien")
    dialogo.notas[visitante].poner(3, "Le faltó marcar faltas")
    dialogo.marcador_local.setValue(1)
    dialogo._aceptar()
    assert dialogo.result() == 1
    notas = arbitros.notas_de_partido(conn, partido)
    assert (notas[local]["estrellas"], notas[visitante]["comentario"]) == (5, "Le faltó marcar faltas")

    # Al volver a abrirlo, aparece lo guardado; con otro árbitro se empieza de cero.
    otra = ui_resultados.DialogoResultado(ventana, conn, fila, fila["local"], fila["visitante"])
    assert otra.notas[local].valores() == (5, "Muy bien")
    otra.arbitro.setCurrentIndex(0)
    assert otra.notas[visitante].valores() == (None, "")
    otra.arbitro.setCurrentIndex(otra.arbitro.findData(uno))
    assert otra.notas[visitante].valores() == (3, "Le faltó marcar faltas")

    ventana.resultados.filtros.refrescar()
    ventana.resultados.ver.setCurrentText(ui_resultados.VER_CAPTURADOS)
    assert ventana.resultados.tabla.item(0, 8).text() == "Árbitro Uno (4.0 de 5)"


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
    local, visitante = _equipos(conn, partido)
    arbitros.asignar(conn, partido, uno)
    arbitros.calificar(conn, partido, {local: (4, ""), visitante: (5, "Excelente trato")})
    resultados.guardar_resultado(conn, partido, 2, 1)
    pagina = ventana.arbitros
    pagina.refrescar()
    assert pagina.tabla.item(0, 0).text() == "Árbitro Uno"
    assert pagina.tabla.item(0, 2).text() == "4.5 de 5"
    assert pagina.ficha.nombre.text() == "Árbitro Uno"
    assert pagina.ficha.valores["partidos"].text() == "1"
    assert pagina.partidos.rowCount() == 2
    assert pagina.partidos.item(0, 1).text() == "Halcones 2-1 Zorros"
    assert [pagina.partidos.item(r, 2).text() for r in range(2)] == ["Halcones", "Zorros"]
    assert pagina.partidos.item(1, 3).text() == "5 de 5"
    assert pagina.partidos.item(1, 4).text() == "Excelente trato"


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
