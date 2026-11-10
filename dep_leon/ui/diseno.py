"""Sistema de diseño: iconos, sombras suaves de las tarjetas y encabezados de página.

Minimalista y sin degradados: superficies blancas con esquinas redondeadas que se separan del fondo
con una sombra corta y tenue, botones redondeados con icono, y un encabezado por pantalla con su
título grande y una línea que explica para qué sirve.

Los iconos salen de la fuente de iconos que trae Windows («Segoe MDL2 Assets»): no se descarga nada
y todos comparten el mismo trazo. Si la fuente no está, el botón queda solo con su texto.
"""

import atexit
from functools import cache

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLayout, QVBoxLayout, QWidget

from .. import colores

FUENTE_ICONOS = "Segoe MDL2 Assets"

# Nombre -> carácter de la fuente de iconos.
ICONOS = {
    "inicio": "",
    "ligas": "",
    "equipos": "",
    "rol": "",
    "resultados": "",
    "estadisticas": "",
    "liguilla": "",
    "cobros": "",
    "reportes": "",
    "configuracion": "",
    "agregar": "",
    "editar": "",
    "eliminar": "",
    "buscar": "",
    "importar": "",
    "exportar": "",
    "imprimir": "",
    "credencial": "",
    "lista": "",
    "pago": "",
    "listo": "",
    "info": "",
    "aviso": "",
    "copiar": "",
    "imagen": "",
    "persona": "",
    "arbitros": "",
}

# El icono de un botón se elige por la primera palabra de su texto: así todos los botones que hacen
# lo mismo llevan el mismo icono sin tener que indicarlo uno por uno.
_ICONO_POR_VERBO = {
    "agregar": "agregar", "nuevo": "agregar", "crear": "agregar", "generar": "agregar",
    "editar": "editar", "capturar": "editar", "ajustar": "editar", "cambiar": "editar",
    "eliminar": "eliminar", "borrar": "eliminar", "anular": "eliminar",
    "importar": "importar", "restaurar": "importar",
    "exportar": "exportar", "descargar": "exportar", "guardar": "exportar",
    "credenciales": "credencial", "recibo": "imprimir",
    "pase": "lista", "asignar": "arbitros", "registrar": "pago", "copiar": "copiar", "buscar": "buscar",
}


@cache
def hay_iconos() -> bool:
    return FUENTE_ICONOS in QFontDatabase.families()


def icono(nombre: str, color: str = colores.TEXTO, tamano: int = 16, aire: int = 0) -> QIcon:
    """Icono de la fuente de Windows, dibujado a doble resolución para que se vea nítido.

    `aire` deja espacio transparente a la derecha para separar el icono del texto del botón.
    """
    if not hay_iconos() or nombre not in ICONOS:
        return QIcon()
    escala = 2
    lienzo = QPixmap((tamano + aire) * escala, tamano * escala)
    lienzo.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(lienzo)
    pintor.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    fuente = QFont(FUENTE_ICONOS)
    fuente.setPixelSize(tamano * escala)
    pintor.setFont(fuente)
    pintor.setPen(QColor(color))
    pintor.drawText(0, 0, tamano * escala, tamano * escala, Qt.AlignmentFlag.AlignCenter, ICONOS[nombre])
    pintor.end()
    lienzo.setDevicePixelRatio(escala)
    return QIcon(lienzo)


def icono_navegacion(nombre: str) -> QIcon:
    """Claro en el menú oscuro; oscuro sobre la píldora dorada de la sección activa."""
    resultado = QIcon()
    for color, estado in ((colores.TEXTO_BARRA, QIcon.State.Off), (colores.BARRA, QIcon.State.On)):
        pixmap = icono(nombre, color, 18, aire=8).pixmap(26, 18)
        resultado.addPixmap(pixmap, QIcon.Mode.Normal, estado)
    return resultado


def icono_de_boton(texto: str) -> str | None:
    palabra = texto.split()[0].casefold() if texto.split() else ""
    return _ICONO_POR_VERBO.get(palabra)


def color_icono_de(estilo: str | None) -> str:
    return {
        None: colores.BLANCO, "": colores.BLANCO, "secundario": colores.VERDE_ACTIVO,
        "mas": colores.VERDE_ACTIVO, "peligro": colores.ROJO,
    }.get(estilo, colores.VERDE_ACTIVO)


# --- Sombras suaves ------------------------------------------------------------------------------

RADIO = 10
# Capas de la sombra, de dentro hacia fuera: (expansión en px, opacidad 0-255). Corta y tenue.
_CAPAS = [(1, 22), (2, 14), (3, 9), (4, 5), (5, 3)]
_COLOR_SOMBRA = QColor(colores.BARRA)
_EVENTOS_DE_LUGAR = (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.Hide)
_cerrando = False


def _al_cerrar() -> None:
    # Al salir, Python se apaga antes que Qt: los filtros dejan de trabajar para no fallar.
    global _cerrando
    _cerrando = True


atexit.register(_al_cerrar)


class _Sombras(QObject):
    """Pinta, en el fondo del contenedor, una sombra suave detrás de cada tarjeta registrada.

    Se dibuja en el evento de pintura del contenedor (antes que sus hijos), así que no usa efectos
    gráficos que vuelvan lento el desplazamiento de las tablas.
    """

    def __init__(self, contenedor: QWidget):
        super().__init__(contenedor)
        self.contenedor = contenedor
        self.tarjetas: list[QWidget] = []
        contenedor.installEventFilter(self)

    def agregar(self, tarjeta: QWidget) -> None:
        self.tarjetas.append(tarjeta)
        tarjeta.installEventFilter(self)

    def eventFilter(self, objeto, evento) -> bool:  # noqa: N802 (nombre de Qt)
        if _cerrando:
            return False
        try:
            tipo = evento.type()
            if objeto is self.contenedor and tipo == QEvent.Type.Paint:
                self._pintar()
            elif objeto is not self.contenedor and tipo in _EVENTOS_DE_LUGAR:
                self.contenedor.update()
        except (RuntimeError, SystemError):  # el programa se está cerrando
            pass
        return False

    def _pintar(self) -> None:
        pintor = QPainter(self.contenedor)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(Qt.PenStyle.NoPen)
        vivas = []
        for tarjeta in self.tarjetas:
            try:
                visible = tarjeta.isVisible() and tarjeta.parentWidget() is self.contenedor
            except RuntimeError:  # la tarjeta ya se destruyó
                continue
            vivas.append(tarjeta)
            if not visible:
                continue
            caja = QRectF(tarjeta.geometry()).translated(0, 2)
            for expansion, opacidad in _CAPAS:
                color = QColor(_COLOR_SOMBRA)
                color.setAlpha(opacidad)
                pintor.setBrush(color)
                pintor.drawRoundedRect(
                    caja.adjusted(-expansion, -expansion, expansion, expansion),
                    RADIO + expansion, RADIO + expansion,
                )
        pintor.end()
        self.tarjetas = vivas


def sombra(tarjeta: QWidget) -> QWidget:
    """Agrega la sombra suave a la tarjeta en cuanto tenga contenedor (al acomodarla en su lugar)."""

    def colocar():
        contenedor = tarjeta.parentWidget()
        if contenedor is None:
            return False
        sombras = getattr(contenedor, "_sombras", None)
        if sombras is None:
            sombras = _Sombras(contenedor)
            contenedor._sombras = sombras
        if tarjeta not in sombras.tarjetas:
            sombras.agregar(tarjeta)
        return True

    if not colocar():
        tarjeta.installEventFilter(_AlColocar(tarjeta, colocar))
    return tarjeta


class _AlColocar(QObject):
    """Espera a que la tarjeta entre en un contenedor para registrar su sombra."""

    def __init__(self, tarjeta: QWidget, colocar):
        super().__init__(tarjeta)
        self.colocar = colocar

    def eventFilter(self, objeto, evento) -> bool:  # noqa: N802 (nombre de Qt)
        if _cerrando:
            return False
        try:
            if evento.type() in (QEvent.Type.ParentChange, QEvent.Type.Show) and self.colocar():
                objeto.removeEventFilter(self)
        except (RuntimeError, SystemError):  # el programa se está cerrando
            pass
        return False


# --- Encabezado de página --------------------------------------------------------------------------


def encabezado(titulo: str | QLabel, ayuda: str = "", acciones: list[QWidget] | None = None) -> QWidget:
    """Título grande y una línea de ayuda a la izquierda; la acción principal, a la derecha."""
    marco = QWidget(objectName="encabezado")
    fila = QHBoxLayout(marco)
    fila.setContentsMargins(2, 0, 2, 4)
    textos = QVBoxLayout()
    textos.setSpacing(2)
    etiqueta = titulo if isinstance(titulo, QLabel) else QLabel(titulo)
    etiqueta.setObjectName("titulo")
    textos.addWidget(etiqueta)
    if ayuda:
        textos.addWidget(QLabel(ayuda, objectName="ayudaPagina", wordWrap=True))
    fila.addLayout(textos, 1)
    for accion in acciones or []:
        fila.addWidget(accion, 0, Qt.AlignmentFlag.AlignBottom)
    return marco


# --- Fila de botones que se acomoda --------------------------------------------------------------


class FilaBotones(QLayout):
    """Pone los botones en un renglón y, si no caben, pasa los que sobran al siguiente.

    Así una pantalla nunca obliga a ensanchar la ventana por tener muchos botones. Acepta
    `addStretch()` y `addSpacing()` para poder usarse donde antes había un QHBoxLayout (no hacen nada).
    """

    def __init__(self, padre=None, espacio: int = 8):
        super().__init__(padre)
        self._elementos: list = []
        self.setSpacing(espacio)
        self.setContentsMargins(0, 2, 0, 2)

    def addItem(self, elemento):  # noqa: N802 (nombre de Qt)
        self._elementos.append(elemento)

    def addStretch(self, *_):  # noqa: N802
        pass

    def addSpacing(self, *_):  # noqa: N802
        pass

    def count(self):
        return len(self._elementos)

    def itemAt(self, indice):  # noqa: N802
        return self._elementos[indice] if 0 <= indice < len(self._elementos) else None

    def takeAt(self, indice):  # noqa: N802
        return self._elementos.pop(indice) if 0 <= indice < len(self._elementos) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, ancho):  # noqa: N802
        return self._acomodar(QRect(0, 0, ancho, 0), probar=True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._acomodar(rect, probar=False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        tamano = QSize()
        for elemento in self._elementos:
            tamano = tamano.expandedTo(elemento.minimumSize())
        izquierda, arriba, derecha, abajo = self.getContentsMargins()
        return tamano + QSize(izquierda + derecha, arriba + abajo)

    def _acomodar(self, rect, probar: bool) -> int:
        izquierda, arriba, derecha, abajo = self.getContentsMargins()
        zona = rect.adjusted(izquierda, arriba, -derecha, -abajo)
        x, y, alto_renglon = zona.x(), zona.y(), 0
        espacio = self.spacing()
        for elemento in self._elementos:
            if elemento.widget() is not None and not elemento.widget().isVisible() and not probar:
                continue
            tamano = elemento.sizeHint()
            if x + tamano.width() > zona.right() + 1 and alto_renglon > 0:
                x = zona.x()
                y += alto_renglon + espacio
                alto_renglon = 0
            if not probar:
                elemento.setGeometry(QRect(QPoint(x, y), tamano))
            x += tamano.width() + espacio
            alto_renglon = max(alto_renglon, tamano.height())
        return y + alto_renglon - rect.y() + abajo
