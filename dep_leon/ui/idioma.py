"""Pone en español lo que dibuja Qt por su cuenta: menús de edición, botones estándar y calendario."""

import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

_traductores: list[QTranslator] = []  # Qt no los conserva: si se destruyen, se pierde la traducción


def _carpetas() -> list[Path]:
    carpetas = [Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        carpetas.append(Path(base) / "PySide6" / "translations")
    return carpetas


def instalar_espanol(app: QApplication) -> bool:
    """Devuelve si se pudo cargar la traducción; sin ella, el programa funciona igual."""
    QLocale.setDefault(QLocale(QLocale.Language.Spanish, QLocale.Country.Mexico))
    for carpeta in _carpetas():
        traductor = QTranslator(app)
        if traductor.load("qtbase_es", str(carpeta)):
            app.installTranslator(traductor)
            _traductores.append(traductor)
            return True
    return False
