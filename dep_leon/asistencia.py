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


# --- Estadísticas generales -----------------------------------------------------------------------

FALTAS_ALERTA = 3  # desde cuántas faltas conviene hablar con el equipo


@dataclass
class EquipoAsistencia:
    equipo_id: int
    nombre: str
    categoria: str
    jugadores: int
    jugados: int  # partidos con resultado
    con_lista: int  # partidos en que se pasó lista al equipo
    asistencias: int

    @property
    def porcentaje(self) -> int | None:
        posibles = self.jugadores * self.con_lista
        return round(100 * self.asistencias / posibles) if posibles else None


@dataclass
class JugadorAsistencia:
    jugador_id: int
    nombre: str
    equipo: str
    asistencias: int
    con_lista: int

    @property
    def faltas(self) -> int:
        return self.con_lista - self.asistencias


@dataclass
class Estadisticas:
    equipos: list[EquipoAsistencia]
    jugadores: list[JugadorAsistencia]
    partidos_jugados: int
    partidos_con_lista: int

    @property
    def porcentaje(self) -> int | None:
        posibles = sum(e.jugadores * e.con_lista for e in self.equipos)
        return round(100 * sum(e.asistencias for e in self.equipos) / posibles) if posibles else None

    @property
    def perfectos(self) -> int:
        """Jugadores que vinieron a todos los partidos con lista de su equipo."""
        return sum(1 for j in self.jugadores if j.con_lista and not j.faltas)

    @property
    def con_muchas_faltas(self) -> list[JugadorAsistencia]:
        return sorted(
            (j for j in self.jugadores if j.faltas >= FALTAS_ALERTA), key=lambda j: (-j.faltas, j.nombre)
        )


def estadisticas(conn: sqlite3.Connection, torneo_id: int | None, categoria_id: int | None = None) -> Estadisticas:
    """Asistencia de los equipos y jugadores del torneo (o de una categoría)."""
    filtro = "e.torneo_id = ? AND (? IS NULL OR e.categoria_id = ?)"
    parametros = (torneo_id, categoria_id, categoria_id)
    con_lista = {
        f["equipo_id"]: f["partidos"]
        for f in conn.execute(
            f"""SELECT j.equipo_id, COUNT(DISTINCT a.partido_id) AS partidos FROM asistencias a
                JOIN jugadores j ON j.id = a.jugador_id JOIN equipos e ON e.id = j.equipo_id
                WHERE {filtro} GROUP BY j.equipo_id""",
            parametros,
        )
    }
    equipos = [
        EquipoAsistencia(
            f["id"], f["nombre"], f["categoria"], f["jugadores"], f["jugados"], con_lista.get(f["id"], 0),
            f["asistencias"],
        )
        for f in conn.execute(
            f"""SELECT e.id, e.nombre, c.nombre AS categoria,
                       (SELECT COUNT(*) FROM jugadores j WHERE j.equipo_id = e.id) AS jugadores,
                       (SELECT COUNT(*) FROM partidos p WHERE (p.local_id = e.id OR p.visitante_id = e.id)
                          AND p.estado IN (?, ?)) AS jugados,
                       (SELECT COUNT(*) FROM asistencias a JOIN jugadores j ON j.id = a.jugador_id
                          WHERE j.equipo_id = e.id) AS asistencias
                FROM equipos e JOIN categorias c ON c.id = e.categoria_id
                WHERE {filtro} ORDER BY c.nombre COLLATE ES, e.nombre COLLATE ES""",
            (rol.JUGADO, rol.DEFAULT, *parametros),
        )
    ]
    jugadores = [
        JugadorAsistencia(f["id"], f["nombre"], f["equipo"], f["asistencias"], con_lista.get(f["equipo_id"], 0))
        for f in conn.execute(
            f"""SELECT j.id, j.nombre, j.equipo_id, e.nombre AS equipo,
                       (SELECT COUNT(*) FROM asistencias a WHERE a.jugador_id = j.id) AS asistencias
                FROM jugadores j JOIN equipos e ON e.id = j.equipo_id WHERE {filtro}""",
            parametros,
        )
    ]
    partidos = conn.execute(
        f"""SELECT COUNT(DISTINCT CASE WHEN p.estado IN (?, ?) THEN p.id END) AS jugados,
                   COUNT(DISTINCT a.partido_id) AS con_lista
            FROM partidos p JOIN equipos e ON e.id = p.local_id
            LEFT JOIN asistencias a ON a.partido_id = p.id
            WHERE {filtro.replace('e.categoria_id', 'p.categoria_id')}""",
        (rol.JUGADO, rol.DEFAULT, *parametros),
    ).fetchone()
    return Estadisticas(equipos, jugadores, partidos["jugados"], partidos["con_lista"])


def partidos_para_lista(conn: sqlite3.Connection, torneo_id: int | None, categoria_id: int | None = None):
    """Partidos a los que se puede pasar lista, del más reciente al más antiguo, con cuántos vinieron."""
    return conn.execute(
        """SELECT p.*, l.nombre AS local, v.nombre AS visitante, c.nombre AS categoria,
                  (SELECT COUNT(*) FROM asistencias a WHERE a.partido_id = p.id) AS presentes
           FROM partidos p JOIN equipos l ON l.id = p.local_id JOIN equipos v ON v.id = p.visitante_id
           JOIN categorias c ON c.id = p.categoria_id
           WHERE p.torneo_id = ? AND (? IS NULL OR p.categoria_id = ?) AND p.estado IN (?, ?, ?)
             AND p.fecha IS NOT NULL
           ORDER BY p.fecha DESC, p.hora, p.cancha""",
        (torneo_id, categoria_id, categoria_id, *ESTADOS_CON_LISTA),
    ).fetchall()
