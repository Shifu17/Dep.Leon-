"""Contenido de los reportes, independiente de si se dibujan en PDF o en imagen."""

import sqlite3
from dataclasses import dataclass, field
from datetime import date

from . import cobros, estadisticas, liguilla, rol

IZQUIERDA = "izquierda"
CENTRO = "centro"
DERECHA = "derecha"


@dataclass(frozen=True)
class Columna:
    titulo: str
    peso: float
    alinear: str = CENTRO


@dataclass
class Seccion:
    titulo: str
    columnas: list[Columna]
    filas: list[list[str]]
    nota: str = ""


@dataclass
class Hoja:
    titulo: str
    subtitulo: str
    secciones: list[Seccion] = field(default_factory=list)

    @property
    def vacia(self) -> bool:
        return not any(s.filas for s in self.secciones)


@dataclass
class HojaLlave:
    titulo: str
    subtitulo: str
    rondas: list[tuple[str, list[str]]] = field(default_factory=list)
    campeon: str = ""

    @property
    def vacia(self) -> bool:
        return not self.rondas


def _torneo(conn: sqlite3.Connection, torneo_id: int) -> str:
    return rol.titulo_torneo(conn.execute("SELECT nombre FROM torneos WHERE id = ?", (torneo_id,)).fetchone()[0])


def _categorias(conn, torneo_id: int, categoria_id: int | None) -> list[sqlite3.Row]:
    """Categorías del torneo que tienen equipos, o solo la indicada."""
    return conn.execute(
        """SELECT DISTINCT c.id, c.nombre FROM categorias c JOIN equipos e ON e.categoria_id = c.id
           WHERE e.torneo_id = ? AND (? IS NULL OR c.id = ?) ORDER BY c.nombre COLLATE ES""",
        (torneo_id, categoria_id, categoria_id),
    ).fetchall()


def fechas_de_rol(conn: sqlite3.Connection, torneo_id: int, categoria_id: int | None = None) -> list[str]:
    return [
        f["fecha"]
        for f in conn.execute(
            "SELECT DISTINCT fecha FROM partidos WHERE torneo_id = ? AND fecha IS NOT NULL "
            "AND (? IS NULL OR categoria_id = ?) ORDER BY fecha",
            (torneo_id, categoria_id, categoria_id),
        )
    ]


def hoja_rol(
    conn: sqlite3.Connection, torneo_id: int, categoria_id: int | None = None, fecha: str | None = None
) -> Hoja:
    """Rol con las columnas de la hoja de la liga, una sección por día."""
    columnas = [
        Columna("Hora", 1), Columna("Equipo", 3), Columna("Equipo", 3),
        Columna("Categoría", 2.4), Columna("Cancha", 1),
    ]
    filas = conn.execute(
        """SELECT p.fecha, p.hora, p.cancha, p.jornada, l.nombre AS local, v.nombre AS visitante,
                  c.nombre AS categoria
           FROM partidos p JOIN equipos l ON l.id = p.local_id
           JOIN equipos v ON v.id = p.visitante_id JOIN categorias c ON c.id = p.categoria_id
           WHERE p.torneo_id = ? AND p.fecha IS NOT NULL
             AND (? IS NULL OR p.categoria_id = ?) AND (? IS NULL OR p.fecha = ?)
           ORDER BY p.fecha, p.cancha, p.hora""",
        (torneo_id, categoria_id, categoria_id, fecha, fecha),
    ).fetchall()

    dias: dict[str, list[list[str]]] = {}
    for p in filas:
        categoria = p["categoria"]
        if p["jornada"] > rol.BASE_LIGUILLA:
            categoria = f"{categoria} · {rol.nombre_jornada(p['jornada'])}"
        dias.setdefault(p["fecha"], []).append(
            [p["hora"], p["local"], p["visitante"], categoria, rol.nombre_cancha(p["cancha"])]
        )

    secciones = []
    for dia, renglones in dias.items():
        descansan = rol.descansos(conn, torneo_id, dia, categoria_id)
        nota = "Descansan: " + ", ".join(f"{e} ({c})" for c, e in descansan) if descansan else ""
        secciones.append(
            Seccion(rol.fecha_larga(date.fromisoformat(dia)), columnas, renglones, nota)
        )
    return Hoja("Rol de juegos", _torneo(conn, torneo_id), secciones)


def hoja_tabla(conn: sqlite3.Connection, torneo_id: int, categoria_id: int | None = None) -> Hoja:
    columnas = [Columna("Pos.", 0.8), Columna("Equipo", 4)] + [
        Columna(t, 0.8) for t in ("PJ", "PG", "PE", "PP", "GF", "GC", "DG", "Pts")
    ]
    secciones = []
    for c in _categorias(conn, torneo_id, categoria_id):
        tabla = estadisticas.tabla_posiciones(conn, torneo_id, c["id"])
        secciones.append(
            Seccion(
                f"Categoría {c['nombre']}",
                columnas,
                [
                    [str(i), f.nombre, *map(str, (f.pj, f.pg, f.pe, f.pp, f.gf, f.gc)), f"{f.dg:+d}", str(f.pts)]
                    for i, f in enumerate(tabla, start=1)
                ],
            )
        )
    return Hoja("Tabla de posiciones", _torneo(conn, torneo_id), secciones)


def hoja_goleadores(conn: sqlite3.Connection, torneo_id: int, categoria_id: int | None = None) -> Hoja:
    secciones = []
    for c in _categorias(conn, torneo_id, categoria_id):
        anotadores = estadisticas.goleadores(conn, torneo_id, c["id"])
        if anotadores:
            secciones.append(
                Seccion(
                    f"Goleadores: {c['nombre']}",
                    [Columna("#", 0.7), Columna("Jugador", 4), Columna("Equipo", 3), Columna("Goles", 1)],
                    [
                        [str(i), g["nombre"], g["equipo"], str(g["goles"])]
                        for i, g in enumerate(anotadores, start=1)
                    ],
                )
            )
        porterias = estadisticas.menos_goleados(estadisticas.tabla_posiciones(conn, torneo_id, c["id"]))
        if porterias:
            secciones.append(
                Seccion(
                    f"Portería menos goleada: {c['nombre']}",
                    [
                        Columna("#", 0.7), Columna("Equipo", 4), Columna("PJ", 1),
                        Columna("Recibidos", 1.3), Columna("Promedio", 1.3),
                    ],
                    [
                        [str(i), f.nombre, str(f.pj), str(f.gc), f"{f.gc / f.pj:.2f}"]
                        for i, f in enumerate(porterias, start=1)
                    ],
                )
            )
    return Hoja("Goleadores y portería menos goleada", _torneo(conn, torneo_id), secciones)


def hoja_adeudos(conn: sqlite3.Connection, torneo_id: int, categoria_id: int | None = None) -> Hoja:
    cobros.sincronizar_torneo(conn, torneo_id)
    columnas = [
        Columna("Equipo", 4), Columna("Cargos", 1.5, DERECHA),
        Columna("Pagado", 1.5, DERECHA), Columna("Saldo", 1.5, DERECHA),
    ]
    secciones = []
    for c in _categorias(conn, torneo_id, categoria_id):
        lista = [a for a in cobros.adeudos(conn, torneo_id, c["id"]) if a.cargos]
        if lista:
            secciones.append(
                Seccion(
                    f"Categoría {c['nombre']}",
                    columnas,
                    [
                        [a.equipo, cobros.dinero(a.cargos), cobros.dinero(a.pagado), cobros.dinero(a.saldo)]
                        for a in lista
                    ],
                )
            )
    total = cobros.resumen(conn, torneo_id, categoria_id)
    if secciones:
        secciones.append(
            Seccion(
                "Total",
                [Columna("Total de cargos", 1), Columna("Cobrado", 1), Columna("Pendiente", 1)],
                [[cobros.dinero(total.cargado), cobros.dinero(total.cobrado), cobros.dinero(total.pendiente)]],
            )
        )
    return Hoja("Adeudos", _torneo(conn, torneo_id), secciones)


def hoja_llave(conn: sqlite3.Connection, torneo_id: int, categoria_id: int) -> HojaLlave:
    nombre = conn.execute("SELECT nombre FROM categorias WHERE id = ?", (categoria_id,)).fetchone()[0]
    hoja = HojaLlave(f"Liguilla: {nombre}", _torneo(conn, torneo_id))
    actual = liguilla.obtener(conn, torneo_id, categoria_id)
    if actual is None:
        return hoja
    rondas: dict[str, list[str]] = {}
    for v in liguilla.vista(conn, actual["id"]):
        rondas.setdefault(v.ronda, []).append(liguilla.texto_llave(v))
    hoja.rondas = list(rondas.items())
    hoja.campeon = liguilla.campeon(conn, actual["id"])
    return hoja


def nombre_archivo(texto: str) -> str:
    return "".join(c for c in texto if c not in '<>:"/\\|?*').strip()
