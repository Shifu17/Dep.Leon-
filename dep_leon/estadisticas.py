"""Tabla de posiciones, goleadores y portería menos goleada."""

import sqlite3
from dataclasses import dataclass
from itertools import groupby

from .resultados import obtener_reglas


@dataclass
class FilaTabla:
    equipo_id: int
    nombre: str
    pj: int = 0
    pg: int = 0
    pe: int = 0
    pp: int = 0
    gf: int = 0
    gc: int = 0
    pts: int = 0

    @property
    def dg(self) -> int:
        return self.gf - self.gc


def _resultados(conn: sqlite3.Connection, torneo_id: int, categoria_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT p.local_id, p.visitante_id, r.goles_local, r.goles_visitante
           FROM resultados r JOIN partidos p ON p.id = r.partido_id
           WHERE p.torneo_id = ? AND p.categoria_id = ?""",
        (torneo_id, categoria_id),
    ).fetchall()


def _sumar(fila: FilaTabla, a_favor: int, en_contra: int, reglas) -> None:
    fila.pj += 1
    fila.gf += a_favor
    fila.gc += en_contra
    if a_favor > en_contra:
        fila.pg += 1
        fila.pts += reglas.victoria
    elif a_favor == en_contra:
        fila.pe += 1
        fila.pts += reglas.empate
    else:
        fila.pp += 1
        fila.pts += reglas.derrota


def tabla_posiciones(conn: sqlite3.Connection, torneo_id: int, categoria_id: int) -> list[FilaTabla]:
    """Ordena por puntos, diferencia de goles, goles a favor y resultados entre los empatados."""
    reglas = obtener_reglas(conn, torneo_id)
    filas = {
        e["id"]: FilaTabla(e["id"], e["nombre"])
        for e in conn.execute(
            "SELECT id, nombre FROM equipos WHERE torneo_id = ? AND categoria_id = ?",
            (torneo_id, categoria_id),
        )
    }
    partidos = _resultados(conn, torneo_id, categoria_id)
    for p in partidos:
        _sumar(filas[p["local_id"]], p["goles_local"], p["goles_visitante"], reglas)
        _sumar(filas[p["visitante_id"]], p["goles_visitante"], p["goles_local"], reglas)

    def principal(f: FilaTabla):
        return (-f.pts, -f.dg, -f.gf)

    ordenadas: list[FilaTabla] = []
    for _, grupo in groupby(sorted(filas.values(), key=principal), key=principal):
        ordenadas += _desempatar(list(grupo), partidos, reglas)
    return ordenadas


def _desempatar(grupo: list[FilaTabla], partidos, reglas) -> list[FilaTabla]:
    """Minitabla con solo los partidos entre los equipos empatados; al final, orden por nombre."""
    if len(grupo) > 1:
        ids = {f.equipo_id for f in grupo}
        mini = {i: FilaTabla(i, "") for i in ids}
        for p in partidos:
            if p["local_id"] in ids and p["visitante_id"] in ids:
                _sumar(mini[p["local_id"]], p["goles_local"], p["goles_visitante"], reglas)
                _sumar(mini[p["visitante_id"]], p["goles_visitante"], p["goles_local"], reglas)
        grupo.sort(
            key=lambda f: (-mini[f.equipo_id].pts, -mini[f.equipo_id].dg, f.nombre.casefold())
        )
    return grupo


def goleadores(conn: sqlite3.Connection, torneo_id: int, categoria_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT j.nombre, e.nombre AS equipo, SUM(g.cantidad) AS goles
           FROM goles g JOIN jugadores j ON j.id = g.jugador_id
           JOIN equipos e ON e.id = j.equipo_id JOIN partidos p ON p.id = g.partido_id
           WHERE p.torneo_id = ? AND p.categoria_id = ?
           GROUP BY j.id ORDER BY goles DESC, j.nombre""",
        (torneo_id, categoria_id),
    ).fetchall()


def menos_goleados(tabla: list[FilaTabla]) -> list[FilaTabla]:
    """Portería menos goleada por equipo: menos goles en contra y, a igualdad, más partidos."""
    jugaron = [f for f in tabla if f.pj]
    return sorted(jugaron, key=lambda f: (f.gc / f.pj, -f.pj, f.nombre.casefold()))


@dataclass(frozen=True)
class Lider:
    torneo: str
    categoria: str
    equipo: str
    puntos: int
    goleador: str
    goles: int


def lideres(conn: sqlite3.Connection, liga_id: int | None = None) -> list[Lider]:
    """Líder y goleador de cada categoría que ya tiene resultados."""
    grupos = conn.execute(
        """SELECT DISTINCT p.torneo_id, p.categoria_id, t.nombre AS torneo, c.nombre AS categoria
           FROM resultados r JOIN partidos p ON p.id = r.partido_id
           JOIN torneos t ON t.id = p.torneo_id JOIN categorias c ON c.id = p.categoria_id
           WHERE ? IS NULL OR t.liga_id = ?
           ORDER BY t.nombre, c.nombre""",
        (liga_id, liga_id),
    ).fetchall()
    resultado = []
    for g in grupos:
        primero = tabla_posiciones(conn, g["torneo_id"], g["categoria_id"])[0]
        anotadores = goleadores(conn, g["torneo_id"], g["categoria_id"])
        goleador = anotadores[0] if anotadores else None
        resultado.append(
            Lider(
                g["torneo"], g["categoria"], primero.nombre, primero.pts,
                goleador["nombre"] if goleador else "", goleador["goles"] if goleador else 0,
            )
        )
    return resultado
