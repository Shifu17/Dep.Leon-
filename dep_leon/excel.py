"""Plantilla de Excel para registrar jugadores y su importación al sistema."""

import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from .jugadores import NUMERO_MAX, POSICIONES, error_de_edad, guardar_foto

HOJA = "Jugadores"
COLUMNAS = {
    "categoria": "Categoría",
    "equipo": "Equipo",
    "nombre": "Nombre completo",
    "fecha": "Fecha de nacimiento",
    "numero": "Número de playera",
    "posicion": "Posición",
    "foto": "Foto",
}
ANCHOS = [14, 24, 36, 20, 18, 14, 26]
FILAS_CON_AYUDA = 1000
MAX_FILAS = 5000
EXTENSIONES_FOTO = (".jpg", ".jpeg", ".png")

VERDE = PatternFill("solid", fgColor="1E7F4C")
AMBAR = PatternFill("solid", fgColor="E4EDE8")
LAVANDA = PatternFill("solid", fgColor="F4F7F5")
BORDE = Border(*[Side(style="thin", color="CBD8D0")] * 4)
AJUSTE = Alignment(wrap_text=True, vertical="top")


def crear_plantilla(conn: sqlite3.Connection, liga_id: int, destino: Path | str) -> None:
    liga = conn.execute("SELECT nombre FROM ligas WHERE id = ?", (liga_id,)).fetchone()
    categorias = conn.execute(
        "SELECT nombre, anio_min, anio_max FROM categorias WHERE liga_id = ? ORDER BY nombre",
        (liga_id,),
    ).fetchall()

    libro = Workbook()
    instrucciones = libro.active
    instrucciones.title = "Instrucciones"
    hoja = libro.create_sheet(HOJA)
    listas = libro.create_sheet("Listas")
    listas.sheet_state = "hidden"

    _llenar_instrucciones(instrucciones, liga["nombre"], categorias)
    _llenar_hoja_jugadores(hoja, listas, categorias)
    libro.save(destino)


def _llenar_hoja_jugadores(hoja, listas, categorias) -> None:
    for i, (titulo, ancho) in enumerate(zip(COLUMNAS.values(), ANCHOS), start=1):
        celda = hoja.cell(row=1, column=i, value=titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = VERDE
        celda.border = BORDE
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        hoja.column_dimensions[celda.column_letter].width = ancho
    hoja.freeze_panes = "A2"

    for i, categoria in enumerate(categorias, start=1):
        listas.cell(row=i, column=1, value=categoria["nombre"])
    for i, posicion in enumerate(POSICIONES, start=1):
        listas.cell(row=i, column=2, value=posicion)

    ultimo = FILAS_CON_AYUDA + 1
    if categorias:
        lista_cat = DataValidation(
            type="list", formula1=f"=Listas!$A$1:$A${len(categorias)}", showErrorMessage=True
        )
        lista_cat.error = "Elige una categoría de la lista."
        hoja.add_data_validation(lista_cat)
        lista_cat.add(f"A2:A{ultimo}")
    lista_pos = DataValidation(
        type="list", formula1=f"=Listas!$B$1:$B${len(POSICIONES)}", showErrorMessage=True
    )
    lista_pos.error = "Elige una posición de la lista."
    hoja.add_data_validation(lista_pos)
    lista_pos.add(f"F2:F{ultimo}")

    for fila in range(2, ultimo + 1):
        hoja.cell(row=fila, column=4).number_format = "DD/MM/YYYY"


def _llenar_instrucciones(hoja, liga: str, categorias) -> None:
    hoja.column_dimensions["A"].width = 24
    hoja.column_dimensions["B"].width = 14
    hoja.column_dimensions["C"].width = 58
    hoja.column_dimensions["D"].width = 24

    fila = 1
    hoja.cell(row=fila, column=1, value=f"Registro de jugadores: liga {liga}").font = Font(
        bold=True, size=14
    )
    fila += 2

    pasos = [
        f"1. Ve a la hoja «{HOJA}» y captura un jugador por renglón, empezando en el renglón 2.",
        "2. Si hay fotos, ponlas en la misma carpeta que este archivo o en una subcarpeta «fotos».",
        "3. En la columna «Foto», escribe el nombre del archivo de cada jugador (ejemplo: juan.jpg).",
        "4. Guarda y cierra el archivo.",
        "5. En el programa, entra a «Equipos y jugadores», elige el torneo y pulsa «Importar Excel».",
        "6. Revisa la vista previa. Corrige en Excel los renglones con error y vuelve a importarlo; "
        "los jugadores que ya estén registrados se actualizan, no se duplican.",
    ]
    for paso in pasos:
        celda = hoja.cell(row=fila, column=1, value=paso)
        hoja.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=4)
        celda.alignment = AJUSTE
        hoja.row_dimensions[fila].height = 32 if len(paso) > 95 else 18
        fila += 1
    fila += 1

    fila = _tabla(
        hoja,
        fila,
        ["Columna", "¿Obligatoria?", "Cómo llenarla", "Ejemplo"],
        [
            ["Categoría", "Sí", "Elígela de la lista.", categorias[0]["nombre"] if categorias else ""],
            ["Equipo", "Sí", "Si el equipo no existe, se crea en esa categoría al importar.", "Pegasos"],
            ["Nombre completo", "Sí", "Nombre y apellidos.", "Juan Pérez López"],
            ["Fecha de nacimiento", "Sí", "Día/mes/año. Debe corresponder a la categoría.", "15/03/2015"],
            ["Número de playera", "Sí", f"De 0 a {NUMERO_MAX}, sin repetir dentro del equipo.", "10"],
            ["Posición", "No", "Elígela de la lista.", "Delantero"],
            ["Foto", "No", "Nombre del archivo JPG o PNG. Sin ella, el jugador se registra sin foto.", "juan.jpg"],
        ],
    )
    fila += 1

    if categorias:
        filas = []
        for c in categorias:
            if c["anio_min"] is None and c["anio_max"] is None:
                anios = "Sin límite de edad"
            else:
                anios = f"{c['anio_min'] or 'Sin mínimo'} a {c['anio_max'] or 'sin máximo'}"
            filas.append([c["nombre"], "", anios, ""])
        _tabla(hoja, fila, ["Categoría", "", "Años de nacimiento permitidos", ""], filas)


def _tabla(hoja, fila: int, encabezados: list[str], filas: list[list[str]]) -> int:
    for i, titulo in enumerate(encabezados, start=1):
        celda = hoja.cell(row=fila, column=i, value=titulo)
        celda.font = Font(bold=True)
        celda.fill = AMBAR
        celda.border = BORDE
    fila += 1
    for valores in filas:
        for i, valor in enumerate(valores, start=1):
            celda = hoja.cell(row=fila, column=i, value=valor)
            celda.fill = LAVANDA
            celda.border = BORDE
            celda.alignment = AJUSTE
        if len(valores[2]) > 60:
            hoja.row_dimensions[fila].height = 30
        fila += 1
    return fila


@dataclass
class Fila:
    renglon: int
    categoria: str = ""
    equipo: str = ""
    nombre: str = ""
    fecha: date | None = None
    numero: int | None = None
    posicion: str = ""
    foto: Path | None = None
    categoria_id: int | None = None
    jugador_id: int | None = None
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def valida(self) -> bool:
        return not self.errores


def _clave(texto: str) -> str:
    """Normaliza para comparar sin distinguir mayúsculas, acentos ni espacios de más."""
    sin_acentos = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return " ".join(sin_acentos.casefold().split())


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return " ".join(str(valor).split())


def _leer_fecha(valor) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(_texto(valor), formato).date()
        except ValueError:
            continue
    return None


def _leer_numero(valor) -> int | None:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, str) and valor.strip().isdigit():
        return int(valor.strip())
    return None


def _buscar_foto(nombre: str, carpeta: Path) -> Path | None:
    """Busca solo dentro de la carpeta del Excel y su subcarpeta «fotos»."""
    base = Path(nombre.replace("\\", "/")).name
    if not base:
        return None
    candidatos = [base] if Path(base).suffix else [base + ext for ext in EXTENSIONES_FOTO]
    for directorio in (carpeta, carpeta / "fotos"):
        for candidato in candidatos:
            ruta = directorio / candidato
            if ruta.is_file():
                return ruta
    return None


def analizar(conn: sqlite3.Connection, ruta: Path | str, torneo_id: int) -> list[Fila]:
    """Lee y valida el archivo sin modificar nada. Lanza ValueError si no es la plantilla."""
    ruta = Path(ruta)
    try:
        libro = load_workbook(ruta, data_only=True, read_only=True)
    except PermissionError as exc:
        raise ValueError("El archivo está abierto en Excel. Ciérralo e inténtalo de nuevo.") from exc
    except Exception as exc:
        raise ValueError("No se pudo abrir el archivo de Excel.") from exc

    try:
        if HOJA not in libro.sheetnames:
            raise ValueError(f"El archivo no tiene la hoja «{HOJA}». Usa la plantilla del programa.")
        renglones = libro[HOJA].iter_rows(values_only=True)
        encabezado = [_clave(_texto(v)) for v in next(renglones, ())]
        indices = {}
        for campo, titulo in COLUMNAS.items():
            if _clave(titulo) not in encabezado:
                raise ValueError(f"Falta la columna «{titulo}». Usa la plantilla del programa.")
            indices[campo] = encabezado.index(_clave(titulo))

        crudos = []
        for numero, renglon in enumerate(renglones, start=2):
            valores = {c: renglon[i] if i < len(renglon) else None for c, i in indices.items()}
            if any(_texto(v) for v in valores.values()):
                crudos.append((numero, valores))
                if len(crudos) > MAX_FILAS:
                    raise ValueError(f"El archivo supera el máximo de {MAX_FILAS} jugadores.")
    finally:
        libro.close()

    torneo = conn.execute("SELECT liga_id FROM torneos WHERE id = ?", (torneo_id,)).fetchone()
    categorias = {
        _clave(c["nombre"]): c
        for c in conn.execute("SELECT * FROM categorias WHERE liga_id = ?", (torneo["liga_id"],))
    }
    existentes: dict[tuple, dict] = {}
    for j in conn.execute(
        """SELECT j.id, j.nombre, j.fecha_nacimiento, j.numero, e.categoria_id, e.nombre AS equipo
           FROM jugadores j JOIN equipos e ON e.id = j.equipo_id WHERE e.torneo_id = ?""",
        (torneo_id,),
    ):
        equipo = (j["categoria_id"], _clave(j["equipo"]))
        grupo = existentes.setdefault(equipo, {"personas": {}, "numeros": {}})
        grupo["personas"][(_clave(j["nombre"]), j["fecha_nacimiento"])] = j["id"]
        grupo["numeros"][j["numero"]] = j["id"]

    return _validar(crudos, categorias, existentes, ruta.parent)


def _validar(crudos, categorias, existentes, carpeta: Path) -> list[Fila]:
    filas = []
    numeros_archivo: dict[tuple, int] = {}
    personas_archivo: dict[tuple, int] = {}

    for renglon, v in crudos:
        fila = Fila(
            renglon=renglon,
            categoria=_texto(v["categoria"]),
            equipo=_texto(v["equipo"]),
            nombre=_texto(v["nombre"]),
            posicion=_texto(v["posicion"]),
        )
        filas.append(fila)

        categoria = categorias.get(_clave(fila.categoria))
        if categoria is None:
            fila.errores.append(f"Categoría no válida: «{fila.categoria}».")
        else:
            fila.categoria = categoria["nombre"]
            fila.categoria_id = categoria["id"]
        if not fila.equipo:
            fila.errores.append("Falta el equipo.")
        if not fila.nombre:
            fila.errores.append("Falta el nombre.")

        fila.fecha = _leer_fecha(v["fecha"])
        if fila.fecha is None:
            fila.errores.append("Fecha de nacimiento no válida; usa día/mes/año.")
        elif categoria is not None:
            motivo = error_de_edad(fila.fecha, categoria["anio_min"], categoria["anio_max"])
            if motivo:
                fila.errores.append(motivo)

        fila.numero = _leer_numero(v["numero"])
        if fila.numero is None or not 0 <= fila.numero <= NUMERO_MAX:
            fila.errores.append(f"Número de playera no válido; debe ser de 0 a {NUMERO_MAX}.")
            fila.numero = None

        if fila.posicion:
            posicion = next((p for p in POSICIONES if _clave(p) == _clave(fila.posicion)), None)
            if posicion is None:
                fila.errores.append(f"Posición no válida: «{fila.posicion}».")
            else:
                fila.posicion = posicion

        nombre_foto = _texto(v["foto"])
        if nombre_foto:
            fila.foto = _buscar_foto(nombre_foto, carpeta)
            if fila.foto is None:
                fila.avisos.append(f"No se encontró la foto «{nombre_foto}»; se registrará sin ella.")

        if fila.categoria_id is None or not fila.equipo:
            continue

        clave_equipo = (fila.categoria_id, _clave(fila.equipo))
        grupo = existentes.get(clave_equipo, {"personas": {}, "numeros": {}})
        if fila.nombre and fila.fecha:
            persona = (_clave(fila.nombre), fila.fecha.isoformat())
            fila.jugador_id = grupo["personas"].get(persona)
            previo = personas_archivo.setdefault((clave_equipo, persona), renglon)
            if previo != renglon:
                fila.errores.append(f"Jugador repetido; ya aparece en el renglón {previo}.")
        if fila.numero is not None:
            previo = numeros_archivo.setdefault((clave_equipo, fila.numero), renglon)
            if previo != renglon:
                fila.errores.append(f"El número {fila.numero} ya se usa en el renglón {previo}.")
            dueno = grupo["numeros"].get(fila.numero)
            if dueno is not None and dueno != fila.jugador_id:
                fila.errores.append(f"El número {fila.numero} ya lo tiene otro jugador del equipo.")

    return filas


def importar(
    conn: sqlite3.Connection, filas: list[Fila], torneo_id: int, fotos_dir: Path
) -> tuple[int, int, int]:
    """Registra las filas válidas en una sola transacción.

    Devuelve (jugadores nuevos, jugadores actualizados, equipos creados).
    """
    nuevos = actualizados = equipos_creados = 0
    fotos_copiadas: list[Path] = []
    equipos = {
        (e["categoria_id"], _clave(e["nombre"])): e["id"]
        for e in conn.execute("SELECT * FROM equipos WHERE torneo_id = ?", (torneo_id,))
    }

    try:
        with conn:
            for fila in filas:
                if not fila.valida:
                    continue
                clave = (fila.categoria_id, _clave(fila.equipo))
                equipo_id = equipos.get(clave)
                if equipo_id is None:
                    equipo_id = conn.execute(
                        "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
                        (torneo_id, fila.categoria_id, fila.equipo),
                    ).lastrowid
                    equipos[clave] = equipo_id
                    equipos_creados += 1

                foto = ""
                if fila.foto is not None:
                    try:
                        foto = guardar_foto(fila.foto, fotos_dir)
                        fotos_copiadas.append(fotos_dir / foto)
                    except ValueError as exc:
                        fila.avisos.append(f"{exc} Se registró sin ella.")

                if fila.jugador_id is None:
                    conn.execute(
                        """INSERT INTO jugadores
                           (equipo_id, nombre, fecha_nacimiento, numero, posicion, foto)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (equipo_id, fila.nombre, fila.fecha.isoformat(), fila.numero, fila.posicion, foto),
                    )
                    nuevos += 1
                else:
                    conn.execute(
                        """UPDATE jugadores SET numero = ?, posicion = ?,
                           foto = CASE WHEN ? <> '' THEN ? ELSE foto END WHERE id = ?""",
                        (fila.numero, fila.posicion, foto, foto, fila.jugador_id),
                    )
                    actualizados += 1
    except Exception:
        for ruta in fotos_copiadas:
            ruta.unlink(missing_ok=True)
        raise
    return nuevos, actualizados, equipos_creados
