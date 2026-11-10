"""Cuadros de texto que solo aceptan lo que les corresponde.

Un nombre solo lleva letras, un teléfono solo números, una CURP letras y números en mayúsculas...
Si se oprime una tecla que no va, no se escribe y aparece una nota que dice qué sí se puede escribir.
"""

from PySide6.QtCore import QPoint
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QLineEdit, QToolTip

TELEFONO_DIGITOS = 10


class Filtro(QValidator):
    def __init__(self, permitido, maximo: int, mayusculas: bool = False, padre=None):
        super().__init__(padre)
        self.permitido = permitido
        self.maximo = maximo
        self.mayusculas = mayusculas

    def limpiar(self, texto: str) -> str:
        """Quita lo que no va; sirve para datos que ya estaban guardados de antes."""
        texto = texto.upper() if self.mayusculas else texto
        return "".join(c for c in texto if self.permitido(c))[: self.maximo]

    def validate(self, texto: str, posicion: int):  # noqa: D102 (método de Qt)
        if self.mayusculas:
            texto = texto.upper()
        if len(texto) > self.maximo or not all(self.permitido(c) for c in texto):
            return QValidator.State.Invalid, texto, posicion
        return QValidator.State.Acceptable, texto, posicion


def _restringir(campo: QLineEdit, filtro: Filtro, ayuda: str, ejemplo: str = "") -> QLineEdit:
    filtro.setParent(campo)
    limpio = filtro.limpiar(campo.text())
    if limpio != campo.text():
        campo.setText(limpio)
    campo.setValidator(filtro)
    campo.setMaxLength(filtro.maximo)
    if ejemplo and not campo.placeholderText():
        campo.setPlaceholderText(ejemplo)
    campo.setToolTip(ayuda)
    campo.inputRejected.connect(
        lambda: QToolTip.showText(campo.mapToGlobal(QPoint(0, campo.height())), ayuda, campo)
    )
    return campo


def _letra_de_nombre(c: str) -> bool:
    return c.isalpha() or c in " .'-"


def solo_nombre(campo: QLineEdit, ejemplo: str = "") -> QLineEdit:
    """Nombres de personas: letras (con acentos y ñ), espacios, punto, guion y apóstrofo."""
    return _restringir(campo, Filtro(_letra_de_nombre, 80), "Solo letras y espacios.", ejemplo)


def solo_nombre_de_equipo(campo: QLineEdit, ejemplo: str = "") -> QLineEdit:
    """Clubes y ligas: letras, números y signos comunes en un nombre («Atlético F.C.», «Club 2000»)."""
    return _restringir(
        campo, Filtro(lambda c: c.isalnum() or c in " .'&()-/", 60),
        "Letras, números, espacios y signos como . - & ( )", ejemplo,
    )


def solo_categoria(campo: QLineEdit) -> QLineEdit:
    return _restringir(
        campo, Filtro(lambda c: c.isalnum() or c in " -", 40),
        "Letras, números, espacios y guion, como 2015-2016 o Libre.",
    )


def solo_dias(campo: QLineEdit) -> QLineEdit:
    return _restringir(
        campo, Filtro(lambda c: c.isalpha() or c in " ,/", 60), "Solo los días, separados con coma o «y».",
    )


def solo_temporada(campo: QLineEdit) -> QLineEdit:
    return _restringir(campo, Filtro(lambda c: c.isdigit() or c in " -/–", 11), "Solo los dos años, como 2026-2027.")


def solo_telefono(campo: QLineEdit) -> QLineEdit:
    """Diez números, sin espacios ni guiones. Si ya traía +52 o espacios, se queda con los últimos diez."""
    filtro = Filtro(str.isdigit, TELEFONO_DIGITOS)
    digitos = "".join(c for c in campo.text() if c.isdigit())
    campo.setText(digitos[-TELEFONO_DIGITOS:])
    return _restringir(campo, filtro, f"Solo números: {TELEFONO_DIGITOS} dígitos.", "10 números, ejemplo 8441234567")


def error_telefono(texto: str) -> str | None:
    """El motivo si el teléfono escrito no está completo; vacío se permite."""
    if texto and len(texto) != TELEFONO_DIGITOS:
        return f"El teléfono lleva {TELEFONO_DIGITOS} números; escribiste {len(texto)}."
    return None


def solo_curp(campo: QLineEdit) -> QLineEdit:
    """18 letras y números; se escribe en mayúsculas aunque se teclee en minúsculas."""
    return _restringir(
        campo, Filtro(lambda c: c.isascii() and c.isalnum(), 18, mayusculas=True),
        "Solo letras y números, 18 en total. Se escribe en mayúsculas.",
    )
