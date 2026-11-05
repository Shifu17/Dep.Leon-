"""Piezas de interfaz compartidas por las páginas."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


# Texto a la izquierda, cantidades a la derecha y códigos cortos al centro, para leer en columna.
COLUMNAS_DERECHA = {
    "Jugadores", "Goles", "PJ", "PG", "PE", "PP", "GF", "GC", "DG", "Pts", "Cargos", "Pagado",
    "Saldo", "Monto", "Recibidos", "Promedio", "Categorías", "Equipos", "Por jugar", "Jugados",
    "Pospuestos",
}
COLUMNAS_CENTRO = {"Marcador", "Cancha", "Núm.", "Pos.", "#", "Lugar", "Foto", "Renglón"}


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


def tabla(columnas: list[str], estirar: int | None = None) -> QTableWidget:
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
    return resultado


def llenar(tabla_: QTableWidget, filas: list[tuple[int, list]]) -> None:
    """Llena la tabla con (id, valores) y conserva la selección si el renglón sigue existiendo."""
    seleccion = id_seleccionado(tabla_)
    tabla_.blockSignals(True)
    tabla_.clearSelection()
    tabla_.setRowCount(len(filas))
    for r, (identificador, valores) in enumerate(filas):
        for c, valor in enumerate(valores):
            celda = QTableWidgetItem("" if valor is None else str(valor))
            celda.setTextAlignment(Qt.AlignmentFlag(tabla_.horizontalHeaderItem(c).textAlignment()))
            # Si un nombre largo no cabe, se puede leer completo al pasar el mouse.
            celda.setToolTip(celda.text())
            celda.setData(Qt.ItemDataRole.UserRole, identificador)
            tabla_.setItem(r, c, celda)
        if identificador == seleccion:
            tabla_.selectRow(r)
    tabla_.blockSignals(False)


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
