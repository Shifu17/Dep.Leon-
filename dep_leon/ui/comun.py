"""Piezas de interfaz compartidas por las páginas."""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..db import clave_orden
from ..paths import asset


# Texto a la izquierda, cantidades a la derecha y códigos cortos al centro, para leer en columna.
COLUMNAS_DERECHA = {
    "Jugadores", "Goles", "PJ", "PG", "PE", "PP", "GF", "GC", "DG", "Pts", "Cargos", "Pagado",
    "Saldo", "Monto", "Recibidos", "Promedio", "Categorías", "Equipos", "Por jugar", "Jugados",
    "Pospuestos", "Por capturar",
}
COLUMNAS_CENTRO = {"Marcador", "Cancha", "Núm.", "Pos.", "#", "Lugar", "Foto", "Renglón"}


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


def boton(texto: str, al_pulsar, estilo: str | None = None) -> QPushButton:
    resultado = QPushButton(texto)
    # El contorno de foco aparece al usar Tab, no cada vez que se hace clic.
    resultado.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    if estilo:
        resultado.setObjectName(estilo)
    resultado.clicked.connect(al_pulsar)
    return resultado


def tabla(columnas: list[str], estirar: int | None = None, ordenable: bool = True) -> QTableWidget:
    resultado = QTableWidget(0, len(columnas))
    resultado.setHorizontalHeaderLabels(columnas)
    resultado.setAccessibleName("Tabla: " + ", ".join(columnas))
    for i, columna in enumerate(columnas):
        resultado.horizontalHeaderItem(i).setTextAlignment(alineacion_de(columna))
    resultado.setAlternatingRowColors(True)
    resultado.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    resultado.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    resultado.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    resultado.verticalHeader().setVisible(False)
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


def campo_busqueda(tabla_: QTableWidget, ayuda: str, al_cambiar=None, ancho: int = 220) -> QLineEdit:
    campo = QLineEdit()
    campo.setPlaceholderText(ayuda)
    campo.setAccessibleName(ayuda)
    campo.setClearButtonEnabled(True)
    campo.setMinimumWidth(ancho)
    campo.textChanged.connect(al_cambiar or (lambda texto: filtrar(tabla_, texto)))
    return campo


def al_activar(tabla_: QTableWidget, accion) -> None:
    """Doble clic o Enter sobre una fila ejecutan su acción principal."""
    tabla_.doubleClicked.connect(lambda *_: accion())
    for tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        atajo = QShortcut(QKeySequence(tecla), tabla_)
        atajo.setContext(Qt.ShortcutContext.WidgetShortcut)
        atajo.activated.connect(accion)


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
