"""Captura de resultados, goleadores y partidos por default."""

import sqlite3

from . import cobros, liguilla, rol
from .cobros import PAGA_AMBOS, PAGA_AUSENTE, PAGA_NINGUNO, PAGA_PRESENTE
from .reglas import Reglas, guardar_reglas, obtener_reglas  # noqa: F401

OPCIONES_PAGA = (PAGA_AUSENTE, PAGA_PRESENTE, PAGA_AMBOS, PAGA_NINGUNO)


def _partido_con_fecha(conn: sqlite3.Connection, partido_id: int) -> sqlite3.Row:
    partido = conn.execute("SELECT * FROM partidos WHERE id = ?", (partido_id,)).fetchone()
    if partido is None:
        raise ValueError("El partido ya no existe.")
    if partido["estado"] == rol.POSPUESTO:
        raise ValueError("Este partido está pospuesto. Primero dale fecha en «Rol de juegos».")
    if partido["estado"] == rol.POR_PROGRAMAR:
        raise ValueError("Este partido todavía no tiene fecha. Primero prográmalo.")
    return partido


def guardar_resultado(
    conn: sqlite3.Connection,
    partido_id: int,
    goles_local: int,
    goles_visitante: int,
    goleadores: dict[int, int] | None = None,
    penales: tuple[int, int] | None = None,
) -> None:
    """Guarda o corrige el marcador y sus goleadores.

    Puede haber goles sin goleador (autogoles o sin identificar), pero no más goleadores que
    goles. Lanza ValueError si los datos no cuadran.
    """
    partido = _partido_con_fecha(conn, partido_id)
    if goles_local < 0 or goles_visitante < 0:
        raise ValueError("El marcador no puede ser negativo.")
    goleadores = {j: n for j, n in (goleadores or {}).items() if n}
    if any(n < 0 for n in goleadores.values()):
        raise ValueError("Los goles de un jugador no pueden ser negativos.")

    por_equipo = {partido["local_id"]: 0, partido["visitante_id"]: 0}
    for jugador_id, cantidad in goleadores.items():
        fila = conn.execute("SELECT equipo_id FROM jugadores WHERE id = ?", (jugador_id,)).fetchone()
        if fila is None or fila["equipo_id"] not in por_equipo:
            raise ValueError("Un goleador no pertenece a los equipos de este partido.")
        por_equipo[fila["equipo_id"]] += cantidad
    if por_equipo[partido["local_id"]] > goles_local or por_equipo[partido["visitante_id"]] > goles_visitante:
        raise ValueError("Hay más goles asignados a jugadores que goles en el marcador.")

    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO resultados (partido_id, goles_local, goles_visitante, ausente_id, paga) "
            "VALUES (?, ?, ?, NULL, NULL)",
            (partido_id, goles_local, goles_visitante),
        )
        conn.execute("DELETE FROM goles WHERE partido_id = ?", (partido_id,))
        conn.executemany(
            "INSERT INTO goles (partido_id, jugador_id, cantidad) VALUES (?, ?, ?)",
            [(partido_id, j, n) for j, n in goleadores.items()],
        )
        conn.execute("UPDATE partidos SET estado = ? WHERE id = ?", (rol.JUGADO, partido_id))
        cobros.sincronizar_partido(conn, partido_id)
        liguilla.aplicar_resultado(conn, partido_id, penales)


def dar_default(conn: sqlite3.Connection, partido_id: int, ausente_id: int, paga: str) -> None:
    """Da el partido al equipo presente con el marcador de las reglas del torneo."""
    partido = _partido_con_fecha(conn, partido_id)
    if ausente_id not in (partido["local_id"], partido["visitante_id"]):
        raise ValueError("Ese equipo no juega este partido.")
    if paga not in OPCIONES_PAGA:
        raise ValueError("Indica quién paga el arbitraje.")
    goles = obtener_reglas(conn, partido["torneo_id"]).default_goles
    local, visitante = (0, goles) if ausente_id == partido["local_id"] else (goles, 0)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO resultados (partido_id, goles_local, goles_visitante, ausente_id, paga) "
            "VALUES (?, ?, ?, ?, ?)",
            (partido_id, local, visitante, ausente_id, paga),
        )
        conn.execute("DELETE FROM goles WHERE partido_id = ?", (partido_id,))
        conn.execute("UPDATE partidos SET estado = ? WHERE id = ?", (rol.DEFAULT, partido_id))
        cobros.sincronizar_partido(conn, partido_id)
        liguilla.aplicar_resultado(conn, partido_id)


def borrar_resultado(conn: sqlite3.Connection, partido_id: int) -> None:
    """Quita el resultado, sus goles y sus cargos; el partido vuelve a estar programado.

    Lanza ValueError si el arbitraje del partido ya tiene pagos.
    """
    with conn:
        liguilla.retirar_resultado(conn, partido_id)
        conn.execute("DELETE FROM resultados WHERE partido_id = ?", (partido_id,))
        cobros.sincronizar_partido(conn, partido_id)
        conn.execute("DELETE FROM goles WHERE partido_id = ?", (partido_id,))
        conn.execute("UPDATE partidos SET estado = ? WHERE id = ?", (rol.PROGRAMADO, partido_id))
