"""Calidad de la interfaz: contraste, foco de teclado, accesibilidad, orden e idioma."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from dep_leon import db, estadisticas, inicio, reportes, rol, updater
from dep_leon.ui import comun, tema
from dep_leon.ui.idioma import instalar_espanol
from dep_leon.ui.ventana import Ventana


def _luminancia(color: str) -> float:
    color = color.lstrip("#")
    canales = [int(color[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    claro, oscuro = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


@pytest.mark.parametrize(
    "frente, fondo",
    [
        (tema.TEXTO, tema.FONDO),
        (tema.TEXTO, tema.BLANCO),
        (tema.TEXTO_SUAVE, tema.FONDO),
        ("#FFFFFF", tema.VERDE),
        ("#FFFFFF", tema.VERDE_ACTIVO),  # botón verde con el mouse encima
        (tema.VERDE_ACTIVO, tema.BLANCO),
        (tema.VERDE_ACTIVO, tema.VERDE_SUAVE),  # botón secundario con el mouse encima
        (tema.ROJO, tema.BLANCO),
        (tema.ROJO, tema.ROJO_SUAVE),
        (tema.TEXTO, tema.VERDE_SUAVE),  # fila seleccionada
        ("#E6EFEA", tema.BARRA),
    ],
)
def test_texto_cumple_contraste_aa(frente, fondo):
    assert contraste(frente, fondo) >= 4.5


@pytest.mark.parametrize(
    "contorno, fondo",
    [
        (tema.BORDE_CONTROL, tema.BLANCO),
        (tema.BORDE_CONTROL, tema.FONDO),
        (tema.BORDE_PELIGRO, tema.BLANCO),
        (tema.VERDE, tema.BLANCO),  # foco en campos y filas seleccionadas
        (tema.BARRA, tema.FONDO),  # foco en botones
        (tema.DORADO, tema.BARRA),  # foco en el menú
    ],
)
def test_contornos_de_control_se_distinguen(contorno, fondo):
    assert contraste(contorno, fondo) >= 3


@pytest.mark.parametrize(
    "crear",
    [
        lambda: QPushButton("Primario"),
        lambda: QPushButton("Secundario", objectName="secundario"),
        lambda: QPushButton("Eliminar", objectName="peligro"),
        lambda: QPushButton("Menú", objectName="nav"),
        lambda: QPushButton("Llave", objectName="llave"),
        lambda: QCheckBox("Casilla"),
        lambda: QRadioButton("Opción"),
    ],
)
def test_el_foco_del_teclado_se_ve(app, crear):
    ventana = QWidget(objectName="contenido")
    disposicion = QVBoxLayout(ventana)
    control, otro = crear(), QPushButton("otro")
    disposicion.addWidget(control)
    disposicion.addWidget(otro)
    ventana.show()
    ventana.activateWindow()
    app.processEvents()

    otro.setFocus(Qt.FocusReason.TabFocusReason)
    app.processEvents()
    sin_foco = control.grab().toImage()
    tamano = control.size()
    control.setFocus(Qt.FocusReason.TabFocusReason)
    app.processEvents()
    con_foco = control.grab().toImage()

    assert control.hasFocus()
    assert con_foco != sin_foco
    assert control.size() == tamano  # el foco no mueve la pantalla
    ventana.close()


def test_boton_toma_foco_con_tab_y_no_con_clic(app):
    assert comun.boton("x", lambda: None).focusPolicy() == Qt.FocusPolicy.TabFocus


@pytest.fixture
def ventana(app, conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    resultado = Ventana(conn)
    resultado.resize(1200, 760)
    resultado.show()
    yield resultado
    resultado.temporizador.stop()
    resultado.close()


def test_todos_los_controles_visibles_tienen_nombre_accesible(ventana, app, conn, torneo_id):
    faltantes = []
    for i in range(ventana.pila.count()):
        pagina = ventana.pila.widget(i)
        ventana.pila.setCurrentWidget(pagina)
        app.processEvents()
        for control in pagina.findChildren(QWidget):
            if (
                control.isVisible()
                and isinstance(control, (QComboBox, QAbstractSpinBox, QTableWidget))
                # Las piezas internas de una lista desplegable pertenecen a la lista.
                and not isinstance(control.parent(), QComboBox)
                and not control.accessibleName()
            ):
                faltantes.append(f"{type(pagina).__name__}: {type(control).__name__}")
    assert faltantes == []


@pytest.mark.parametrize(
    "columna, horizontal",
    [
        ("Equipo", Qt.AlignmentFlag.AlignLeft),
        ("Saldo", Qt.AlignmentFlag.AlignRight),
        ("Pts", Qt.AlignmentFlag.AlignRight),
        ("Marcador", Qt.AlignmentFlag.AlignHCenter),
    ],
)
def test_columna_y_celdas_usan_la_misma_alineacion(app, columna, horizontal):
    tabla_ = comun.tabla([columna])
    comun.llenar(tabla_, [(1, ["x"])])
    assert Qt.AlignmentFlag(tabla_.item(0, 0).textAlignment()) & horizontal
    assert Qt.AlignmentFlag(tabla_.horizontalHeaderItem(0).textAlignment()) & horizontal


def test_clave_de_orden_en_espanol():
    nombres = ["Toros", "Ñandúes", "Águilas", "nogales", "Niupi", "ángeles", "Zorros"]
    assert sorted(nombres, key=db.clave_orden) == [
        "Águilas", "ángeles", "Niupi", "nogales", "Ñandúes", "Toros", "Zorros",
    ]


@pytest.fixture
def categoria(conn, infantil_id):
    return conn.execute(
        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = '2015-2016'", (infantil_id,)
    ).fetchone()["id"]


@pytest.fixture
def equipos(conn, torneo_id, categoria):
    with conn:
        return {
            n: conn.execute(
                "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
                (torneo_id, categoria, n),
            ).lastrowid
            for n in ("Toros", "Águilas", "Ñandúes", "Niupi")
        }


def test_listas_y_tablas_quedan_en_orden_alfabetico(ventana, conn, torneo_id, categoria, equipos):
    pagina = ventana.equipos
    pagina.refrescar()
    orden = [pagina.tabla_equipos.item(f, 0).text() for f in range(pagina.tabla_equipos.rowCount())]
    assert orden == ["Águilas", "Niupi", "Ñandúes", "Toros"]
    # Sin partidos, la tabla de posiciones desempata por nombre.
    tabla_ = estadisticas.tabla_posiciones(conn, torneo_id, categoria)
    assert [f.nombre for f in tabla_] == ["Águilas", "Niupi", "Ñandúes", "Toros"]


def test_torneo_no_repite_la_palabra(conn, infantil_id):
    assert rol.titulo_torneo("Copa de Verano") == "Torneo Copa de Verano"
    assert rol.titulo_torneo("Torneo de Verano") == "Torneo de Verano"
    assert rol.titulo_torneo("TORNEO Clausura") == "TORNEO Clausura"
    with conn:
        t = conn.execute(
            "INSERT INTO torneos (liga_id, nombre) VALUES (?, 'Torneo de Verano')", (infantil_id,)
        ).lastrowid
    assert reportes.hoja_tabla(conn, t).subtitulo == "Torneo de Verano"


def test_estados_sin_fecha_usan_el_mismo_texto(ventana, conn, torneo_id, categoria, equipos):
    with conn:
        partido = conn.execute(
            "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, minutos, estado) "
            "VALUES (?, ?, 1, ?, ?, 50, ?)",
            (torneo_id, categoria, equipos["Toros"], equipos["Niupi"], rol.POR_PROGRAMAR),
        ).lastrowid
    pagina = ventana.rol
    pagina.refrescar()
    pagina.fecha.setCurrentIndex(0)
    fila = [pagina.tabla.item(0, c).text() for c in range(pagina.tabla.columnCount())]
    assert fila[0] == "Sin fecha" and fila[1] == "-" and fila[5] == "-"
    assert pagina.tabla.horizontalHeaderItem(6).text() == "Fase"
    assert fila[6] == "Jornada 1"
    assert partido


def test_qt_queda_en_espanol(app):
    assert instalar_espanol(app)
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "Cancelar"
    assert "Cortar" in QCoreApplication.translate("QWidgetTextControl", "Cu&t").replace("&", "")
    assert comun.etiqueta("Ver:", QWidget()).text() == "Ver:"


def test_inicio_sigue_ordenando_equipos_por_jugar(conn, torneo_id, categoria, equipos):
    from datetime import date

    with conn:
        conn.execute(
            "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, fecha, hora, "
            "minutos, cancha, estado) VALUES (?, ?, 1, ?, ?, '2030-01-05', '09:00', 50, '1', ?)",
            (torneo_id, categoria, equipos["Toros"], equipos["Águilas"], rol.PROGRAMADO),
        )
    _, lista = inicio.equipos_proxima_fecha(conn, date(2030, 1, 1))
    assert [e["equipo"] for e in lista] == ["Águilas", "Toros"]


def test_celdas_muestran_el_texto_completo_al_pasar_el_mouse(app):
    tabla_ = comun.tabla(["Equipo"])
    comun.llenar(tabla_, [(1, ["Deportivo León Blanco de Saltillo"])])
    assert tabla_.item(0, 0).toolTip() == "Deportivo León Blanco de Saltillo"
