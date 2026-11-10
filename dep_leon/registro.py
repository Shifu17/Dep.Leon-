"""Hoja de registro de equipo: el formato de Excel que entregan los clubes.

Cada hoja trae el nombre del club, la categoría y la rama, y abajo la lista de jugadores con
número de playera, nombre completo, fecha de nacimiento, CURP y las columnas J1, J2... del pase
de lista; al final, entrenador, asistente y director. La hoja «Cédula» arma las credenciales con
fórmulas que apuntan a esos renglones, y en cada una va la foto del jugador.

Se pueden importar varios archivos a la vez (un equipo por hoja, de cualquier categoría, con sus
fotos) y exportar un equipo con el mismo formato, a partir de una copia limpia de esa hoja.
"""

import posixpath
import re
import sqlite3
import tempfile
import zipfile
from copy import copy
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

from openpyxl import load_workbook
from openpyxl.drawing.image import Image as ImagenExcel
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, TwoCellAnchor
from openpyxl.utils import get_column_letter
from PIL import Image, UnidentifiedImageError

from . import asistencia, credenciales
from .jugadores import borrar_foto
from .paths import asset
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
PLANTILLA = "hoja_registro.xlsx"  # copia limpia del formato de los clubes, sin datos personales

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
    fotos: dict[int, bytes] = field(default_factory=dict)  # renglón del jugador -> foto de su credencial

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
        for r in encontrados:
            r.fotos = _fotos_de_cedula(ruta, r.hoja)
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
    reemplazadas: list[str] = []
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
                with tempfile.TemporaryDirectory() as temporal:
                    reemplazadas += _preparar_fotos(conn, registro, Path(temporal))
                    nuevos, actualizados, equipos = _registrar(
                        conn, registro.filas, torneo_id, fotos_dir, fotos,
                        {"responsable": registro.responsable, "asistente": registro.asistente,
                         "director": registro.director, "rama": registro.rama.upper()},
                    )
                totales[0] += nuevos
                totales[1] += actualizados
                totales[2] += equipos
    except Exception:
        for ruta in fotos:
            ruta.unlink(missing_ok=True)
        raise
    for nombre in reemplazadas:  # ya quedó la foto nueva: la anterior sobra
        borrar_foto(nombre, fotos_dir)
    return tuple(totales)


def _preparar_fotos(conn: sqlite3.Connection, registro: Registro, carpeta: Path) -> list[str]:
    """Deja lista la foto de la credencial de cada jugador. Devuelve las fotos anteriores que reemplaza."""
    reemplazadas = []
    for fila in registro.filas:
        datos = registro.fotos.get(fila.renglon)
        if not datos or fila.foto is not None or not fila.valida:
            continue
        if fila.jugador_id is not None:
            actual = conn.execute("SELECT foto FROM jugadores WHERE id = ?", (fila.jugador_id,)).fetchone()
            if actual and actual["foto"]:
                reemplazadas.append(actual["foto"])
        ruta = carpeta / f"{fila.renglon}.img"
        ruta.write_bytes(datos)
        fila.foto = ruta
    return reemplazadas


# --- Acomodo de la hoja y de la cédula --------------------------------------------------------


@dataclass
class Forma:
    """Dónde va cada dato en un libro con el formato de registro."""

    hoja_registro: str
    datos: dict[str, tuple[int, int]]  # club, categoria, rama -> (renglón, columna) del valor
    encabezado: int
    columnas: dict[str, int]  # numero, nombre, fecha, curp -> columna
    jornadas: list[int]  # columnas J1, J2...
    primer_renglon: int
    ultimo_renglon: int
    personal: dict[str, int]  # entrenador, asistente, director -> renglón
    hoja_cedula: str | None = None
    fotos: dict[int, tuple[int, int]] = field(default_factory=dict)  # renglón -> (columna, renglón) base 0


def forma_de_plantilla(libro, titulo: str | None = None) -> Forma:
    """Lee el acomodo a partir de las etiquetas y de las fórmulas de la cédula."""
    hoja = libro[titulo] if titulo else libro.worksheets[0]
    datos: dict[str, tuple[int, int]] = {}
    encabezado = None
    for renglon in hoja.iter_rows(max_row=MAX_RENGLONES):
        claves = [_clave(_texto(c.value)).rstrip(":").strip() for c in renglon]
        if "nombre completo" in claves:
            encabezado = renglon[0].row
            break
        for celda, clave in zip(renglon, claves):
            for nombre, prefijo in (("club", "nombre del club"), ("categoria", "categoria"), ("rama", "rama")):
                if clave.startswith(prefijo) and nombre not in datos:
                    datos[nombre] = (celda.row, celda.column + 1)
    if encabezado is None:
        raise ValueError("La plantilla no tiene el renglón de encabezados.")

    columnas, jornadas = {}, []
    for celda in hoja[encabezado]:
        clave = _clave(_texto(celda.value))
        if clave == "nombre completo":
            columnas["nombre"] = celda.column
        elif "playera" in clave:
            columnas["numero"] = celda.column
        elif "nacimiento" in clave:
            columnas["fecha"] = celda.column
        elif clave == "curp":
            columnas["curp"] = celda.column
        elif _JORNADA.match(clave):
            jornadas.append(celda.column)

    personal = {}
    for renglon in hoja.iter_rows(min_row=encabezado + 1, max_row=MAX_RENGLONES):
        for celda in renglon:
            puesto = _ETIQUETAS_PERSONAL.get(_clave(_texto(celda.value)).rstrip(":").strip())
            if puesto and puesto not in personal:
                personal[puesto] = celda.row
    ultimo = min(personal.values()) - 1 if personal else encabezado + COLUMNAS_LISTA_MINIMAS
    forma = Forma(hoja.title, datos, encabezado, columnas, jornadas, encabezado + 1, ultimo, personal)

    letra_nombre = get_column_letter(columnas["nombre"])
    referencia = re.compile(rf"^=\+?'?{re.escape(hoja.title)}'?!\$?{letra_nombre}\$?(\d+)$")
    for otra in libro.worksheets:
        if otra.title == hoja.title:
            continue
        for renglon in otra.iter_rows():
            for celda in renglon:
                m = referencia.match(str(celda.value or "").strip())
                if m and forma.primer_renglon <= int(m.group(1)) <= forma.ultimo_renglon:
                    forma.hoja_cedula = otra.title
                    # La foto va a la izquierda del nombre, en el mismo renglón (base 0 para el dibujo).
                    forma.fotos[int(m.group(1))] = (celda.column - 2, celda.row - 1)
    return forma


_NS = {
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


def _relaciones(archivo: zipfile.ZipFile, parte: str) -> dict[str, str]:
    ruta = posixpath.join(posixpath.dirname(parte), "_rels", posixpath.basename(parte) + ".rels")
    if ruta not in archivo.namelist():
        return {}
    raiz = ElementTree.fromstring(archivo.read(ruta))
    resultado = {}
    for rel in raiz.findall("rel:Relationship", _NS):
        destino = rel.get("Target")
        destino = destino.lstrip("/") if destino.startswith("/") else posixpath.normpath(
            posixpath.join(posixpath.dirname(parte), destino)
        )
        resultado[rel.get("Id")] = destino
    return resultado


def _imagenes_de_hoja(archivo: zipfile.ZipFile, titulo: str) -> list[tuple[int, int, bytes]]:
    """Imágenes de una hoja con la celda (columna, renglón, base 0) donde empiezan."""
    libro = ElementTree.fromstring(archivo.read("xl/workbook.xml"))
    rels = _relaciones(archivo, "xl/workbook.xml")
    hoja = next(
        (h for h in libro.iterfind("x:sheets/x:sheet", _NS) if h.get("name") == titulo), None
    )
    if hoja is None:
        return []
    parte = rels[hoja.get(f"{{{_NS['r']}}}id")]
    imagenes = []
    for dibujo in _relaciones(archivo, parte).values():
        if "drawings/" not in dibujo or not dibujo.endswith(".xml"):
            continue
        medios = _relaciones(archivo, dibujo)
        raiz = ElementTree.fromstring(archivo.read(dibujo))
        for ancla in [*raiz.findall("xdr:twoCellAnchor", _NS), *raiz.findall("xdr:oneCellAnchor", _NS)]:
            inicio = ancla.find("xdr:from", _NS)
            blip = ancla.find(".//a:blip", _NS)
            if inicio is None or blip is None:
                continue
            medio = medios.get(blip.get(f"{{{_NS['r']}}}embed"))
            if medio and medio in archivo.namelist():
                imagenes.append((
                    int(inicio.findtext("xdr:col", "0", _NS)), int(inicio.findtext("xdr:row", "0", _NS)),
                    archivo.read(medio),
                ))
    return imagenes


def _fotos_de_cedula(ruta: Path, titulo: str) -> dict[int, bytes]:
    """Fotos de la hoja «Cédula», por renglón del jugador. Sin cédula o si algo falla, ninguna."""
    try:
        libro = load_workbook(ruta)
        forma = forma_de_plantilla(libro, titulo)
        if not forma.hoja_cedula:
            return {}
        with zipfile.ZipFile(ruta) as archivo:
            imagenes = _imagenes_de_hoja(archivo, forma.hoja_cedula)
    except (KeyError, ValueError, OSError, zipfile.BadZipFile, ElementTree.ParseError):
        return {}
    repetidas = {datos for _, _, datos in imagenes if sum(d == datos for _, _, d in imagenes) > 1}
    fotos = {}
    for renglon, (columna, fila) in forma.fotos.items():
        for c, f, datos in imagenes:
            # El escudo se repite en todas las credenciales; una foto aparece una sola vez.
            if c == columna and abs(f - fila) <= 2 and datos not in repetidas:
                fotos[renglon] = datos
                break
    return fotos


# --- Exportar ---------------------------------------------------------------------------------

_DESDE_FOTO = (93925, 88292)  # márgenes de la foto dentro de su recuadro, como en la cédula original
_HASTA_FOTO = (676193, 144851)
_ALTO_FOTO = 5  # renglones que ocupa la foto


def _foto_para_cedula(ruta: Path) -> ImagenExcel | None:
    """La foto recortada a 3:4, como el recuadro de la credencial, para que no se deforme."""
    try:
        with Image.open(ruta) as original:
            imagen = original.convert("RGB")
    except (OSError, UnidentifiedImageError):
        return None
    ancho, alto = imagen.size
    if ancho * 4 > alto * 3:
        nuevo = alto * 3 // 4
        imagen = imagen.crop(((ancho - nuevo) // 2, 0, (ancho - nuevo) // 2 + nuevo, alto))
    else:
        nuevo = ancho * 4 // 3
        imagen = imagen.crop((0, (alto - nuevo) // 2, ancho, (alto - nuevo) // 2 + nuevo))
    imagen.thumbnail((300, 400))
    datos = BytesIO()
    imagen.save(datos, "JPEG", quality=85)
    datos.seek(0)
    return ImagenExcel(datos)


def _copiar_estilo(origen, destino) -> None:
    if origen.has_style:
        destino.font, destino.border, destino.fill = copy(origen.font), copy(origen.border), copy(origen.fill)
        destino.number_format, destino.alignment = origen.number_format, copy(origen.alignment)


def exportar(conn: sqlite3.Connection, equipo_id: int, destino: Path | str, fotos_dir: Path) -> None:
    """Escribe la hoja de registro del equipo con el formato de los clubes.

    Lleva el pase de lista de cada partido en J1, J2..., y la cédula arma las credenciales con la foto
    de cada jugador. Si hay más jugadores que renglones en la hoja, se agregan renglones; las
    credenciales solo alcanzan para los que caben en la cédula.
    """
    equipo = conn.execute(
        """SELECT e.*, c.nombre AS categoria, l.nombre AS liga, t.nombre AS torneo FROM equipos e
           JOIN categorias c ON c.id = e.categoria_id JOIN torneos t ON t.id = e.torneo_id
           JOIN ligas l ON l.id = t.liga_id WHERE e.id = ?""",
        (equipo_id,),
    ).fetchone()
    jugadores = conn.execute(
        "SELECT * FROM jugadores WHERE equipo_id = ? ORDER BY numero IS NULL, numero, nombre COLLATE ES",
        (equipo_id,),
    ).fetchall()
    partidos = asistencia.partidos_de_equipo(conn, equipo_id)
    asistio = asistencia.de_equipo(conn, equipo_id)

    libro = load_workbook(asset(PLANTILLA))
    forma = forma_de_plantilla(libro)
    hoja = libro[forma.hoja_registro]

    for nombre, valor in (
        ("club", equipo["nombre"]), ("categoria", equipo["categoria"].upper()),
        ("rama", credenciales.rama_de(equipo)),
    ):
        if nombre in forma.datos:
            hoja.cell(*forma.datos[nombre], value=valor)

    # Más jugadores que renglones: se agregan antes del personal y se corrigen las fórmulas de la cédula.
    capacidad = forma.ultimo_renglon - forma.primer_renglon + 1
    extra = max(0, len(jugadores) - capacidad)
    if extra:
        hoja.insert_rows(forma.ultimo_renglon + 1, extra)
        for r in range(forma.ultimo_renglon + 1, forma.ultimo_renglon + 1 + extra):
            for c in range(1, hoja.max_column + 1):
                _copiar_estilo(hoja.cell(row=forma.ultimo_renglon, column=c), hoja.cell(row=r, column=c))
        if forma.hoja_cedula:
            _recorrer_referencias(libro[forma.hoja_cedula], forma, extra)
        forma.personal = {k: v + extra for k, v in forma.personal.items()}

    # Más partidos que columnas J: se agregan a la derecha con el mismo estilo.
    while len(forma.jornadas) < len(partidos):
        ultima = forma.jornadas[-1]
        nueva = ultima + 1
        for r in range(forma.encabezado, forma.ultimo_renglon + extra + 1):
            _copiar_estilo(hoja.cell(row=r, column=ultima), hoja.cell(row=r, column=nueva))
        hoja.column_dimensions[get_column_letter(nueva)].width = hoja.column_dimensions[get_column_letter(ultima)].width
        forma.jornadas.append(nueva)
    for n, columna in enumerate(forma.jornadas):
        hoja.cell(row=forma.encabezado, column=columna, value=partidos[n].etiqueta if n < len(partidos) else f"J{n + 1}")

    cedula = libro[forma.hoja_cedula] if forma.hoja_cedula else None
    for i, j in enumerate(jugadores):
        renglon = forma.primer_renglon + i
        c = forma.columnas
        if "numero" in c:
            hoja.cell(row=renglon, column=c["numero"], value=j["numero"])
        hoja.cell(row=renglon, column=c["nombre"], value=j["nombre"])
        if "fecha" in c:
            hoja.cell(row=renglon, column=c["fecha"], value=datetime.fromisoformat(j["fecha_nacimiento"]))
            hoja.cell(row=renglon, column=c["fecha"]).number_format = "DD/MM/YYYY"
        if "curp" in c:
            hoja.cell(row=renglon, column=c["curp"], value=j["curp"] or None)
        presentes = asistio.get(j["id"], set())
        for n, columna in enumerate(forma.jornadas):
            marcado = n < len(partidos) and partidos[n].id in presentes
            hoja.cell(row=renglon, column=columna, value=MARCA_ASISTENCIA if marcado else None)

        lugar = forma.fotos.get(renglon)
        if cedula is not None and lugar and j["foto"]:
            imagen = _foto_para_cedula(fotos_dir / j["foto"])
            if imagen is not None:
                columna, fila = lugar
                imagen.anchor = TwoCellAnchor(
                    editAs="oneCell",
                    _from=AnchorMarker(col=columna, colOff=_DESDE_FOTO[0], row=fila, rowOff=_DESDE_FOTO[1]),
                    to=AnchorMarker(col=columna, colOff=_HASTA_FOTO[0], row=fila + _ALTO_FOTO, rowOff=_HASTA_FOTO[1]),
                )
                cedula.add_image(imagen)

    for puesto, columna in (("entrenador", "responsable"), ("asistente", "asistente"), ("director", "director")):
        if puesto in forma.personal:
            hoja.cell(row=forma.personal[puesto], column=forma.columnas["nombre"], value=equipo[columna] or None)
    if cedula is not None:
        # El pie de cada credencial lleva el torneo, igual que las credenciales en PDF.
        for renglon in cedula.iter_rows():
            for celda in renglon:
                if isinstance(celda.value, str) and celda.value.upper().startswith(credenciales.CIUDAD):
                    celda.value = credenciales.pie(equipo["torneo"])
    libro.save(destino)


def _recorrer_referencias(cedula, forma: Forma, extra: int) -> None:
    """Las fórmulas que apuntan al personal se mueven junto con sus renglones."""
    patron = re.compile(rf"('?{re.escape(forma.hoja_registro)}'?!\$?[A-Z]+\$?)(\d+)")

    def mover(m):
        renglon = int(m.group(2))
        return m.group(1) + str(renglon + extra if renglon > forma.ultimo_renglon else renglon)

    for renglon in cedula.iter_rows():
        for celda in renglon:
            if isinstance(celda.value, str) and celda.value.startswith("="):
                celda.value = patron.sub(mover, celda.value)
