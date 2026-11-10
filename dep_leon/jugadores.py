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


def rango_anios(anio_min: int | None, anio_max: int | None) -> str:
    """«2012» si es un solo año; «2009–2010» si son varios; «Sin límite» en una categoría libre."""
    if anio_min is None and anio_max is None:
        return "Sin límite"
    if anio_min is None or anio_max is None:
        return f"Desde {anio_min}" if anio_max is None else f"Hasta {anio_max}"
    return str(anio_min) if anio_min == anio_max else f"{anio_min}–{anio_max}"


def motivo_no_elegible(nacimiento: date, anio_min: int | None, anio_max: int | None) -> str | None:
    """Por qué el jugador no entra en su categoría; None si entra o si la categoría es libre."""
    if anio_min is None and anio_max is None:
        return None
    fuera = (anio_min is not None and nacimiento.year < anio_min) or (
        anio_max is not None and nacimiento.year > anio_max
    )
    if not fuera:
        return None
    return f"Nació en {nacimiento.year}, la categoría permite {rango_anios(anio_min, anio_max)}."


def faltantes(jugador) -> list[str]:
    """Lo que le falta al expediente del jugador para estar completo."""
    falta = []
    if not jugador["curp"]:
        falta.append("CURP")
    if not jugador["foto"]:
        falta.append("foto")
    if jugador["numero"] is None:
        falta.append("número")
    return falta


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
