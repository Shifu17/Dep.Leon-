"""Base de datos SQLite: esquema, datos iniciales, respaldo y restauración."""

import sqlite3
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

NOMBRE_DB_RESPALDO = "liga.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ligas (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    modalidad TEXT NOT NULL CHECK (modalidad IN ('Fut 7', 'Fut 11')),
    dias TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY,
    liga_id INTEGER NOT NULL REFERENCES ligas(id) ON DELETE RESTRICT,
    nombre TEXT NOT NULL,
    anio_min INTEGER,
    anio_max INTEGER,
    UNIQUE (liga_id, nombre)
);
CREATE TABLE IF NOT EXISTS torneos (
    id INTEGER PRIMARY KEY,
    liga_id INTEGER NOT NULL REFERENCES ligas(id) ON DELETE RESTRICT,
    nombre TEXT NOT NULL,
    UNIQUE (liga_id, nombre)
);
CREATE TABLE IF NOT EXISTS equipos (
    id INTEGER PRIMARY KEY,
    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE RESTRICT,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id) ON DELETE RESTRICT,
    nombre TEXT NOT NULL,
    responsable TEXT NOT NULL DEFAULT '',
    telefono TEXT NOT NULL DEFAULT '',
    UNIQUE (torneo_id, categoria_id, nombre)
);
CREATE TABLE IF NOT EXISTS jugadores (
    id INTEGER PRIMARY KEY,
    equipo_id INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    fecha_nacimiento TEXT NOT NULL,
    numero INTEGER NOT NULL,
    posicion TEXT NOT NULL DEFAULT '',
    foto TEXT NOT NULL DEFAULT '',
    UNIQUE (equipo_id, numero),
    UNIQUE (equipo_id, nombre, fecha_nacimiento)
);
CREATE TABLE IF NOT EXISTS partidos (
    id INTEGER PRIMARY KEY,
    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE RESTRICT,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id) ON DELETE RESTRICT,
    jornada INTEGER NOT NULL,
    local_id INTEGER NOT NULL REFERENCES equipos(id) ON DELETE RESTRICT,
    visitante_id INTEGER NOT NULL REFERENCES equipos(id) ON DELETE RESTRICT,
    fecha TEXT,
    hora TEXT,
    minutos INTEGER NOT NULL,
    cancha TEXT,
    estado TEXT NOT NULL,
    CHECK (local_id <> visitante_id)
);
CREATE INDEX IF NOT EXISTS partidos_fecha ON partidos (fecha);
CREATE TABLE IF NOT EXISTS config_rol (
    torneo_id INTEGER PRIMARY KEY REFERENCES torneos(id) ON DELETE CASCADE,
    datos TEXT NOT NULL
);
"""

LIGAS_INICIALES = [
    ("Femenil", "Fut 7", "Lunes"),
    ("Libre Martes", "Fut 7", "Martes"),
    ("Libre Miércoles", "Fut 7", "Miércoles"),
    ("Libre Jueves", "Fut 7", "Jueves"),
    ("Infantil", "Fut 7", "Viernes y sábado"),
    ("Fut 11", "Fut 11", "Domingo"),
]

CATEGORIAS_INFANTILES = [
    (2009, 2010),
    (2011, 2012),
    (2013, 2014),
    (2015, 2016),
    (2017, 2018),
    (2019, 2020),
]


def conectar(ruta: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(ESQUEMA)
    _cargar_datos_iniciales(conn)
    return conn


def _cargar_datos_iniciales(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM ligas LIMIT 1").fetchone():
        return
    with conn:
        conn.executemany(
            "INSERT INTO ligas (nombre, modalidad, dias) VALUES (?, ?, ?)", LIGAS_INICIALES
        )
        infantil = conn.execute("SELECT id FROM ligas WHERE nombre = 'Infantil'").fetchone()["id"]
        conn.executemany(
            "INSERT INTO categorias (liga_id, nombre, anio_min, anio_max) VALUES (?, ?, ?, ?)",
            [(infantil, f"{a}-{b}", a, b) for a, b in CATEGORIAS_INFANTILES],
        )


def respaldar(conn: sqlite3.Connection, destino: Path | str, fotos_dir: Path) -> None:
    """Crea un .zip con la base de datos y las fotos de los jugadores."""
    with tempfile.TemporaryDirectory() as temporal:
        copia_ruta = Path(temporal) / NOMBRE_DB_RESPALDO
        copia = sqlite3.connect(copia_ruta)
        try:
            conn.backup(copia)
        finally:
            copia.close()
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as archivo:
            archivo.write(copia_ruta, NOMBRE_DB_RESPALDO)
            for foto in fotos_dir.glob("*.jpg"):
                archivo.write(foto, f"fotos/{foto.name}")


def restaurar(conn: sqlite3.Connection, origen: Path | str, fotos_dir: Path) -> None:
    """Reemplaza los datos actuales por los del respaldo, si este es válido."""
    error = "El archivo no es un respaldo de este programa."
    try:
        with zipfile.ZipFile(origen) as archivo, tempfile.TemporaryDirectory() as temporal:
            copia_ruta = Path(temporal) / NOMBRE_DB_RESPALDO
            copia_ruta.write_bytes(archivo.read(NOMBRE_DB_RESPALDO))
            fuente = sqlite3.connect(copia_ruta)
            try:
                tablas = {
                    f[0] for f in fuente.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                if not {"ligas", "categorias", "torneos", "equipos", "jugadores"} <= tablas:
                    raise ValueError(error)
                fuente.backup(conn)
                # Un respaldo de una versión anterior puede no traer las tablas nuevas.
                conn.executescript(ESQUEMA)
            finally:
                fuente.close()
            for nombre in archivo.namelist():
                # Solo fotos directas: se ignora cualquier otra ruta dentro del .zip.
                ruta = PurePosixPath(nombre)
                if ruta.parent == PurePosixPath("fotos") and ruta.suffix == ".jpg":
                    (fotos_dir / ruta.name).write_bytes(archivo.read(nombre))
    except (zipfile.BadZipFile, KeyError, sqlite3.DatabaseError) as exc:
        raise ValueError(error) from exc
