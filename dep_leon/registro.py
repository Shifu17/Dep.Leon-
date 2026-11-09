"""Hoja de registro de equipo: el formato de Excel que entregan los clubes.

Cada hoja trae el nombre del club, la categoría y la rama, y abajo la lista de jugadores con
número de playera, nombre completo, fecha de nacimiento, CURP y las columnas J1, J2... del pase
de lista; al final, entrenador, asistente y director. Se pueden importar varios archivos a la vez
(un equipo por hoja, de cualquier categoría) y exportar un equipo en el mismo formato.
"""

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from . import asistencia, colores
from .excel import (
    Fila,
    _categorias_de_torneo,
    _clave,
    _existentes,
    _registrar,
    _texto,
    _validar,
)

MAX_RENGLONES = 400
MAX_JUGADORES = 200
CATEGORIA_NUEVA = -1  # categoría que se creará al importar
COLUMNAS_LISTA_MINIMAS = 10
MARCA_ASISTENCIA = "✓"

_ETIQUETAS_PERSONAL = {
    "entrenador": "entrenador",
    "asistente": "asistente",
    "dr. gral": "director",
    "dr gral": "director",
    "dir. gral": "director",
    "dir gral": "director",
    "director": "director",
    "director general": "director",
}
_JORNADA = re.compile(r"^j\s*(\d{1,2})$")
_ANIOS = re.compile(r"^(\d{4})(?:\s*-\s*(\d{4}))?$")


@dataclass
class Registro:
    """Un equipo leído de una hoja de registro."""

    archivo: str
    hoja: str
    equipo: str
    categoria: str  # como viene en el archivo
    rama: str
    entrenador: str = ""
    asistente: str = ""
    director: str = ""
    crudos: list[tuple[int, dict]] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    categoria_id: int | None = None  # CATEGORIA_NUEVA si se va a crear
    nombre_categoria_nueva: str = ""
    filas: list[Fila] = field(default_factory=list)

    @property
    def responsable(self) -> str:
        return self.entrenador or self.director

    @property
    def validas(self) -> int:
        return sum(f.valida for f in self.filas) if not self.errores else 0


def es_hoja_de_registro(ruta: Path | str) -> bool:
    """True si el archivo tiene al menos una hoja con el formato de registro de equipo."""
    try:
        libro = load_workbook(ruta, data_only=True, read_only=True)
    except Exception:
        return False
    try:
        return any(_leer_hoja(hoja, Path(ruta).name) is not None for hoja in libro.worksheets)
    finally:
        libro.close()


def leer(rutas: list[Path | str]) -> list[Registro]:
    """Lee los equipos de uno o varios archivos. Lanza ValueError si un archivo no se puede usar."""
    registros = []
    for ruta in rutas:
        ruta = Path(ruta)
        try:
            libro = load_workbook(ruta, data_only=True, read_only=True)
        except PermissionError as exc:
            raise ValueError(f"«{ruta.name}» está abierto en Excel. Ciérralo e inténtalo de nuevo.") from exc
        except Exception as exc:
            raise ValueError(f"No se pudo abrir «{ruta.name}» como archivo de Excel.") from exc
        try:
            encontrados = [r for h in libro.worksheets if (r := _leer_hoja(h, ruta.name)) is not None]
        finally:
            libro.close()
        if not encontrados:
            raise ValueError(
                f"«{ruta.name}» no tiene una hoja de registro de equipo "
                "(con «NOMBRE DEL CLUB» y «NOMBRE COMPLETO»)."
            )
        registros.extend(encontrados)
    return registros


def _a_la_derecha(renglon: tuple, columna: int) -> str:
    for valor in renglon[columna + 1 :]:
        if _texto(valor):
            return _texto(valor)
    return ""


def _leer_hoja(hoja, archivo: str) -> Registro | None:
    renglones = []
    for i, renglon in enumerate(hoja.iter_rows(values_only=True), start=1):
        if i > MAX_RENGLONES:
            break
        renglones.append((i, renglon))

    datos = {"club": "", "categoria": "", "rama": ""}
    encabezado = None
    for i, renglon in renglones:
        claves = [_clave(_texto(v)).rstrip(":").strip() for v in renglon]
        if "nombre completo" in claves and any("nacimiento" in c for c in claves):
            encabezado = (i, claves)
            break
        for c, clave in enumerate(claves):
            if clave.startswith("nombre del club") or clave.startswith("nombre del equipo"):
                datos["club"] = datos["club"] or _a_la_derecha(renglon, c)
            elif clave.startswith("categoria"):
                datos["categoria"] = datos["categoria"] or _a_la_derecha(renglon, c)
            elif clave.startswith("rama"):
                datos["rama"] = datos["rama"] or _a_la_derecha(renglon, c)
    if encabezado is None or not datos["club"]:
        return None

    fila_encabezado, claves = encabezado
    columnas = {}
    for c, clave in enumerate(claves):
        if clave == "nombre completo":
            columnas["nombre"] = c
        elif "playera" in clave or clave in ("no", "no.", "num", "num.", "numero", "#"):
            columnas.setdefault("numero", c)
        elif "nacimiento" in clave:
            columnas["fecha"] = c
        elif clave == "curp":
            columnas["curp"] = c

    registro = Registro(
        archivo=archivo, hoja=hoja.title, equipo=datos["club"],
        categoria=datos["categoria"], rama=datos["rama"],
    )
    for i, renglon in renglones:
        if i <= fila_encabezado:
            continue
        claves = [_clave(_texto(v)).rstrip(":").strip() for v in renglon]
        personal = next(
            ((c, _ETIQUETAS_PERSONAL[k]) for c, k in enumerate(claves) if k in _ETIQUETAS_PERSONAL), None
        )
        if personal is not None:
            columna, puesto = personal
            setattr(registro, puesto, getattr(registro, puesto) or _a_la_derecha(renglon, columna))
            continue
        valor = lambda campo: renglon[columnas[campo]] if campo in columnas and columnas[campo] < len(renglon) else None  # noqa: E731
        if not _texto(valor("nombre")):
            continue
        registro.crudos.append(
            (i, {"nombre": valor("nombre"), "fecha": valor("fecha"), "numero": valor("numero"), "curp": valor("curp")})
        )
    if len(registro.crudos) > MAX_JUGADORES:
        registro.errores.append(f"La hoja tiene más de {MAX_JUGADORES} jugadores.")
    if not registro.crudos:
        registro.errores.append("La hoja no tiene jugadores capturados.")
    return registro


def _anios(texto: str) -> tuple[int, int] | None:
    m = _ANIOS.match(texto.strip())
    if not m:
        return None
    desde = int(m.group(1))
    return desde, int(m.group(2) or desde)


def nombre_sugerido(registro: Registro) -> str:
    """Nombre para crear la categoría cuando no existe: el del archivo, con mayúscula inicial."""
    texto = registro.categoria or "Sin categoría"
    return texto if _anios(texto) else texto.strip().capitalize()


def sugerir_categoria(registro: Registro, categorias: list[sqlite3.Row]) -> int | None:
    """Busca la categoría de la liga que corresponde a la del archivo."""
    por_nombre = {_clave(c["nombre"]): c["id"] for c in categorias}
    for candidato in (registro.categoria, f"{registro.categoria} {registro.rama}"):
        if _clave(candidato) in por_nombre:
            return por_nombre[_clave(candidato)]
    anios = _anios(registro.categoria)
    if anios:
        for c in categorias:
            if c["anio_min"] is not None and c["anio_max"] is not None:
                if c["anio_min"] <= anios[0] and anios[1] <= c["anio_max"]:
                    return c["id"]
    if len(categorias) == 1:
        return categorias[0]["id"]
    return None


def preparar(conn: sqlite3.Connection, registros: list[Registro], torneo_id: int) -> None:
    """Elige categoría para cada equipo (o propone crearla) y valida sus jugadores."""
    categorias = list(_categorias_de_torneo(conn, torneo_id).values())
    for registro in registros:
        registro.categoria_id = sugerir_categoria(registro, categorias)
        if registro.categoria_id is None:
            registro.categoria_id = CATEGORIA_NUEVA
            registro.nombre_categoria_nueva = nombre_sugerido(registro)
        validar(conn, registro, torneo_id)


def validar(conn: sqlite3.Connection, registro: Registro, torneo_id: int) -> None:
    """Valida los jugadores con la categoría elegida, sin modificar nada."""
    categorias = _categorias_de_torneo(conn, torneo_id)
    if registro.categoria_id == CATEGORIA_NUEVA:
        nombre = registro.nombre_categoria_nueva
        anios = _anios(nombre)
        existente = categorias.get(_clave(nombre))
        if existente is not None:
            registro.categoria_id = existente["id"]
            categoria = existente
        else:
            categoria = {
                "id": CATEGORIA_NUEVA, "nombre": nombre,
                "anio_min": anios[0] if anios else None, "anio_max": anios[1] if anios else None,
            }
            categorias = {**categorias, _clave(nombre): categoria}
    else:
        categoria = next(c for c in categorias.values() if c["id"] == registro.categoria_id)
    crudos = [
        (renglon, {**v, "categoria": categoria["nombre"], "equipo": registro.equipo})
        for renglon, v in registro.crudos
    ]
    registro.filas = _validar(crudos, categorias, _existentes(conn, torneo_id), Path("."), numero_obligatorio=False)


def importar(
    conn: sqlite3.Connection, registros: list[Registro], torneo_id: int, fotos_dir: Path
) -> tuple[int, int, int, int]:
    """Registra todos los equipos en una sola transacción.

    Devuelve (jugadores nuevos, actualizados, equipos creados, categorías creadas).
    """
    totales = [0, 0, 0, 0]
    fotos: list[Path] = []
    liga_id = conn.execute("SELECT liga_id FROM torneos WHERE id = ?", (torneo_id,)).fetchone()["liga_id"]
    try:
        with conn:
            for registro in registros:
                if registro.errores or not registro.validas:
                    continue
                if registro.categoria_id == CATEGORIA_NUEVA:
                    nombre = registro.nombre_categoria_nueva
                    fila = conn.execute(
                        "SELECT id FROM categorias WHERE liga_id = ? AND nombre = ?", (liga_id, nombre)
                    ).fetchone()
                    if fila is None:
                        anios = _anios(nombre)
                        categoria_id = conn.execute(
                            "INSERT INTO categorias (liga_id, nombre, anio_min, anio_max) VALUES (?, ?, ?, ?)",
                            (liga_id, nombre, anios[0] if anios else None, anios[1] if anios else None),
                        ).lastrowid
                        totales[3] += 1
                    else:
                        categoria_id = fila["id"]
                    for f in registro.filas:
                        f.categoria_id = categoria_id
                    registro.categoria_id = categoria_id
                nuevos, actualizados, equipos = _registrar(
                    conn, registro.filas, torneo_id, fotos_dir, fotos, registro.responsable
                )
                totales[0] += nuevos
                totales[1] += actualizados
                totales[2] += equipos
    except Exception:
        for ruta in fotos:
            ruta.unlink(missing_ok=True)
        raise
    return tuple(totales)


# --- Exportar ---------------------------------------------------------------------------------

_VERDE = PatternFill("solid", fgColor=colores.VERDE.lstrip("#"))
_BORDE = Border(*[Side(style="thin", color=colores.BORDE_CONTROL.lstrip("#"))] * 4)
_CENTRO = Alignment(horizontal="center", vertical="center", wrap_text=True)


def exportar(conn: sqlite3.Connection, equipo_id: int, destino: Path | str) -> None:
    """Escribe la hoja de registro del equipo, con el pase de lista de cada partido marcado."""
    equipo = conn.execute(
        """SELECT e.*, c.nombre AS categoria, t.nombre AS torneo FROM equipos e
           JOIN categorias c ON c.id = e.categoria_id JOIN torneos t ON t.id = e.torneo_id
           WHERE e.id = ?""",
        (equipo_id,),
    ).fetchone()
    jugadores = conn.execute(
        "SELECT * FROM jugadores WHERE equipo_id = ? ORDER BY numero IS NULL, numero, nombre COLLATE ES",
        (equipo_id,),
    ).fetchall()
    partidos = asistencia.partidos_de_equipo(conn, equipo_id)
    asistio = asistencia.de_equipo(conn, equipo_id)

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Hoja de Registro"
    for etiqueta, valor, fila in (
        ("NOMBRE DEL CLUB", equipo["nombre"], 3),
        ("CATEGORÍA:", equipo["categoria"], 4),
        ("TORNEO:", equipo["torneo"], 5),
    ):
        hoja.cell(row=fila, column=2, value=etiqueta).font = Font(bold=True)
        hoja.cell(row=fila, column=3, value=valor)

    columnas_lista = max(COLUMNAS_LISTA_MINIMAS, len(partidos))
    titulos = ["NO. PLAYERA", "NOMBRE COMPLETO", "FECHA DE NACIMIENTO", "CURP"]
    for i, titulo in enumerate(titulos, start=2):
        _encabezado(hoja.cell(row=7, column=i, value=titulo))
    for n in range(columnas_lista):
        celda = hoja.cell(row=7, column=7 + n, value=partidos[n].etiqueta if n < len(partidos) else f"J{n + 1}")
        _encabezado(celda)
        hoja.column_dimensions[celda.column_letter].width = 7 if n >= len(partidos) or len(celda.value) < 5 else 12
    total_col = 7 + columnas_lista
    _encabezado(hoja.cell(row=7, column=total_col, value="ASISTENCIAS"))
    hoja.column_dimensions[hoja.cell(row=7, column=total_col).column_letter].width = 13

    fila = 8
    for j in jugadores:
        valores = [
            j["numero"], j["nombre"],
            date.fromisoformat(j["fecha_nacimiento"]).strftime("%d/%m/%Y"), j["curp"] or None,
        ]
        for i, valor in enumerate(valores, start=2):
            celda = hoja.cell(row=fila, column=i, value=valor)
            celda.border = _BORDE
            if i != 3:
                celda.alignment = _CENTRO
        presentes = asistio.get(j["id"], set())
        for n in range(columnas_lista):
            marcado = n < len(partidos) and partidos[n].id in presentes
            celda = hoja.cell(row=fila, column=7 + n, value=MARCA_ASISTENCIA if marcado else None)
            celda.border = _BORDE
            celda.alignment = _CENTRO
        celda = hoja.cell(row=fila, column=total_col, value=len(presentes))
        celda.border = _BORDE
        celda.alignment = _CENTRO
        fila += 1

    fila += 1
    for etiqueta, valor in (("Entrenador", equipo["responsable"]), ("Asistente", ""), ("Dr. Gral", "")):
        hoja.cell(row=fila, column=2, value=etiqueta).font = Font(bold=True)
        hoja.cell(row=fila, column=3, value=valor or None)
        fila += 1

    for letra, ancho in (("A", 3), ("B", 16), ("C", 38), ("D", 20), ("E", 22), ("F", 2)):
        hoja.column_dimensions[letra].width = ancho
    hoja.freeze_panes = "C8"
    hoja.page_setup.orientation = "landscape"
    hoja.page_setup.fitToWidth = 1
    hoja.sheet_properties.pageSetUpPr.fitToPage = True
    libro.save(destino)


def _encabezado(celda) -> None:
    celda.font = Font(bold=True, color="FFFFFF")
    celda.fill = _VERDE
    celda.border = _BORDE
    celda.alignment = _CENTRO
