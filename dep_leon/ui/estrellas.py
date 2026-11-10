"""Calificación con estrellas.

Las estrellas se dibujan, no se escriben con una fuente: así se ven iguales en cualquier
computadora. El número siempre acompaña a las estrellas para no depender solo del color.
"""

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QVBoxLayout, QWidget

from .. import colores
from ..arbitros import COMENTARIO_MAX, ESTRELLAS_MAX, texto_calificacion

_ESCALA = 2  # se dibuja al doble para que se vea nítido en pantallas con escala


def _estrella(centro: QPointF, radio: float) -> QPolygonF:
    puntos = []
    for i in range(10):
        r = radio if i % 2 == 0 else radio * 0.48
        angulo = math.radians(-90 + i * 36)
        puntos.append(QPointF(centro.x() + r * math.cos(angulo), centro.y() + r * math.sin(angulo)))
    return QPolygonF(puntos)


def pintar_estrellas(pintor: QPainter, x: float, y: float, tamano: float, espacio: float, valor: float) -> None:
    """Cinco estrellas; las primeras `valor` llenas (acepta fracciones, como un promedio de 3.5)."""
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    lleno, contorno, vacio = QColor(colores.ESTRELLA), QColor(colores.ESTRELLA), QColor(colores.BORDE_CONTROL)
    radio = tamano / 2 - 1
    for i in range(ESTRELLAS_MAX):
        centro = QPointF(x + i * (tamano + espacio) + tamano / 2, y + tamano / 2 + 0.5)
        forma = QPainterPath()
        forma.addPolygon(_estrella(centro, radio))
        forma.closeSubpath()
        parte = max(0.0, min(1.0, valor - i))
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.fillPath(forma, QColor(colores.BLANCO))
        if parte > 0:
            pintor.save()
            pintor.setClipRect(QRectF(centro.x() - radio, centro.y() - radio, 2 * radio * parte, 2 * radio))
            pintor.fillPath(forma, lleno)
            pintor.restore()
        pluma = QPen(contorno if parte > 0 else vacio, max(1.0, tamano / 14))
        pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pintor.strokePath(forma, pluma)


def pixmap_estrellas(valor: float | None, tamano: int = 14, espacio: int = 2) -> QPixmap:
    """Las estrellas como imagen, para ponerlas en una celda de tabla o junto a un texto."""
    ancho = ESTRELLAS_MAX * tamano + (ESTRELLAS_MAX - 1) * espacio
    lienzo = QPixmap(ancho * _ESCALA, tamano * _ESCALA)
    lienzo.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(lienzo)
    pintor.scale(_ESCALA, _ESCALA)
    pintar_estrellas(pintor, 0, 0, tamano, espacio, valor or 0)
    pintor.end()
    lienzo.setDevicePixelRatio(_ESCALA)
    return lienzo


class Estrellas(QWidget):
    """Elegir de 1 a 5 estrellas con el mouse o el teclado (flechas, números del 1 al 5, 0 para quitar).

    Volver a tocar la estrella elegida quita la calificación.
    """

    cambiada = Signal(int)  # 0: sin calificar

    def __init__(self, valor: int = 0, tamano: int = 30, padre=None):
        super().__init__(padre)
        self._valor = valor
        self._encima = 0
        self._tamano = tamano
        self._espacio = 8
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Calificación del árbitro")
        self._describir()

    def valor(self) -> int:
        return self._valor

    def setValor(self, valor: int) -> None:  # noqa: N802 (como los controles de Qt)
        valor = max(0, min(ESTRELLAS_MAX, int(valor or 0)))
        if valor == self._valor:
            return
        self._valor = valor
        self._describir()
        self.update()
        self.cambiada.emit(valor)

    def _describir(self):
        self.setAccessibleDescription(texto_calificacion(self._valor))
        self.setToolTip(texto_calificacion(self._valor))

    def sizeHint(self) -> QSize:  # noqa: N802
        ancho = ESTRELLAS_MAX * self._tamano + (ESTRELLAS_MAX - 1) * self._espacio
        return QSize(ancho + 8, self._tamano + 8)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def _estrella_en(self, x: float) -> int:
        paso = self._tamano + self._espacio
        indice = int((x - 4 + self._espacio / 2) // paso) + 1
        return max(1, min(ESTRELLAS_MAX, indice))

    def paintEvent(self, _evento):  # noqa: N802
        pintor = QPainter(self)
        apagado = not self.isEnabled()
        if apagado:
            pintor.setOpacity(0.4)
        pintar_estrellas(pintor, 4, 4, self._tamano, self._espacio, self._encima or self._valor)
        if self.hasFocus():
            pluma = QPen(QColor(colores.VERDE_ACTIVO), 2)
            pintor.setPen(pluma)
            pintor.setBrush(Qt.BrushStyle.NoBrush)
            pintor.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 6, 6)
        pintor.end()

    def mouseMoveEvent(self, evento):  # noqa: N802
        if self.isEnabled():
            self._encima = self._estrella_en(evento.position().x())
            self.update()

    def leaveEvent(self, _evento):  # noqa: N802
        self._encima = 0
        self.update()

    def mousePressEvent(self, evento):  # noqa: N802
        if evento.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(evento)
        elegida = self._estrella_en(evento.position().x())
        self.setValor(0 if elegida == self._valor else elegida)

    def keyPressEvent(self, evento):  # noqa: N802
        tecla = evento.key()
        if tecla in (Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Plus):
            self.setValor(self._valor + 1)
        elif tecla in (Qt.Key.Key_Left, Qt.Key.Key_Down, Qt.Key.Key_Minus):
            self.setValor(self._valor - 1)
        elif Qt.Key.Key_0 <= tecla <= Qt.Key.Key_5:
            self.setValor(tecla - Qt.Key.Key_0)
        elif tecla in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self.setValor(0)
        else:
            super().keyPressEvent(evento)

    def changeEvent(self, evento):  # noqa: N802
        super().changeEvent(evento)
        self.update()


class CalificacionArbitro(QWidget):
    """Las estrellas con su significado al lado («4 de 5: Muy bueno»)."""

    def __init__(self, valor: int = 0, padre=None):
        super().__init__(padre)
        self.estrellas = Estrellas(valor)
        self.texto = QLabel(objectName="ayuda")
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)
        fila.addWidget(self.estrellas)
        fila.addWidget(self.texto, 1)
        self.estrellas.cambiada.connect(self._mostrar)
        self._mostrar(valor)

    def _mostrar(self, valor: int):
        self.texto.setText(texto_calificacion(valor) if self.isEnabled() else "Elige primero al árbitro")

    def valor(self) -> int | None:
        return self.estrellas.valor() or None

    def changeEvent(self, evento):  # noqa: N802
        super().changeEvent(evento)
        if hasattr(self, "texto"):
            self._mostrar(self.estrellas.valor())


class NotaEquipo(QWidget):
    """Lo que un equipo opina del árbitro: sus estrellas y una nota o comentario opcional."""

    def __init__(self, equipo: str, estrellas: int = 0, comentario: str = "", padre=None):
        super().__init__(padre)
        self.titulo = QLabel(f"Calificación de {equipo}", objectName="seccion")
        self.calificacion = CalificacionArbitro(estrellas)
        self.calificacion.estrellas.setAccessibleName(f"Calificación del árbitro según {equipo}")
        self.comentario = QLineEdit(comentario, maxLength=COMENTARIO_MAX)
        self.comentario.setPlaceholderText("Nota o comentario (opcional)")
        self.comentario.setAccessibleName(f"Comentario de {equipo} sobre el árbitro")
        self.comentario.setClearButtonEnabled(True)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(4)
        columna.addWidget(self.titulo)
        columna.addWidget(self.calificacion)
        columna.addWidget(self.comentario)

    def valores(self) -> tuple[int | None, str]:
        return self.calificacion.valor(), self.comentario.text().strip()

    def poner(self, estrellas: int, comentario: str) -> None:
        self.calificacion.estrellas.setValor(estrellas)
        self.comentario.setText(comentario)
