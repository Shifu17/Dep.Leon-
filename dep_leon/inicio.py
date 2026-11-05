"""Datos de la pantalla de inicio: resumen de la liga y próximos juegos."""

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from . import cobros, rol
from .db import clave_orden


@dataclass(frozen=True)
class ResumenLiga:
    liga_id: int
    nombre: str
    modalidad: str
    dias: str
    categorias: int
    equipos: int
    jugadores: int
    por_jugar: int
    por_capturar: int
    jugados: int
    pospuestos: int


def resumen_por_liga(conn: sqlite3.Connection, hoy: date) -> list[ResumenLiga]:
    filas = conn.execute(
        """SELECT l.id, l.nombre, l.modalidad, l.dias,
            (SELECT COUNT(*) FROM categorias c WHERE c.liga_id = l.id) AS categorias,
            (SELECT COUNT(*) FROM equipos e JOIN torneos t ON t.id = e.torneo_id
             WHERE t.liga_id = l.id) AS equipos,
            (SELECT COUNT(*) FROM jugadores j JOIN equipos e ON e.id = j.equipo_id
             JOIN torneos t ON t.id = e.torneo_id WHERE t.liga_id = l.id) AS jugadores,
            (SELECT COUNT(*) FROM partidos p JOIN torneos t ON t.id = p.torneo_id
             WHERE t.liga_id = l.id AND p.estado = ? AND p.fecha >= ?) AS por_jugar,
            (SELECT COUNT(*) FROM partidos p JOIN torneos t ON t.id = p.torneo_id
             WHERE t.liga_id = l.id AND p.estado = ? AND p.fecha < ?) AS por_capturar,
            (SELECT COUNT(*) FROM resultados r JOIN partidos p ON p.id = r.partido_id
             JOIN torneos t ON t.id = p.torneo_id WHERE t.liga_id = l.id) AS jugados,
            (SELECT COUNT(*) FROM partidos p JOIN torneos t ON t.id = p.torneo_id
             WHERE t.liga_id = l.id AND p.estado = ?) AS pospuestos
           FROM ligas l ORDER BY l.id""",
        (rol.PROGRAMADO, hoy.isoformat(), rol.PROGRAMADO, hoy.isoformat(), rol.POSPUESTO),
    ).fetchall()
    return [ResumenLiga(*f) for f in filas]


def _partidos_futuros(conn: sqlite3.Connection, hoy: date, liga_id: int | None, extra: str = "", args=()):
    return conn.execute(
        f"""SELECT p.fecha, p.hora, p.cancha, l.nombre AS local, v.nombre AS visitante,
                   c.nombre AS categoria, g.nombre AS liga
            FROM partidos p JOIN equipos l ON l.id = p.local_id
            JOIN equipos v ON v.id = p.visitante_id JOIN categorias c ON c.id = p.categoria_id
            JOIN torneos t ON t.id = p.torneo_id JOIN ligas g ON g.id = t.liga_id
            WHERE p.estado = ? AND p.fecha >= ? AND (? IS NULL OR t.liga_id = ?) {extra}
            ORDER BY p.fecha, p.hora, p.cancha""",
        (rol.PROGRAMADO, hoy.isoformat(), liga_id, liga_id, *args),
    )


def primer_atrasado(conn: sqlite3.Connection, hoy: date, liga_id: int | None = None) -> tuple | None:
    """(liga, torneo) del partido más antiguo sin resultado, para llevar directo a capturarlo."""
    fila = conn.execute(
        """SELECT t.liga_id, p.torneo_id FROM partidos p JOIN torneos t ON t.id = p.torneo_id
           WHERE p.estado = ? AND p.fecha < ? AND (? IS NULL OR t.liga_id = ?)
           ORDER BY p.fecha, p.hora LIMIT 1""",
        (rol.PROGRAMADO, hoy.isoformat(), liga_id, liga_id),
    ).fetchone()
    return (fila["liga_id"], fila["torneo_id"]) if fila else None


def sin_fecha(conn: sqlite3.Connection, liga_id: int | None = None) -> tuple[int, tuple | None]:
    """Partidos pospuestos o sin horario en común, y (liga, torneo) del primero."""
    filas = conn.execute(
        """SELECT t.liga_id, p.torneo_id FROM partidos p JOIN torneos t ON t.id = p.torneo_id
           WHERE p.estado IN (?, ?) AND (? IS NULL OR t.liga_id = ?) ORDER BY p.id""",
        (rol.POSPUESTO, rol.POR_PROGRAMAR, liga_id, liga_id),
    ).fetchall()
    return len(filas), ((filas[0]["liga_id"], filas[0]["torneo_id"]) if filas else None)


def por_cobrar(conn: sqlite3.Connection, liga_id: int | None = None) -> tuple[int, tuple | None]:
    """Total pendiente de cobro y (liga, torneo) del torneo que más debe."""
    total, mayor, destino = 0, 0, None
    for t in conn.execute(
        "SELECT id, liga_id FROM torneos WHERE ? IS NULL OR liga_id = ? ORDER BY id", (liga_id, liga_id)
    ).fetchall():
        cobros.sincronizar_torneo(conn, t["id"])
        pendiente = cobros.resumen(conn, t["id"]).pendiente
        total += pendiente
        if pendiente > mayor:
            mayor, destino = pendiente, (t["liga_id"], t["id"])
    return total, destino


def siguiente_paso(conn: sqlite3.Connection, liga_id: int | None = None) -> tuple | None:
    """Lo que falta para empezar a usar el programa: (pantalla, explicación, texto del botón)."""
    filtro = "(? IS NULL OR t.liga_id = ?)"
    if not conn.execute(f"SELECT 1 FROM torneos t WHERE {filtro} LIMIT 1", (liga_id, liga_id)).fetchone():
        return "ligas", "Para empezar, crea un torneo en «Ligas y categorías».", "Crear torneo"
    if not conn.execute(
        f"SELECT 1 FROM equipos e JOIN torneos t ON t.id = e.torneo_id WHERE {filtro} LIMIT 1", (liga_id, liga_id)
    ).fetchone():
        return "equipos", "Siguiente paso: registra los equipos y sus jugadores.", "Registrar equipos"
    if not conn.execute(
        f"SELECT 1 FROM partidos p JOIN torneos t ON t.id = p.torneo_id WHERE {filtro} LIMIT 1", (liga_id, liga_id)
    ).fetchone():
        return "rol", "Siguiente paso: genera el rol de juegos.", "Generar rol"
    return None


def proximos_partidos(
    conn: sqlite3.Connection, hoy: date, liga_id: int | None = None, limite: int = 30
) -> list[sqlite3.Row]:
    return _partidos_futuros(conn, hoy, liga_id).fetchmany(limite)


def equipos_proxima_fecha(
    conn: sqlite3.Connection, hoy: date, liga_id: int | None = None
) -> tuple[date | None, list[dict]]:
    """Devuelve el próximo día con juegos y cada equipo que juega ese día, con su rival."""
    primero = _partidos_futuros(conn, hoy, liga_id).fetchone()
    if primero is None:
        return None, []
    filas = _partidos_futuros(conn, hoy, liga_id, "AND p.fecha = ?", (primero["fecha"],)).fetchall()
    equipos = []
    for p in filas:
        for equipo, rival in ((p["local"], p["visitante"]), (p["visitante"], p["local"])):
            equipos.append(
                {
                    "hora": p["hora"], "equipo": equipo, "rival": rival,
                    "categoria": p["categoria"], "cancha": p["cancha"],
                }
            )
    equipos.sort(key=lambda e: (e["hora"], e["categoria"], clave_orden(e["equipo"])))
    return date.fromisoformat(primero["fecha"]), equipos


def dia_corto(fecha: date, hoy: date) -> str:
    if fecha == hoy:
        return "Hoy"
    if fecha == hoy + timedelta(days=1):
        return "Mañana"
    return f"{rol.DIAS[fecha.weekday()][:3]} {fecha:%d/%m}"
