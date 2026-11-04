"""Ubicaciones de datos y recursos.

Los datos viven fuera de la carpeta del ejecutable para que una actualización no los toque.
"""

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    base = os.environ.get("DEP_LEON_DATA") or Path(os.environ["LOCALAPPDATA"]) / "DeportivoLeon"
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "liga.db"


def fotos_dir() -> Path:
    path = data_dir() / "fotos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def asset(nombre: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "dep_leon" / "assets" / nombre
