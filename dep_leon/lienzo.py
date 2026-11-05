"""Dibuja los reportes. El mismo código produce el PDF, la imagen y la vista previa."""

from pathlib import Path

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPageSize,
    QPainter,
    QPdfWriter,
    QPen,
)

from . import reportes
from .paths import asset

OSCURO = QColor("#10291D")
DORADO = QColor("#C9A24B")
VERDE = QColor("#1E7F4C")
TEXTO = QColor("#1E2B25")
SUAVE = QColor("#52635A")
ENCABEZADO = QColor("#E4EDE8")
ALTERNA = QColor("#F1F6F3")
BORDE = QColor("#CBD8D0")
BLANCO = QColor("#FFFFFF")

ANCHO = 720.0  # ancho útil en unidades lógicas, tanto en PDF como en imagen
MARGEN_PDF = 48.0
MARGEN_IMAGEN = 24.0
ESCALA_IMAGEN = 1.5  # da una imagen de buen tamaño para WhatsApp

ALTO_ENCABEZADO = 96.0
ALTO_TITULO_SECCION = 34.0
ALTO_COLUMNAS = 28.0
ALTO_FILA = 28.0
ALTO_NOTA = 36.0
SEPARACION = 16.0
ALTO_CARTA_LLAVE = 66.0
SEPARACION_LLAVE = 14.0
ALTO_RONDA = 28.0
ALTO_CAMPEON = 40.0


def _fuente(pixeles: int, negrita: bool = False) -> QFont:
    fuente = QFont("Segoe UI")
    fuente.setPixelSize(pixeles)
    fuente.setBold(negrita)
    return fuente


def _texto(p: QPainter, rect: QRectF, texto: str, alinear=Qt.AlignmentFlag.AlignCenter) -> None:
    """Texto de un renglón, recortado con puntos suspensivos si no cabe."""
    recortado = QFontMetricsF(p.font()).elidedText(texto, Qt.TextElideMode.ElideRight, rect.width() - 8)
    p.drawText(rect.adjusted(4, 0, -4, 0), alinear | Qt.AlignmentFlag.AlignVCenter, recortado)


def _encabezado(p: QPainter, x: float, y: float, titulo: str, subtitulo: str) -> float:
    p.fillRect(QRectF(x, y, ANCHO, ALTO_ENCABEZADO), OSCURO)
    p.fillRect(QRectF(x, y + ALTO_ENCABEZADO, ANCHO, 4), DORADO)
    logo = QImage(str(asset("logo.png")))
    alto_logo = ALTO_ENCABEZADO - 10
    ancho_logo = logo.width() * alto_logo / logo.height()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(QRectF(x + 6, y + 5, ancho_logo, alto_logo), logo)
    izquierda = x + ancho_logo + 22
    p.setPen(BLANCO)
    p.setFont(_fuente(24, True))
    _texto(p, QRectF(izquierda, y + 16, x + ANCHO - izquierda - 10, 36), titulo, Qt.AlignmentFlag.AlignLeft)
    p.setFont(_fuente(15))
    _texto(p, QRectF(izquierda, y + 52, x + ANCHO - izquierda - 10, 26), subtitulo, Qt.AlignmentFlag.AlignLeft)
    return y + ALTO_ENCABEZADO + 4 + SEPARACION


def _titulo_seccion(p: QPainter, x: float, y: float, titulo: str) -> float:
    p.fillRect(QRectF(x, y, ANCHO, ALTO_TITULO_SECCION), VERDE)
    p.setPen(BLANCO)
    p.setFont(_fuente(15, True))
    _texto(p, QRectF(x, y, ANCHO, ALTO_TITULO_SECCION), titulo)
    return y + ALTO_TITULO_SECCION


def _anchos(columnas: list[reportes.Columna]) -> list[float]:
    total = sum(c.peso for c in columnas)
    return [ANCHO * c.peso / total for c in columnas]


def _alineacion(columna: reportes.Columna):
    return {
        reportes.IZQUIERDA: Qt.AlignmentFlag.AlignLeft,
        reportes.DERECHA: Qt.AlignmentFlag.AlignRight,
    }.get(columna.alinear, Qt.AlignmentFlag.AlignHCenter)


def _fila(p: QPainter, x: float, y: float, alto: float, columnas, valores, fondo: QColor, negrita: bool) -> float:
    p.fillRect(QRectF(x, y, ANCHO, alto), fondo)
    p.setPen(QPen(BORDE, 0.75))
    p.drawLine(QRectF(x, y + alto, ANCHO, 0).topLeft(), QRectF(x + ANCHO, y + alto, 0, 0).topLeft())
    p.setPen(TEXTO)
    p.setFont(_fuente(13, negrita))
    izquierda = x
    for ancho, columna, valor in zip(_anchos(columnas), columnas, valores):
        _texto(p, QRectF(izquierda, y, ancho, alto), valor, _alineacion(columna))
        izquierda += ancho
    return y + alto


def _nota(p: QPainter, x: float, y: float, nota: str) -> float:
    p.setPen(SUAVE)
    p.setFont(_fuente(12))
    p.drawText(
        QRectF(x + 4, y + 4, ANCHO - 8, ALTO_NOTA - 4),
        Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        nota,
    )
    return y + ALTO_NOTA


def altura_hoja(hoja: reportes.Hoja) -> float:
    alto = ALTO_ENCABEZADO + 4 + SEPARACION
    for s in hoja.secciones:
        alto += ALTO_TITULO_SECCION + ALTO_COLUMNAS + len(s.filas) * ALTO_FILA + SEPARACION
        if s.nota:
            alto += ALTO_NOTA
    return alto


def _pintar_hoja(p: QPainter, hoja: reportes.Hoja, x: float, y: float, limite: float | None, nueva_pagina) -> None:
    """Sin límite dibuja todo seguido; con límite salta de página y repite los encabezados."""
    inicio = y
    y = _encabezado(p, x, y, hoja.titulo, hoja.subtitulo)

    def saltar(necesario: float, y_actual: float) -> tuple[float, bool]:
        if limite is not None and y_actual + necesario > limite:
            nueva_pagina()
            return inicio, True
        return y_actual, False

    for s in hoja.secciones:
        y, _ = saltar(ALTO_TITULO_SECCION + ALTO_COLUMNAS + ALTO_FILA, y)
        y = _titulo_seccion(p, x, y, s.titulo)
        y = _fila(p, x, y, ALTO_COLUMNAS, s.columnas, [c.titulo for c in s.columnas], ENCABEZADO, True)
        for i, fila in enumerate(s.filas):
            y, salto = saltar(ALTO_FILA, y)
            if salto:
                y = _titulo_seccion(p, x, y, f"{s.titulo} (continúa)")
                y = _fila(p, x, y, ALTO_COLUMNAS, s.columnas, [c.titulo for c in s.columnas], ENCABEZADO, True)
            y = _fila(p, x, y, ALTO_FILA, s.columnas, fila, ALTERNA if i % 2 else BLANCO, False)
        if s.nota:
            y, _ = saltar(ALTO_NOTA, y)
            y = _nota(p, x, y, s.nota)
        y += SEPARACION


def _altura_cuerpo_llave(hoja: reportes.HojaLlave) -> float:
    mayor = max((len(cartas) for _, cartas in hoja.rondas), default=0)
    return ALTO_RONDA + mayor * (ALTO_CARTA_LLAVE + SEPARACION_LLAVE)


def altura_llave(hoja: reportes.HojaLlave) -> float:
    alto = ALTO_ENCABEZADO + 4 + SEPARACION + _altura_cuerpo_llave(hoja) + SEPARACION
    return alto + (ALTO_CAMPEON + SEPARACION if hoja.campeon else 0)


def _pintar_llave(p: QPainter, hoja: reportes.HojaLlave, x: float, y: float) -> None:
    y = _encabezado(p, x, y, hoja.titulo, hoja.subtitulo)
    if hoja.campeon:
        p.fillRect(QRectF(x, y, ANCHO, ALTO_CAMPEON), OSCURO)
        p.fillRect(QRectF(x, y, 5, ALTO_CAMPEON), DORADO)
        p.setPen(BLANCO)
        p.setFont(_fuente(17, True))
        _texto(p, QRectF(x, y, ANCHO, ALTO_CAMPEON), f"Campeón: {hoja.campeon}")
        y += ALTO_CAMPEON + SEPARACION

    total = len(hoja.rondas)
    if not total:
        return
    ancho_columna = ANCHO / total
    ancho_carta = ancho_columna - 12
    alto_cuerpo = _altura_cuerpo_llave(hoja) - ALTO_RONDA
    centros: list[list[float]] = []
    for r, (nombre, cartas) in enumerate(hoja.rondas):
        izquierda = x + r * ancho_columna
        p.setPen(TEXTO)
        p.setFont(_fuente(13, True))
        _texto(p, QRectF(izquierda, y, ancho_carta, ALTO_RONDA), nombre)
        tope = y + ALTO_RONDA
        fila_centros = []
        for i, carta in enumerate(cartas):
            centro = tope + (i + 0.5) * alto_cuerpo / len(cartas)
            fila_centros.append(centro)
            rect = QRectF(izquierda, centro - ALTO_CARTA_LLAVE / 2, ancho_carta, ALTO_CARTA_LLAVE)
            p.setPen(QPen(BORDE, 1))
            p.setBrush(BLANCO)
            p.drawRoundedRect(rect, 5, 5)
            renglones = carta.split("\n")
            for n, renglon in enumerate(renglones):
                es_fecha = n == 0 and len(renglones) == 3
                p.setPen(SUAVE if es_fecha else TEXTO)
                p.setFont(_fuente(10 if es_fecha else 12, renglon.startswith("»")))
                _texto(
                    p,
                    QRectF(rect.left() + 3, rect.top() + 3 + n * 20, rect.width() - 6, 20),
                    renglon,
                    Qt.AlignmentFlag.AlignLeft,
                )
        centros.append(fila_centros)

    # Líneas que unen cada llave con la de la siguiente ronda.
    p.setPen(QPen(SUAVE, 1))
    for r in range(total - 1):
        salida = x + r * ancho_columna + ancho_carta
        llegada = x + (r + 1) * ancho_columna
        medio = (salida + llegada) / 2
        for i, centro in enumerate(centros[r]):
            destino = centros[r + 1][i // 2]
            p.drawLine(QRectF(salida, centro, 0, 0).topLeft(), QRectF(medio, centro, 0, 0).topLeft())
            p.drawLine(QRectF(medio, centro, 0, 0).topLeft(), QRectF(medio, destino, 0, 0).topLeft())
            p.drawLine(QRectF(medio, destino, 0, 0).topLeft(), QRectF(llegada, destino, 0, 0).topLeft())


def a_imagen(hoja: reportes.Hoja | reportes.HojaLlave) -> QImage:
    es_llave = isinstance(hoja, reportes.HojaLlave)
    alto = altura_llave(hoja) if es_llave else altura_hoja(hoja)
    imagen = QImage(
        int((ANCHO + 2 * MARGEN_IMAGEN) * ESCALA_IMAGEN),
        int((alto + 2 * MARGEN_IMAGEN) * ESCALA_IMAGEN),
        QImage.Format.Format_RGB32,
    )
    imagen.fill(BLANCO)
    p = QPainter(imagen)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.scale(ESCALA_IMAGEN, ESCALA_IMAGEN)
    if es_llave:
        _pintar_llave(p, hoja, MARGEN_IMAGEN, MARGEN_IMAGEN)
    else:
        _pintar_hoja(p, hoja, MARGEN_IMAGEN, MARGEN_IMAGEN, None, None)
    p.end()
    return imagen


def guardar_imagen(hoja: reportes.Hoja | reportes.HojaLlave, destino: Path | str) -> None:
    if not a_imagen(hoja).save(str(destino), "PNG"):
        raise OSError(f"No se pudo guardar {destino}.")


def guardar_pdf(hoja: reportes.Hoja | reportes.HojaLlave, destino: Path | str) -> None:
    """Hoja carta. Las tablas continúan en más hojas; la llave se ajusta a una sola."""
    escritor = QPdfWriter(str(destino))
    escritor.setTitle(hoja.titulo)
    escritor.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
    escritor.setResolution(96)
    pagina = QSizeF(8.5 * 96, 11 * 96)
    p = QPainter()
    if not p.begin(escritor):
        raise OSError(f"No se pudo escribir {destino}: el archivo puede estar abierto en otro programa.")
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    x = (pagina.width() - ANCHO) / 2
    if isinstance(hoja, reportes.HojaLlave):
        disponible = pagina.height() - 2 * MARGEN_PDF
        escala = min(1.0, disponible / altura_llave(hoja))
        p.translate(pagina.width() / 2, MARGEN_PDF)
        p.scale(escala, escala)
        _pintar_llave(p, hoja, -ANCHO / 2, 0)
    else:
        _pintar_hoja(p, hoja, x, MARGEN_PDF, pagina.height() - MARGEN_PDF, escritor.newPage)
    p.end()
