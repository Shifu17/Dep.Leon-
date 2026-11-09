"""Pase de lista: qué jugadores se presentaron a cada partido.

Un jugador marcado como presente en un partido cuenta como asistencia. Un partido sin nadie
marcado de ese equipo se considera sin pase de lista, no como si todos hubieran faltado.
"""

import sqlite3
from dataclasses import dataclass

from . import rol

# Estados en los que el partido ya se jugó o se está jugando: tiene sentido pasar lista.
ESTADOS_CON_LISTA = (rol.PROGRAMADO, rol.JUGADO, rol.DEFAULT)


def presentes(conn: sqlite3.Connection, partido_id: int) -> set[int]:
    return {
        f["jugador_id"]
        for f in conn.execute("SELECT jugador_id FROM asistencias WHERE partido_id = ?", (partido_id,))
    }


def guardar(conn: sqlite3.Connection, partido_id: int, jugadores: set[int]) -> None:
    """Reemplaza el pase de lista del partido. Lanza ValueError si alguien no juega ese partido."""
    partido = conn.execute(
        "SELECT local_id, visitante_id FROM partidos WHERE id = ?", (partido_id,)
    ).fetchone()
    if partido is None:
        raise ValueError("El partido ya no existe.")
    if jugadores:
        marcas = ",".join("?" * len(jugadores))
        equipos = {
            f["equipo_id"]
            for f in conn.execute(f"SELECT equipo_id FROM jugadores WHERE id IN ({marcas})", tuple(jugadores))
        }
        if not equipos <= {partido["local_id"], partido["visitante_id"]}:
            raise ValueError("Un jugador marcado no pertenece a los equipos de este partido.")
    with conn:
        conn.execute("DELETE FROM asistencias WHERE partido_id = ?", (partido_id,))
        conn.executemany(
            "INSERT INTO asistencias (partido_id, jugador_id) VALUES (?, ?)",
            [(partido_id, j) for j in sorted(jugadores)],
        )


def guardar_de_equipo(conn: sqlite3.Connection, equipo_id: int, marcas: dict[int, set[int]]) -> None:
    """Guarda la cuadrícula de un equipo: para cada partido, los jugadores del equipo presentes.

    No toca lo que se marcó del equipo rival en esos partidos.
    """
    propios = {f["id"] for f in conn.execute("SELECT id FROM jugadores WHERE equipo_id = ?", (equipo_id,))}
    with conn:
        for partido_id, jugadores in marcas.items():
            if not jugadores <= propios:
                raise ValueError("Un jugador marcado no pertenece a este equipo.")
            conn.execute(
                "DELETE FROM asistencias WHERE partido_id = ? AND jugador_id IN "
                "(SELECT id FROM jugadores WHERE equipo_id = ?)",
                (partido_id, equipo_id),
            )
            conn.executemany(
                "INSERT INTO asistencias (partido_id, jugador_id) VALUES (?, ?)",
                [(partido_id, j) for j in sorted(jugadores)],
            )


@dataclass
class PartidoDeLista:
    id: int
    etiqueta: str  # J1, J2... o la ronda de liguilla
    descripcion: str  # fecha y rival, para la ayuda emergente
    estado: str


def partidos_de_equipo(conn: sqlite3.Connection, equipo_id: int) -> list[PartidoDeLista]:
    """Partidos del equipo en orden de juego, como las columnas J1, J2... de la hoja de registro."""
    filas = conn.execute(
        """SELECT p.id, p.jornada, p.fecha, p.estado,
                  CASE WHEN p.local_id = ? THEN v.nombre ELSE l.nombre END AS rival
           FROM partidos p JOIN equipos l ON l.id = p.local_id JOIN equipos v ON v.id = p.visitante_id
           WHERE (p.local_id = ? OR p.visitante_id = ?) AND p.estado IN (?, ?, ?)
           ORDER BY p.jornada, p.fecha IS NULL, p.fecha, p.hora""",
        (equipo_id, equipo_id, equipo_id, *ESTADOS_CON_LISTA),
    ).fetchall()
    partidos = []
    for f in filas:
        if f["jornada"] > rol.BASE_LIGUILLA:
            etiqueta = rol.nombre_jornada(f["jornada"])
        else:
            etiqueta = f"J{f['jornada']}"
        fecha = f["fecha"][8:10] + "/" + f["fecha"][5:7] if f["fecha"] else "sin fecha"
        partidos.append(PartidoDeLista(f["id"], etiqueta, f"{fecha} contra {f['rival']}", f["estado"]))
    return partidos


def de_equipo(conn: sqlite3.Connection, equipo_id: int) -> dict[int, set[int]]:
    """Para cada jugador del equipo, los partidos a los que asistió."""
    resultado: dict[int, set[int]] = {}
    for f in conn.execute(
        """SELECT a.jugador_id, a.partido_id FROM asistencias a
           JOIN jugadores j ON j.id = a.jugador_id WHERE j.equipo_id = ?""",
        (equipo_id,),
    ):
        resultado.setdefault(f["jugador_id"], set()).add(f["partido_id"])
    return resultado


def resumen_de_equipo(conn: sqlite3.Connection, equipo_id: int) -> tuple[dict[int, int], int]:
    """Asistencias de cada jugador y en cuántos partidos se pasó lista al equipo."""
    asistencias = de_equipo(conn, equipo_id)
    con_lista = set().union(*asistencias.values()) if asistencias else set()
    return {j: len(p) for j, p in asistencias.items()}, len(con_lista)
