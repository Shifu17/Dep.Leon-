"""Controles de selección más rápidos que una lista desplegable.

- `Segmentado`: pocas opciones (2 a 4) a la vista; se elige con un solo clic.
- `SelectorFecha`: una lista de fechas con flechas para ir a la anterior o a la siguiente sin abrirla.
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QComboBox, QHBoxLayout, QPushButton, QStyledItemDelegate, QWidget

from .. import colores
from . import diseno


ROL_DETALLE = Qt.ItemDataRole.UserRole + 1


class _DelegadoDetalle(QStyledItemDelegate):
    """En la lista abierta, cada opción lleva su detalle: «Infantil · Viernes y sábado»."""

    def initStyleOption(self, opcion, indice):  # noqa: N802 (nombre de Qt)
        super().initStyleOption(opcion, indice)
        detalle = indice.data(ROL_DETALLE)
        if detalle:
            opcion.text = f"{opcion.text}   ·   {detalle}"


def con_detalle(combo: QComboBox) -> QComboBox:
    """La lista abierta muestra el detalle de cada opción; ya elegida, solo su nombre."""
    combo.setItemDelegate(_DelegadoDetalle(combo))
    return combo


def ajustar_combo(combo: QComboBox, letras: int = 6) -> QComboBox:
    """La lista se puede angostar sin cortar la ventana; el texto completo se ve al abrirla."""
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(letras)
    combo.setMaxVisibleItems(12)
    return combo


class Segmentado(QWidget):
    """Botones unidos, uno elegido a la vez. Se usa como una lista de pocas opciones."""

    currentIndexChanged = Signal(int)  # noqa: N815 (igual que QComboBox, para usarlo en su lugar)

    def __init__(self, opciones: list[str], nombre: str = "", padre=None):
        super().__init__(padre)
        self._grupo = QButtonGroup(self, exclusive=True)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(0)
        for i, texto in enumerate(opciones):
            control = QPushButton(texto, objectName="segmento", checkable=True)
            posicion = "solo" if len(opciones) == 1 else "inicio" if i == 0 else "fin" if i == len(opciones) - 1 else "medio"
            control.setProperty("posicion", posicion)
            control.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            control.setAccessibleName(f"{nombre}: {texto}" if nombre else texto)
            self._grupo.addButton(control, i)
            fila.addWidget(control)
        self._grupo.button(0).setChecked(True)
        self._grupo.idToggled.connect(lambda i, marcado: marcado and self.currentIndexChanged.emit(i))

    def currentIndex(self) -> int:  # noqa: N802
        return self._grupo.checkedId()

    def currentText(self) -> str:  # noqa: N802
        return self._grupo.checkedButton().text()

    def setCurrentIndex(self, indice: int) -> None:  # noqa: N802
        self._grupo.button(indice).setChecked(True)

    def setCurrentText(self, texto: str) -> None:  # noqa: N802
        for control in self._grupo.buttons():
            if control.text() == texto:
                control.setChecked(True)
                return

    def botones(self) -> list[QPushButton]:
        return self._grupo.buttons()


class SelectorFecha(QWidget):
    """La lista de fechas entre dos flechas: ‹ anterior y siguiente ›."""

    def __init__(self, combo: QComboBox, padre=None):
        super().__init__(padre)
        self.combo = ajustar_combo(combo, 8)
        self.anterior = self._flecha("atras", "Fecha anterior", -1)
        self.siguiente = self._flecha("adelante", "Fecha siguiente", 1)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(4)
        fila.addWidget(self.anterior)
        fila.addWidget(self.combo, 1)
        fila.addWidget(self.siguiente)
        combo.currentIndexChanged.connect(self._actualizar)
        combo.model().rowsInserted.connect(self._actualizar)
        combo.model().rowsRemoved.connect(self._actualizar)
        self._actualizar()

    def _flecha(self, icono: str, texto: str, paso: int) -> QPushButton:
        control = QPushButton(objectName="icono")
        control.setIcon(diseno.icono(icono, colores.VERDE_ACTIVO, 14))
        control.setIconSize(QSize(14, 14))
        control.setFixedSize(34, 34)
        control.setToolTip(texto)
        control.setAccessibleName(texto)
        control.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        control.clicked.connect(lambda: self.combo.setCurrentIndex(self.combo.currentIndex() + paso))
        return control

    def _actualizar(self, *_):
        indice, total = self.combo.currentIndex(), self.combo.count()
        self.anterior.setEnabled(indice > 0)
        self.siguiente.setEnabled(0 <= indice < total - 1)
