import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date

import pytest
from PIL import Image
from PySide6.QtCore import Qt

from dep_leon import colores, updater
from dep_leon.jugadores import faltantes, motivo_no_elegible, rango_anios
from dep_leon.ui import pagina_equipos as ui_equipos
from dep_leon.ui.ventana import Ventana


def test_elegibilidad_por_anio():
    assert motivo_no_elegible(date(1984, 5, 1), 2009, 2010) == "Nació en 1984, la categoría permite 2009–2010."
    assert motivo_no_elegible(date(2013, 1, 1), 2012, 2012) == "Nació en 2013, la categoría permite 2012."
    assert motivo_no_elegible(date(2009, 12, 31), 2009, 2010) is None
    assert motivo_no_elegible(date(1984, 5, 1), None, None) is None  # categoría libre: no se valida
    assert rango_anios(None, None) == "Sin límite"


def test_lo_que_falta_al_expediente():
    completo = {"curp": "XXXX150301HCLXXX01", "foto": "a.jpg", "numero": 7}
    assert faltantes(completo) == []
    assert faltantes({"curp": "", "foto": "", "numero": None}) == ["CURP", "foto", "número"]
    assert faltantes({**completo, "numero": 0}) == []  # el 0 es un número válido


@pytest.fixture
def ventana(app, conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    resultado = Ventana(conn)
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


@pytest.fixture
def equipo(conn, torneo_id, infantil_id, tmp_path):
    categoria = conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2015-2016'", (infantil_id,)
    ).fetchone()[0]
    (tmp_path / "fotos").mkdir(exist_ok=True)
    Image.new("RGB", (30, 40), "white").save(tmp_path / "fotos" / "f.jpg")
    with conn:
        equipo_id = conn.execute(
            "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, 'Pumas')", (torneo_id, categoria)
        ).lastrowid
        conn.executemany(
            "INSERT INTO jugadores (equipo_id, nombre, fecha_nacimiento, numero, curp, foto) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (equipo_id, "Completo Uno", "2015-03-01", 1, "XXXX150301HCLXXX01", "f.jpg"),
                (equipo_id, "Sin Datos", "2016-03-01", None, "", ""),
                (equipo_id, "Mayor Tres", "1984-03-01", 3, "XXXX840301HCLXXX03", "f.jpg"),
            ],
        )
    return equipo_id


def _fila(tabla, nombre):
    return next(r for r in range(tabla.rowCount()) if tabla.item(r, 2).text() == nombre)


def test_avisos_y_elegibilidad(ventana, equipo):
    pagina = ventana.equipos
    pagina.refrescar()
    tabla = pagina.tabla_jugadores
    assert tabla.rowCount() == 3

    completo = _fila(tabla, "Completo Uno")
    assert tabla.item(completo, 6).toolTip() == "Expediente completo"
    assert tabla.item(completo, 6).icon().isNull()
    assert not tabla.item(completo, 0).icon().isNull()  # foto redonda

    incompleto = _fila(tabla, "Sin Datos")
    assert tabla.item(incompleto, 6).toolTip() == "Le falta: CURP, foto, número."
    assert not tabla.item(incompleto, 0).icon().isNull()  # iniciales

    mayor = _fila(tabla, "Mayor Tres")
    assert tabla.item(mayor, 6).toolTip() == "Nació en 1984, la categoría permite 2015–2016."
    assert tabla.item(mayor, 3).foreground().color().name().upper() == colores.ROJO


def test_solo_incompletos(ventana, equipo):
    pagina = ventana.equipos
    pagina.refrescar()
    tabla = pagina.tabla_jugadores
    pagina.solo_incompletos.setChecked(True)
    visibles = [tabla.item(r, 2).text() for r in range(tabla.rowCount()) if not tabla.isRowHidden(r)]
    assert visibles == ["Sin Datos"]
    pagina.solo_incompletos.setChecked(False)
    assert sum(not tabla.isRowHidden(r) for r in range(tabla.rowCount())) == 3


def test_numero_se_edita_en_la_celda(ventana, equipo, conn, app, monkeypatch):
    errores = []
    monkeypatch.setattr(ui_equipos, "error", lambda _, m: errores.append(m))
    pagina = ventana.equipos
    pagina.refrescar()
    tabla = pagina.tabla_jugadores
    fila = _fila(tabla, "Sin Datos")
    delegado = tabla.itemDelegateForColumn(1)
    indice = tabla.model().index(fila, 1)
    editor = delegado.createEditor(tabla.viewport(), None, indice)
    delegado.setEditorData(editor, indice)
    assert editor.value() == -1  # «Sin número»

    editor.setValue(3)  # ya lo tiene «Mayor Tres»
    delegado.setModelData(editor, tabla.model(), indice)
    app.processEvents()
    assert errores == ["El número 3 ya lo tiene otro jugador de este equipo."]
    assert conn.execute("SELECT numero FROM jugadores WHERE nombre = 'Sin Datos'").fetchone()[0] is None

    editor.setValue(9)
    delegado.setModelData(editor, tabla.model(), indice)
    app.processEvents()
    assert conn.execute("SELECT numero FROM jugadores WHERE nombre = 'Sin Datos'").fetchone()[0] == 9
    assert tabla.item(_fila(tabla, "Sin Datos"), 1).text() == "9"


def test_doble_clic_en_numero_edita_y_en_otra_columna_abre_el_formulario(ventana, equipo, monkeypatch):
    abiertos = []
    pagina = ventana.equipos
    monkeypatch.setattr(pagina, "editar_jugador", lambda: abiertos.append(True))
    pagina.refrescar()
    tabla = pagina.tabla_jugadores
    tabla.selectRow(0)
    pagina._doble_clic_jugador(tabla.model().index(0, 2))
    assert abiertos == [True]
    ventana.show()
    pagina._doble_clic_jugador(tabla.model().index(0, 1))
    assert tabla.state() == tabla.State.EditingState and abiertos == [True]


# --- Fase 3: tarjeta, lista de equipos y acciones -------------------------------------------------


def test_tarjeta_resume_expedientes_y_atenua_vacios(ventana, equipo):
    pagina = ventana.equipos
    pagina.refrescar()
    tarjeta = pagina.datos_equipo
    assert tarjeta.resumen.text() == "3 jugadores · 2 con foto · 2 con CURP"
    assert tarjeta.avance.value() == 67  # 2 de 3 con foto, CURP y número
    assert tarjeta.avance_texto.text() == "67% con expediente completo"
    vacio = tarjeta.valores["asistente"]
    assert vacio.text() == "Sin dato" and vacio.objectName() == "datoVacio"
    assert tarjeta.valores["club"].objectName() == "datoValor"


def test_lista_de_equipos_con_porcentaje(ventana, equipo, conn, torneo_id):
    with conn:
        conn.execute("INSERT INTO equipos (torneo_id, categoria_id, nombre) "
                     "SELECT torneo_id, categoria_id, 'Vacío' FROM equipos WHERE id = ?", (equipo,))
    pagina = ventana.equipos
    pagina.refrescar()
    tabla = pagina.tabla_equipos
    filas = {tabla.item(r, 0).text(): r for r in range(tabla.rowCount())}
    assert tabla.item(filas["Pumas"], 3).text() == "67%"
    assert tabla.item(filas["Vacío"], 3).text() == "-"
    assert not tabla.item(filas["Pumas"], 0).icon().isNull()  # iniciales del club


def test_iconos_en_la_fila_elegida(ventana, equipo, monkeypatch):
    from PySide6.QtWidgets import QPushButton

    pagina = ventana.equipos
    llamadas = []
    pagina.acciones_jugador.acciones = [
        ("editar", "Editar jugador", lambda: llamadas.append("editar"), "secundario"),
        ("eliminar", "Eliminar jugador", lambda: llamadas.append("eliminar"), "peligro"),
    ]
    pagina.refrescar()
    tabla = pagina.tabla_jugadores
    assert all(tabla.cellWidget(r, 7) is None for r in range(tabla.rowCount()))
    tabla.selectRow(1)
    botones = tabla.cellWidget(1, 7).findChildren(QPushButton)
    assert [b.accessibleName() for b in botones] == ["Editar jugador", "Eliminar jugador"]
    botones[1].click()
    assert llamadas == ["eliminar"]
    tabla.selectRow(2)
    assert tabla.cellWidget(1, 7) is None and tabla.cellWidget(2, 7) is not None
    assert tabla.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_menu_acciones_agrupa_excel_y_credenciales(ventana, monkeypatch):
    pagina = ventana.equipos
    llamadas = []
    for nombre in ("importar_excel", "exportar_registro", "exportar_todos", "generar_credenciales"):
        monkeypatch.setattr(pagina, nombre, lambda n=nombre: llamadas.append(n))
    menu = pagina.boton_acciones.menu()
    acciones = {a.text(): a for a in menu.actions() if a.text()}
    acciones["Importar Excel..."].trigger()
    acciones["Credenciales PDF..."].trigger()
    for sub in acciones["Exportar Excel"].menu().actions():
        sub.trigger()
    assert llamadas == ["importar_excel", "generar_credenciales", "exportar_registro", "exportar_todos"]


def test_credenciales_avisan_lo_que_falta(ventana, equipo, monkeypatch):
    preguntas = []
    monkeypatch.setattr(ui_equipos, "confirmar", lambda _, m: preguntas.append(m) or False)
    monkeypatch.setattr(ui_equipos.QFileDialog, "getSaveFileName",
                        lambda *a, **k: pytest.fail("no debió pedir dónde guardar"))
    pagina = ventana.equipos
    pagina.refrescar()
    pagina.generar_credenciales()
    assert preguntas and preguntas[0].startswith("1 jugador no tiene foto y 1 jugador no tiene CURP.")
