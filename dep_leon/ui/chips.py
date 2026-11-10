"""Chips y badges: etiquetas cortas en una píldora de color, dentro de las celdas de una tabla.

El texto de la celda no cambia (se sigue pudiendo buscar, ordenar y leer con lector de pantalla);
solo cambia cómo se dibuja. Cada chip lleva su palabra, así el color nunca es la única pista.
"""

import re

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from .. import colores

# (fondo, texto, borde)
NEUTRO = (colores.FILA_ALTERNA, colores.TEXTO, colores.BORDE)
VERDE = (colores.VERDE_SUAVE, colores.VERDE_ACTIVO, "#9CCBAE")  # el borde lo separa de la fila elegida
DORADO = (colores.DORADO_SUAVE, colores.DORADO_TEXTO, colores.DORADO_SUAVE)
GRIS = (colores.CAMPO_DESACTIVADO, colores.TEXTO_SUAVE, colores.BORDE)

MODALIDAD = {"Fut 7": VERDE, "Fut 11": DORADO}
ESTADO_TORNEO = {"Activo": VERDE, "Próximo": DORADO, "Finalizado": GRIS}

_ALTO = 22
_RELLENO = 9
_ESPACIO = 4


def separar_dias(texto: str) -> list[str]:
    """«Viernes y sábado» -> ["Viernes", "Sábado"]; acepta comas, «y» y diagonales."""
    partes = re.split(r"\s*(?:,|/|\by\b|\be\b)\s*", texto.strip())
    return [p[:1].upper() + p[1:] for p in partes if p]


class DelegadoChips(QStyledItemDelegate):
    """Dibuja el texto de la celda como una o varias píldoras.

    `estilo(texto)` da los colores de cada chip; `separar(texto)` lo parte en varios chips.
    """

    def __init__(self, padre=None, estilo=None, separar=None, pequeno: bool = False):
        super().__init__(padre)
        self._estilo = estilo or (lambda _texto: NEUTRO)
        self._separar = separar or (lambda texto: [texto] if texto else [])
        self._pequeno = pequeno

    def _fuente(self, base: QFont) -> QFont:
        fuente = QFont(base)
        if self._pequeno:
            fuente.setPointSizeF(max(7.5, base.pointSizeF() - 1))
        fuente.setWeight(QFont.Weight.DemiBold)
        return fuente

    def _anchos(self, opcion, partes):
        medida = QFontMetrics(self._fuente(opcion.font))
        relleno = _RELLENO - 3 if self._pequeno else _RELLENO
        return [medida.horizontalAdvance(p) + 2 * relleno for p in partes]

    def paint(self, pintor: QPainter, opcion, indice):
        # Fondo y selección como cualquier celda, sin el texto.
        self.initStyleOption(opcion, indice)
        texto = opcion.text
        opcion.text = ""
        estilo = opcion.widget.style() if opcion.widget else None
        if estilo:
            estilo.drawControl(QStyle.ControlElement.CE_ItemViewItem, opcion, pintor, opcion.widget)
        partes = self._separar(texto)
        if not partes:
            return
        pintor.save()
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setFont(self._fuente(opcion.font))
        alto = _ALTO - (4 if self._pequeno else 0)
        x = opcion.rect.x() + 6
        y = opcion.rect.y() + (opcion.rect.height() - alto) / 2
        for parte, ancho in zip(partes, self._anchos(opcion, partes)):
            if x + ancho > opcion.rect.right() - 2:
                break  # lo que no cabe se lee en el tooltip de la celda
            fondo, letra, borde = self._estilo(parte)
            caja = QRectF(x, y, ancho, alto)
            pintor.setPen(QPen(QColor(borde), 1))
            pintor.setBrush(QColor(fondo))
            pintor.drawRoundedRect(caja.adjusted(0.5, 0.5, -0.5, -0.5), alto / 2, alto / 2)
            pintor.setPen(QColor(letra))
            pintor.drawText(caja, Qt.AlignmentFlag.AlignCenter, parte)
            x += ancho + _ESPACIO
        pintor.restore()

    def sizeHint(self, opcion, indice):  # noqa: N802
        self.initStyleOption(opcion, indice)
        anchos = self._anchos(opcion, self._separar(opcion.text))
        return QSize(sum(anchos) + _ESPACIO * max(0, len(anchos) - 1) + 14, _ALTO + 10)


def chips_en(tabla, columna: int, estilo=None, separar=None, pequeno: bool = False) -> DelegadoChips:
    delegado = DelegadoChips(tabla, estilo, separar, pequeno)
    tabla.setItemDelegateForColumn(columna, delegado)
    return delegado
