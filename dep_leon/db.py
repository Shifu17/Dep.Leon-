"""Base de datos SQLite: esquema, datos iniciales, respaldo y restauración."""

import sqlite3
import tempfile
import unicodedata
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
    asistente TEXT NOT NULL DEFAULT '',
    director TEXT NOT NULL DEFAULT '',
    rama TEXT NOT NULL DEFAULT '',
    UNIQUE (torneo_id, categoria_id, nombre)
);
CREATE TABLE IF NOT EXISTS jugadores (
    id INTEGER PRIMARY KEY,
    equipo_id INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    fecha_nacimiento TEXT NOT NULL,
    numero INTEGER,
    posicion TEXT NOT NULL DEFAULT '',
    foto TEXT NOT NULL DEFAULT '',
    curp TEXT NOT NULL DEFAULT '',
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
CREATE TABLE IF NOT EXISTS resultados (
    partido_id INTEGER PRIMARY KEY REFERENCES partidos(id) ON DELETE CASCADE,
    goles_local INTEGER NOT NULL CHECK (goles_local >= 0),
    goles_visitante INTEGER NOT NULL CHECK (goles_visitante >= 0),
    ausente_id INTEGER REFERENCES equipos(id) ON DELETE RESTRICT,
    paga TEXT
);
CREATE TABLE IF NOT EXISTS goles (
    partido_id INTEGER NOT NULL REFERENCES partidos(id) ON DELETE CASCADE,
    jugador_id INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE RESTRICT,
    cantidad INTEGER NOT NULL CHECK (cantidad > 0),
    PRIMARY KEY (partido_id, jugador_id)
);
CREATE TABLE IF NOT EXISTS reglas_torneo (
    torneo_id INTEGER PRIMARY KEY REFERENCES torneos(id) ON DELETE CASCADE,
    victoria INTEGER NOT NULL,
    empate INTEGER NOT NULL,
    derrota INTEGER NOT NULL,
    default_goles INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS tarifas (
    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
    arbitraje INTEGER NOT NULL CHECK (arbitraje >= 0),
    inscripcion INTEGER NOT NULL CHECK (inscripcion >= 0),
    PRIMARY KEY (torneo_id, categoria_id)
);
CREATE TABLE IF NOT EXISTS cargos (
    id INTEGER PRIMARY KEY,
    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE RESTRICT,
    equipo_id INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    partido_id INTEGER REFERENCES partidos(id) ON DELETE RESTRICT,
    concepto TEXT NOT NULL,
    monto INTEGER NOT NULL CHECK (monto >= 0),
    fecha TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS cargo_por_partido ON cargos (partido_id, equipo_id)
    WHERE partido_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS cargo_inscripcion ON cargos (equipo_id)
    WHERE partido_id IS NULL;
CREATE TABLE IF NOT EXISTS pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipo_id INTEGER NOT NULL REFERENCES equipos(id) ON DELETE RESTRICT,
    fecha TEXT NOT NULL,
    monto INTEGER NOT NULL CHECK (monto > 0),
    nota TEXT NOT NULL DEFAULT '',
    anulado INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS aplicaciones (
    pago_id INTEGER NOT NULL REFERENCES pagos(id) ON DELETE CASCADE,
    cargo_id INTEGER NOT NULL REFERENCES cargos(id) ON DELETE RESTRICT,
    monto INTEGER NOT NULL CHECK (monto > 0),
    PRIMARY KEY (pago_id, cargo_id)
);
CREATE TABLE IF NOT EXISTS tarifas (
    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
    arbitraje INTEGER NOT NULL CHECK (arbitraje >= 0),
    inscripcion INTEGER NOT NULL CHECK (inscripcion >= 0),
    PRIMARY KEY (torneo_id, categoria_id)
);
CREATE TABLE IF NOT EXISTS cargos (
    id INTEGER PRIMARY KEY,
    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE RESTRICT,
    equipo_id INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    partido_id INTEGER REFERENCES partidos(id) ON DELETE RESTRICT,
    concepto TEXT NOT NULL,
    monto INTEGER NOT NULL CHECK (monto >= 0),
    fecha TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS cargo_por_partido ON cargos (partido_id, equipo_id)
    WHERE partido_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS cargo_inscripcion ON cargos (equipo_id)
    WHERE partido_id IS NULL;
CREATE TABLE IF NOT EXISTS pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipo_id INTEGER NOT NULL REFERENCES equipos(id) ON DELETE RESTRICT,
    fecha TEXT NOT NULL,
    monto INTEGER NOT NULL CHECK (monto > 0),
    nota TEXT NOT NULL DEFAULT '',
    anulado INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS aplicaciones (
    pago_id INTEGER NOT NULL REFERENCES pagos(id) ON DELETE CASCADE,
    cargo_id INTEGER NOT NULL REFERENCES cargos(id) ON DELETE RESTRICT,
    monto INTEGER NOT NULL CHECK (monto > 0),
    PRIMARY KEY (pago_id, cargo_id)
);
CREATE TABLE IF NOT EXISTS liguillas (
    id INTEGER PRIMARY KEY,
    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE RESTRICT,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id) ON DELETE RESTRICT,
    desde INTEGER NOT NULL,
    hasta INTEGER NOT NULL,
    desempate TEXT NOT NULL,
    UNIQUE (torneo_id, categoria_id)
);
CREATE TABLE IF NOT EXISTS llaves (
    id INTEGER PRIMARY KEY,
    liguilla_id INTEGER NOT NULL REFERENCES liguillas(id) ON DELETE CASCADE,
    ronda INTEGER NOT NULL,
    orden INTEGER NOT NULL,
    equipo_a_id INTEGER REFERENCES equipos(id) ON DELETE RESTRICT,
    semilla_a INTEGER,
    equipo_b_id INTEGER REFERENCES equipos(id) ON DELETE RESTRICT,
    semilla_b INTEGER,
    partido_id INTEGER REFERENCES partidos(id) ON DELETE RESTRICT,
    ganador_id INTEGER REFERENCES equipos(id) ON DELETE RESTRICT,
    penales_local INTEGER,
    penales_visitante INTEGER,
    UNIQUE (liguilla_id, ronda, orden)
);
CREATE TABLE IF NOT EXISTS disponibilidad (
    equipo_id INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    dia INTEGER NOT NULL CHECK (dia BETWEEN 0 AND 6),
    desde INTEGER NOT NULL,
    hasta INTEGER NOT NULL,
    PRIMARY KEY (equipo_id, dia)
);
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    usuario TEXT NOT NULL,
    contrasena TEXT NOT NULL,
    codigo TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asistencias (
    partido_id INTEGER NOT NULL REFERENCES partidos(id) ON DELETE CASCADE,
    jugador_id INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    PRIMARY KEY (partido_id, jugador_id)
);
CREATE TABLE IF NOT EXISTS arbitros (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    telefono TEXT NOT NULL DEFAULT '',
    foto TEXT NOT NULL DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS arbitrajes (
    partido_id INTEGER PRIMARY KEY REFERENCES partidos(id) ON DELETE CASCADE,
    arbitro_id INTEGER NOT NULL REFERENCES arbitros(id) ON DELETE RESTRICT,
    calificacion INTEGER CHECK (calificacion BETWEEN 1 AND 5)
);
CREATE TABLE IF NOT EXISTS config_rol (
    torneo_id INTEGER PRIMARY KEY REFERENCES torneos(id) ON DELETE CASCADE,
    datos TEXT NOT NULL
);
"""

# Cómo se crea la tabla de jugadores hoy; la migración copia los datos de versiones anteriores a ella.
TABLA_JUGADORES = """CREATE TABLE jugadores (
    id INTEGER PRIMARY KEY,
    equipo_id INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    fecha_nacimiento TEXT NOT NULL,
    numero INTEGER,
    posicion TEXT NOT NULL DEFAULT '',
    foto TEXT NOT NULL DEFAULT '',
    curp TEXT NOT NULL DEFAULT '',
    UNIQUE (equipo_id, numero),
    UNIQUE (equipo_id, nombre, fecha_nacimiento)
);"""


def _migrar(conn: sqlite3.Connection) -> None:
    """Pone al día una base de una versión anterior sin perder datos."""
    # Hasta la 0.9.6 el equipo solo guardaba un responsable; la hoja de registro trae más personal.
    del_equipo = {c["name"] for c in conn.execute("PRAGMA table_info(equipos)")}
    for columna in ("asistente", "director", "rama"):
        if columna not in del_equipo:
            with conn:
                conn.execute(f"ALTER TABLE equipos ADD COLUMN {columna} TEXT NOT NULL DEFAULT ''")
    _migrar_jugadores(conn)


def _migrar_jugadores(conn: sqlite3.Connection) -> None:
    """Hasta la 0.9.5 el número de playera era obligatorio y no se guardaba la CURP; las hojas de
    registro de los equipos suelen traer jugadores sin número."""
    columnas = {c["name"]: c for c in conn.execute("PRAGMA table_info(jugadores)")}
    if "curp" in columnas and not columnas["numero"]["notnull"]:
        return
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with conn:
            conn.execute("BEGIN")  # todo o nada: el esquema también entra en la transacción
            conn.execute(TABLA_JUGADORES.replace("jugadores (", "jugadores_nueva (", 1))
            conn.execute(
                """INSERT INTO jugadores_nueva (id, equipo_id, nombre, fecha_nacimiento, numero, posicion, foto)
                   SELECT id, equipo_id, nombre, fecha_nacimiento, numero, posicion, foto FROM jugadores"""
            )
            conn.execute("DROP TABLE jugadores")
            conn.execute("ALTER TABLE jugadores_nueva RENAME TO jugadores")
            if conn.execute("PRAGMA foreign_key_check").fetchone():
                raise sqlite3.IntegrityError("La migración de jugadores dejó referencias rotas.")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


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


def clave_orden(texto: str) -> str:
    """Clave de orden alfabético en español: sin distinguir acentos, con la ñ después de la n."""
    plano = texto.casefold().replace("ñ", "n\uffff")
    sin_acentos = unicodedata.normalize("NFD", plano)
    return "".join(c for c in sin_acentos if not unicodedata.combining(c))


def _comparar_es(a: str, b: str) -> int:
    x, y = clave_orden(a), clave_orden(b)
    return (x > y) - (x < y)


def conectar(ruta: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(ruta)
    conn.create_collation("ES", _comparar_es)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(ESQUEMA)
    _migrar(conn)
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
                # La cuenta es de esta computadora: un respaldo no debe cambiar quién entra.
                cuenta = conn.execute("SELECT * FROM usuarios").fetchall()
                fuente.backup(conn)
                # Un respaldo de una versión anterior puede no traer las tablas nuevas.
                conn.executescript(ESQUEMA)
                _migrar(conn)
                with conn:
                    conn.execute("DELETE FROM usuarios")
                    conn.executemany(
                        "INSERT INTO usuarios (id, usuario, contrasena, codigo) VALUES (?, ?, ?, ?)",
                        [tuple(c) for c in cuenta],
                    )
            finally:
                fuente.close()
            for nombre in archivo.namelist():
                # Solo fotos directas: se ignora cualquier otra ruta dentro del .zip.
                ruta = PurePosixPath(nombre)
                if ruta.parent == PurePosixPath("fotos") and ruta.suffix == ".jpg":
                    (fotos_dir / ruta.name).write_bytes(archivo.read(nombre))
    except (zipfile.BadZipFile, KeyError, sqlite3.DatabaseError) as exc:
        raise ValueError(error) from exc
