"""Reglas de jugadores y fotos, compartidas por los formularios y la importación."""

import uuid
from datetime import date
from pathlib import Path

from PIL import Image, UnidentifiedImageError

POSICIONES = ["Portero", "Defensa", "Medio", "Delantero"]
NUMERO_MAX = 99


def error_de_edad(fecha: date, anio_min: int | None, anio_max: int | None) -> str | None:
    """Devuelve el motivo si la fecha de nacimiento no corresponde a la categoría."""
    if fecha > date.today():
        return "La fecha de nacimiento está en el futuro."
    if anio_min is not None and fecha.year < anio_min:
        return f"Nació en {fecha.year}; la categoría admite desde {anio_min}."
    if anio_max is not None and fecha.year > anio_max:
        return f"Nació en {fecha.year}; la categoría admite hasta {anio_max}."
    return None


def guardar_foto(origen: Path, destino_dir: Path) -> str:
    """Copia la foto ya reducida a la carpeta del programa y devuelve el nombre del archivo.

    Lanza ValueError si el archivo no es una imagen válida.
    """
    try:
        with Image.open(origen) as imagen:
            imagen = imagen.convert("RGB")
            imagen.thumbnail((600, 600))
            nombre = f"{uuid.uuid4().hex}.jpg"
            imagen.save(destino_dir / nombre, "JPEG", quality=88)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"No se pudo leer la foto {origen.name}.") from exc
    return nombre


def borrar_foto(nombre: str, fotos_dir: Path) -> None:
    if nombre:
        (fotos_dir / nombre).unlink(missing_ok=True)
