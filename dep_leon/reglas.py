"""Reglas de cada torneo: puntos de la tabla y marcador del partido por default."""

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Reglas:
    victoria: int = 3
    empate: int = 1
    derrota: int = 0
    default_goles: int = 3


def obtener_reglas(conn: sqlite3.Connection, torneo_id: int) -> Reglas:
    fila = conn.execute(
        "SELECT victoria, empate, derrota, default_goles FROM reglas_torneo WHERE torneo_id = ?",
        (torneo_id,),
    ).fetchone()
    return Reglas(*fila) if fila else Reglas()


def guardar_reglas(conn: sqlite3.Connection, torneo_id: int, reglas: Reglas) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO reglas_torneo "
            "(torneo_id, victoria, empate, derrota, default_goles) VALUES (?, ?, ?, ?, ?)",
            (torneo_id, reglas.victoria, reglas.empate, reglas.derrota, reglas.default_goles),
        )
