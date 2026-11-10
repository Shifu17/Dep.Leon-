"""Reglas de jugadores y fotos, compartidas por los formularios y la importación."""

import re
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


def encimadas(categorias) -> dict[int, list[str]]:
    """Para cada categoría con años, las otras de la misma lista con las que comparte años de nacimiento.

    Devuelve {id: ["2011-2012 (2012)", ...]}: si un año cabe en dos categorías, el jugador podría
    registrarse en cualquiera de las dos.
    """
    con_anios = [c for c in categorias if c["anio_min"] is not None and c["anio_max"] is not None]
    resultado: dict[int, list[str]] = {}
    for c in con_anios:
        for otra in con_anios:
            if otra["id"] == c["id"]:
                continue
            desde, hasta = max(c["anio_min"], otra["anio_min"]), min(c["anio_max"], otra["anio_max"])
            if desde <= hasta:
                resultado.setdefault(c["id"], []).append(f"{otra['nombre']} ({rango_anios(desde, hasta)})")
    return resultado


def nombre_categoria(texto: str) -> str:
    """«2009-10» -> «2009-2010»; los demás nombres se dejan como están, sin espacios de más."""
    limpio = " ".join(texto.split())
    corto = re.fullmatch(r"(\d{4})\s*[-/–]\s*(\d{2})", limpio)
    if corto:
        inicio = int(corto.group(1))
        fin = inicio // 100 * 100 + int(corto.group(2))
        if fin < inicio:
            fin += 100
        return f"{inicio}-{fin}"
    largo = re.fullmatch(r"(\d{4})\s*[-/–]\s*(\d{4})", limpio)
    return f"{largo.group(1)}-{largo.group(2)}" if largo else limpio


def anios_del_nombre(nombre: str) -> tuple[int, int] | None:
    """Si el nombre son años («2015-2016» o «2012»), esos años; si no, None."""
    rango = re.fullmatch(r"(\d{4})-(\d{4})", nombre)
    if rango:
        return int(rango.group(1)), int(rango.group(2))
    solo = re.fullmatch(r"\d{4}", nombre)
    return (int(nombre), int(nombre)) if solo else None


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
