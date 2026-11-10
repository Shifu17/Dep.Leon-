"""La foto redonda de una persona; si no hay foto, sus iniciales."""

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap

from .. import colores

_ESCALA = 2  # se dibuja al doble para que se vea nítido en pantallas con escala

VERDE = (colores.VERDE_SUAVE, colores.VERDE_ACTIVO)
GRIS = (colores.CAMPO_DESACTIVADO, colores.TEXTO_SUAVE)


def iniciales(nombre: str) -> str:
    partes = [p for p in nombre.split() if p[:1].isalpha()]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


@lru_cache(maxsize=512)
def _foto(ruta: str, lado: int) -> QPixmap | None:
    # Las fotos se guardan con un nombre nuevo cada vez que cambian: se pueden recordar sin riesgo.
    imagen = QPixmap(ruta)
    if imagen.isNull():
        return None
    return imagen.scaled(lado, lado, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                         Qt.TransformationMode.SmoothTransformation)


def avatar(foto: Path | None, nombre: str, tamano: int = 28, colores_iniciales=VERDE) -> QPixmap:
    """La foto recortada en círculo; si no hay, las iniciales sobre un círculo de color."""
    lado = tamano * _ESCALA
    lienzo = QPixmap(lado, lado)
    lienzo.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(lienzo)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    circulo = QPainterPath()
    circulo.addEllipse(QRectF(0, 0, lado, lado))
    imagen = _foto(str(foto), lado) if foto else None
    if imagen is not None:
        pintor.setClipPath(circulo)
        # Las fotos de credencial son verticales: se centra a lo ancho y se deja la cara arriba.
        pintor.drawPixmap(int((lado - imagen.width()) / 2), int(min(0, (lado - imagen.height()) / 4)), imagen)
    else:
        fondo, letra = colores_iniciales
        pintor.fillPath(circulo, QColor(fondo))
        fuente = QFont("Segoe UI")
        fuente.setPixelSize(int(lado * 0.4))
        fuente.setWeight(QFont.Weight.DemiBold)
        pintor.setFont(fuente)
        pintor.setPen(QColor(letra))
        pintor.drawText(QRectF(0, 0, lado, lado), Qt.AlignmentFlag.AlignCenter, iniciales(nombre))
    pintor.end()
    lienzo.setDevicePixelRatio(_ESCALA)
    return lienzo
