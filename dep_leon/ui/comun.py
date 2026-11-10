"""Piezas de interfaz compartidas por las páginas."""

import re

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from . import diseno
from ..db import clave_orden
from ..paths import asset


# Texto a la izquierda, cantidades a la derecha y códigos cortos al centro, para leer en columna.
COLUMNAS_DERECHA = {
    "Jugadores", "Goles", "PJ", "PG", "PE", "PP", "GF", "GC", "DG", "Pts", "Cargos", "Pagado",
    "Saldo", "Monto", "Recibidos", "Promedio", "Categorías", "Equipos", "Por jugar", "Jugados",
    "Pospuestos", "Por capturar",
}
COLUMNAS_CENTRO = {
    "Marcador", "Cancha", "Núm.", "Pos.", "#", "Lugar", "Foto", "Renglón", "Asistencias", "Total", "Listos",
    "Con error",
}


class _Logo(QLabel):
    """El escudo, redibujado a la escala del monitor donde está la ventana para que se vea nítido."""

    def __init__(self, ancho: int, alto: int):
        super().__init__(alignment=Qt.AlignmentFlag.AlignCenter)
        self._caja = QSize(ancho, alto)
        self._escala = 0.0
        self.setAccessibleName("Escudo de Deportivo León, Saltillo A.C.")
        pantalla = QGuiApplication.primaryScreen()
        self._dibujar(pantalla.devicePixelRatio() if pantalla else 1.0)

    def _dibujar(self, escala: float):
        if escala == self._escala:
            return
        self._escala = escala
        imagen = QPixmap(str(asset("logo.png"))).scaled(
            self._caja * escala, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        imagen.setDevicePixelRatio(escala)
        self.setPixmap(imagen)

    def event(self, evento: QEvent) -> bool:
        if evento.type() in (QEvent.Type.Show, QEvent.Type.DevicePixelRatioChange):
            self._dibujar(self.devicePixelRatioF())
        return super().event(evento)


def logo(ancho: int, alto: int) -> QLabel:
    """El escudo completo, ajustado a la caja dada."""
    return _Logo(ancho, alto)


_NUMERO = re.compile(r"^[+\-]?\$?[\d,]+(\.\d+)?$")
_FECHA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_HORA = re.compile(r"^(\d{2}):(\d{2})$")
_SIN_DATO = {"", "-", "Sin fecha"}


def clave_de_celda(texto: str) -> tuple:
    """Ordena por el valor real: 10 después de 9, y fechas por año. Lo vacío siempre va al final."""
    if texto in _SIN_DATO:
        return (2, 0, "")
    if m := _FECHA.match(texto):
        return (0, int(m[3] + m[2] + m[1]), "")
    if m := _HORA.match(texto):
        return (0, int(m[1] + m[2]), "")
    if _NUMERO.match(texto):
        return (0, float(texto.replace("$", "").replace(",", "")), "")
    return (1, 0, clave_orden(texto))


class _Celda(QTableWidgetItem):
    def __lt__(self, otra):
        return clave_de_celda(self.text()) < clave_de_celda(otra.text())


def alineacion_de(columna: str) -> Qt.AlignmentFlag:
    if columna in COLUMNAS_DERECHA:
        horizontal = Qt.AlignmentFlag.AlignRight
    elif columna in COLUMNAS_CENTRO:
        horizontal = Qt.AlignmentFlag.AlignHCenter
    else:
        horizontal = Qt.AlignmentFlag.AlignLeft
    return horizontal | Qt.AlignmentFlag.AlignVCenter


def etiqueta(texto: str, control: QWidget) -> QLabel:
    """Etiqueta ligada a su control, para que un lector de pantalla los anuncie juntos."""
    resultado = QLabel(texto)
    resultado.setBuddy(control)
    control.setAccessibleName(texto.rstrip(":"))
    return resultado


class AvisoCampo(QLabel):
    """Mensaje de error junto al campo que lo causa; se borra en cuanto se corrige.

    Sin campo, sirve para errores que involucran varios datos, al pie del formulario.
    """

    def __init__(self, campo: QWidget | None = None):
        super().__init__(objectName="errorCampo", wordWrap=True)
        self.campo = campo
        self.setVisible(False)
        if campo is not None:
            for senal in ("textEdited", "dateChanged", "timeChanged", "valueChanged", "currentIndexChanged"):
                if hasattr(campo, senal):
                    getattr(campo, senal).connect(self.limpiar)

    def _marcar(self, invalido: bool):
        if self.campo is not None:
            self.campo.setProperty("invalido", invalido)
            self.campo.setAccessibleDescription(self.text() if invalido else "")
            self.campo.style().unpolish(self.campo)
            self.campo.style().polish(self.campo)

    def mostrar(self, texto: str):
        self.setText(texto)
        self.setVisible(True)
        self._marcar(True)
        if self.campo is not None:
            self.campo.setFocus()

    def limpiar(self, *_):
        if self.isVisible():
            self.setVisible(False)
            self._marcar(False)


def fila_con_error(forma, titulo: str, campo: QWidget) -> AvisoCampo:
    forma.addRow(titulo, campo)
    aviso = AvisoCampo(campo)
    forma.addRow(aviso)
    return aviso


def listo(widget: QWidget, texto: str) -> None:
    """Confirma en la barra inferior de la ventana que algo se guardó, sin interrumpir con un mensaje."""
    ventana = widget.window()
    barra = getattr(ventana, "statusBar", None)
    if callable(barra):
        barra().showMessage(f"Listo: {texto}", 6000)


def ayuda_pagina(texto: str) -> QLabel:
    """Una línea bajo el título que dice para qué sirve la pantalla y por dónde empezar."""
    return QLabel(texto, objectName="ayudaPagina", wordWrap=True)


def boton_mas(texto: str, acciones: list[tuple[str, object]]) -> QPushButton:
    """Agrupa acciones poco frecuentes o delicadas para no saturar la pantalla de botones."""
    resultado = QPushButton(texto, objectName="mas")
    resultado.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    menu = QMenu(resultado)
    for nombre, accion in acciones:
        menu.addAction(nombre).triggered.connect(lambda _=False, a=accion: a())
    resultado.setMenu(menu)
    return resultado


def poner_vacio(tabla_: QTableWidget, texto: str, accion=None, texto_boton: str = "") -> None:
    """Texto que orienta cuando la tabla no tiene filas, en lugar de un rectángulo en blanco.

    Con `accion`, abajo del texto aparece un botón para crear el primer registro.
    """
    if not hasattr(tabla_, "_vacio"):
        tabla_._vacio = QLabel(objectName="vacio", wordWrap=True, alignment=Qt.AlignmentFlag.AlignCenter)
        tabla_._vacio_boton = None
        disposicion = QVBoxLayout(tabla_.viewport())
        disposicion.setContentsMargins(24, 24, 24, 24)
        disposicion.addStretch(1)
        disposicion.addWidget(tabla_._vacio)  # a todo lo ancho, para que el texto pueda partirse
        tabla_._vacio_disposicion = disposicion
        disposicion.addStretch(1)
    if accion and tabla_._vacio_boton is None:
        tabla_._vacio_boton = boton(texto_boton or "Agregar", accion, "secundario")
        tabla_._vacio_disposicion.insertWidget(2, tabla_._vacio_boton, 0, Qt.AlignmentFlag.AlignHCenter)
    tabla_._vacio_texto = texto
    actualizar_vacio(tabla_)


def menu_de_fila(tabla_: QTableWidget, acciones: list[tuple[str, object]]) -> None:
    """Clic derecho sobre una fila: la elige y ofrece sus acciones (Editar, Eliminar...)."""
    tabla_.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def mostrar(posicion):
        fila = tabla_.rowAt(posicion.y())
        if fila < 0:
            return
        tabla_.selectRow(fila)
        menu = QMenu(tabla_)
        for nombre, accion in acciones:
            menu.addAction(nombre).triggered.connect(lambda _=False, a=accion: a())
        menu.exec(tabla_.viewport().mapToGlobal(posicion))

    tabla_.customContextMenuRequested.connect(mostrar)


class AccionesDeFila:
    """Botones con icono (Editar, Eliminar...) que aparecen solo en la fila elegida de la tabla.

    `acciones` es una lista de (icono, texto, función, estilo). Llamar `colocar()` después de volver a
    llenar la tabla, porque al llenarla se quitan.
    """

    def __init__(self, tabla_: QTableWidget, columna: int, acciones):
        self.tabla = tabla_
        self.columna = columna
        self.acciones = acciones
        self._fila: int | None = None
        tabla_.itemSelectionChanged.connect(self.colocar)
        tabla_.horizontalHeader().sortIndicatorChanged.connect(lambda *_: self.colocar())
        ancho = len(acciones) * 34 + 2
        tabla_.horizontalHeader().setSectionResizeMode(columna, QHeaderView.ResizeMode.Fixed)
        tabla_.setColumnWidth(columna, ancho)

    def _botones(self) -> QWidget:
        caja = QWidget()
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(2, 0, 2, 0)
        fila.setSpacing(4)
        for icono, texto, accion, estilo in self.acciones:
            control = QPushButton(objectName="icono" if estilo != "peligro" else "iconoPeligro")
            control.setIcon(diseno.icono(icono, diseno.color_icono_de(estilo or "secundario")))
            control.setIconSize(QSize(16, 16))
            control.setFixedSize(30, 28)
            control.setToolTip(texto)
            control.setAccessibleName(texto)
            control.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            control.clicked.connect(lambda _=False, a=accion: a())
            fila.addWidget(control)
        return caja

    def colocar(self) -> None:
        if self._fila is not None and self._fila < self.tabla.rowCount():
            self.tabla.removeCellWidget(self._fila, self.columna)
        for r in range(self.tabla.rowCount()):
            self.tabla.removeCellWidget(r, self.columna)
        fila = self.tabla.currentRow() if self.tabla.selectedItems() else -1
        self._fila = fila if fila >= 0 else None
        if self._fila is not None:
            self.tabla.setCellWidget(self._fila, self.columna, self._botones())


def boton_opciones(acciones: list[tuple[str, object]], de: str) -> QPushButton:
    """Botón de tres puntos con las acciones de la fila elegida; ocupa poco y siempre cabe en una fila."""
    resultado = boton_mas("Más", acciones)
    resultado.setIcon(diseno.icono("opciones", diseno.color_icono_de("secundario"), aire=6))
    resultado.setIconSize(QSize(22, 16))
    resultado.setAccessibleName(f"Más acciones de {de}")
    resultado.setToolTip(f"Editar o eliminar {de} (también con clic derecho en la fila)")
    return resultado


def actualizar_vacio(tabla_: QTableWidget) -> None:
    if not hasattr(tabla_, "_vacio"):
        return
    visibles = sum(not tabla_.isRowHidden(r) for r in range(tabla_.rowCount()))
    if tabla_.rowCount() == 0:
        tabla_._vacio.setText(tabla_._vacio_texto)
    else:
        tabla_._vacio.setText("Ninguna fila coincide con la búsqueda.")
    tabla_._vacio.setVisible(visibles == 0)
    if tabla_._vacio_boton is not None:
        tabla_._vacio_boton.setVisible(tabla_.rowCount() == 0)


def boton(texto: str, al_pulsar, estilo: str | None = None, icono: str | None = None) -> QPushButton:
    """Botón redondeado; si su verbo tiene icono (Agregar, Editar, Importar...), lo lleva."""
    resultado = QPushButton(texto)
    # El contorno de foco aparece al usar Tab, no cada vez que se hace clic.
    resultado.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    if estilo:
        resultado.setObjectName(estilo)
    nombre_icono = icono or diseno.icono_de_boton(texto)
    if nombre_icono:
        resultado.setIcon(diseno.icono(nombre_icono, diseno.color_icono_de(estilo), aire=6))
        resultado.setIconSize(QSize(22, 16))
    resultado.clicked.connect(al_pulsar)
    return resultado


def tabla(columnas: list[str], estirar: int | None = None, ordenable: bool = True) -> QTableWidget:
    resultado = QTableWidget(0, len(columnas))
    resultado.setHorizontalHeaderLabels(columnas)
    resultado.setAccessibleName("Tabla: " + ", ".join(columnas))
    for i, columna in enumerate(columnas):
        resultado.horizontalHeaderItem(i).setTextAlignment(alineacion_de(columna))
    resultado.setAlternatingRowColors(True)
    resultado.setShowGrid(False)  # sin rejilla: los renglones alternos bastan para seguir la línea
    resultado.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    resultado.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    resultado.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    resultado.verticalHeader().setVisible(False)
    resultado.verticalHeader().setDefaultSectionSize(34)  # renglones cómodos de leer y de atinar
    diseno.sombra(resultado)
    encabezado = resultado.horizontalHeader()
    encabezado.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    encabezado.setSectionResizeMode(
        len(columnas) - 1 if estirar is None else estirar, QHeaderView.ResizeMode.Stretch
    )
    if ordenable:
        # Sin columna elegida se respeta el orden original hasta que se pulse un encabezado.
        encabezado.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        resultado.setSortingEnabled(True)
        # El indicador de Qt reserva espacio en todas las columnas y recorta los nombres.
        encabezado.setSortIndicatorShown(False)
        encabezado.sortIndicatorChanged.connect(lambda seccion, orden: _marcar_orden(resultado, seccion, orden))
    return resultado


def _marcar_orden(tabla_: QTableWidget, seccion: int, orden: Qt.SortOrder) -> None:
    archivo = "flecha_arriba.png" if orden == Qt.SortOrder.AscendingOrder else "flecha.png"
    for c in range(tabla_.columnCount()):
        tabla_.horizontalHeaderItem(c).setIcon(QIcon(str(asset(archivo))) if c == seccion else QIcon())


def llenar(tabla_: QTableWidget, filas: list[tuple[int, list]]) -> None:
    """Llena la tabla con (id, valores) y conserva la selección si el renglón sigue existiendo."""
    seleccion = id_seleccionado(tabla_)
    ordenable = tabla_.isSortingEnabled()
    tabla_.setSortingEnabled(False)  # con el orden activo, las filas cambiarían de lugar al llenarlas
    tabla_.blockSignals(True)
    tabla_.clearSelection()
    tabla_.setRowCount(len(filas))
    for r, (identificador, valores) in enumerate(filas):
        for c, valor in enumerate(valores):
            celda = _Celda("" if valor is None else str(valor))
            celda.setTextAlignment(Qt.AlignmentFlag(tabla_.horizontalHeaderItem(c).textAlignment()))
            # Si un nombre largo no cabe, se puede leer completo al pasar el mouse.
            celda.setToolTip(celda.text())
            celda.setData(Qt.ItemDataRole.UserRole, identificador)
            tabla_.setItem(r, c, celda)
        if identificador == seleccion:
            tabla_.selectRow(r)
    tabla_.setSortingEnabled(ordenable)
    tabla_.horizontalHeader().setSortIndicatorShown(False)  # Qt lo reactiva al activar el orden
    tabla_.blockSignals(False)
    filtrar(tabla_, *getattr(tabla_, "_busqueda", ("", None)))


def filtrar(tabla_: QTableWidget, texto: str, ids: set | None = None) -> None:
    """Oculta las filas sin coincidencia, sin distinguir acentos ni mayúsculas.

    Con ids, también conserva esas filas, por ejemplo equipos con un jugador que coincide.
    """
    tabla_._busqueda = (texto, ids)
    buscado = clave_orden(texto.strip())
    for r in range(tabla_.rowCount()):
        celdas = [tabla_.item(r, c) for c in range(tabla_.columnCount())]
        coincide = not buscado or any(c and buscado in clave_orden(c.text()) for c in celdas)
        if not coincide and ids and celdas[0]:
            coincide = celdas[0].data(Qt.ItemDataRole.UserRole) in ids
        tabla_.setRowHidden(r, not coincide)
    fila = tabla_.currentRow()
    if tabla_.selectedItems() and fila >= 0 and tabla_.isRowHidden(fila):
        tabla_.clearSelection()  # las acciones no deben caer sobre una fila que ya no se ve
    actualizar_vacio(tabla_)


def campo_busqueda(tabla_: QTableWidget, ayuda: str, al_cambiar=None, ancho: int = 220) -> QLineEdit:
    campo = QLineEdit()
    campo.setPlaceholderText(ayuda)
    campo.setAccessibleName(ayuda)
    campo.setClearButtonEnabled(True)
    campo.setMinimumWidth(ancho)
    campo.textChanged.connect(al_cambiar or (lambda texto: filtrar(tabla_, texto)))
    return campo


def al_activar(tabla_: QTableWidget, accion, doble_clic=None) -> None:
    """Doble clic o Enter sobre una fila ejecutan su acción principal.

    Con `doble_clic`, el doble clic recibe la celda tocada y decide (por ejemplo, editar ahí mismo).
    """
    if doble_clic:
        tabla_.doubleClicked.connect(doble_clic)
    else:
        tabla_.doubleClicked.connect(lambda *_: accion())
    for tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        atajo = QShortcut(QKeySequence(tecla), tabla_)
        atajo.setContext(Qt.ShortcutContext.WidgetShortcut)
        atajo.activated.connect(accion)


def id_seleccionado_en(tabla_: QTableWidget, fila: int):
    """El id guardado en un renglón de la tabla, esté elegido o no."""
    celda = tabla_.item(fila, 0)
    return None if celda is None else celda.data(Qt.ItemDataRole.UserRole)


def id_seleccionado(tabla_: QTableWidget) -> int | None:
    fila = tabla_.currentRow() if tabla_.selectedItems() else -1
    if fila < 0 or tabla_.item(fila, 0) is None:
        return None
    return tabla_.item(fila, 0).data(Qt.ItemDataRole.UserRole)


def botones_dialogo(dialogo: QDialog, al_aceptar, texto: str = "Guardar") -> QDialogButtonBox:
    caja = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    )
    caja.button(QDialogButtonBox.StandardButton.Save).setText(texto)
    cancelar = caja.button(QDialogButtonBox.StandardButton.Cancel)
    cancelar.setText("Cancelar")
    cancelar.setObjectName("secundario")
    caja.accepted.connect(al_aceptar)
    caja.rejected.connect(dialogo.reject)
    return caja


def error(padre: QWidget, mensaje: str) -> None:
    QMessageBox.warning(padre, "Deportivo León", mensaje)


def info(padre: QWidget, mensaje: str) -> None:
    QMessageBox.information(padre, "Deportivo León", mensaje)


def confirmar(padre: QWidget, mensaje: str) -> bool:
    caja = QMessageBox(QMessageBox.Icon.Question, "Deportivo León", mensaje, parent=padre)
    si = caja.addButton("Sí", QMessageBox.ButtonRole.YesRole)
    no = caja.addButton("No", QMessageBox.ButtonRole.NoRole)
    caja.setDefaultButton(no)
    caja.exec()
    return caja.clickedButton() is si
