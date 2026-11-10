"""Árbitros: registro con foto, el árbitro de cada partido y su calificación de 1 a 5 estrellas."""

import sqlite3

ESTRELLAS_MAX = 5
NOMBRE_CALIFICACION = {1: "Malo", 2: "Regular", 3: "Bueno", 4: "Muy bueno", 5: "Excelente"}


def texto_calificacion(estrellas: int | None) -> str:
    if not estrellas:
        return "Sin calificar"
    return f"{estrellas} de {ESTRELLAS_MAX}: {NOMBRE_CALIFICACION[estrellas]}"


def guardar(
    conn: sqlite3.Connection,
    nombre: str,
    telefono: str = "",
    foto: str = "",
    activo: bool = True,
    arbitro_id: int | None = None,
) -> int:
    """Registra o corrige un árbitro y devuelve su id. Lanza ValueError si el nombre falta o se repite."""
    nombre = " ".join(nombre.split())
    if not nombre:
        raise ValueError("Escribe el nombre del árbitro.")
    datos = (nombre, telefono.strip(), foto, int(activo))
    try:
        with conn:
            if arbitro_id is None:
                return conn.execute(
                    "INSERT INTO arbitros (nombre, telefono, foto, activo) VALUES (?, ?, ?, ?)", datos
                ).lastrowid
            conn.execute(
                "UPDATE arbitros SET nombre = ?, telefono = ?, foto = ?, activo = ? WHERE id = ?",
                (*datos, arbitro_id),
            )
            return arbitro_id
    except sqlite3.IntegrityError as exc:
        raise ValueError("Ya hay un árbitro registrado con ese nombre.") from exc


def partidos_dirigidos(conn: sqlite3.Connection, arbitro_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM arbitrajes WHERE arbitro_id = ?", (arbitro_id,)
    ).fetchone()[0]


def borrar(conn: sqlite3.Connection, arbitro_id: int) -> str:
    """Elimina al árbitro y devuelve el nombre de su foto para borrarla.

    Lanza ValueError si ya tiene partidos: su historial y sus calificaciones deben conservarse.
    """
    if partidos_dirigidos(conn, arbitro_id):
        raise ValueError("Este árbitro ya tiene partidos asignados.")
    fila = conn.execute("SELECT foto FROM arbitros WHERE id = ?", (arbitro_id,)).fetchone()
    with conn:
        conn.execute("DELETE FROM arbitros WHERE id = ?", (arbitro_id,))
    return fila["foto"] if fila else ""


def dar_de_baja(conn: sqlite3.Connection, arbitro_id: int) -> None:
    """Deja de ofrecerlo al asignar partidos, sin perder lo que ya dirigió."""
    with conn:
        conn.execute("UPDATE arbitros SET activo = 0 WHERE id = ?", (arbitro_id,))


def para_elegir(conn: sqlite3.Connection, incluir: int | None = None) -> list[sqlite3.Row]:
    """Los árbitros activos, en orden alfabético; `incluir` agrega uno dado de baja (el ya asignado)."""
    return conn.execute(
        "SELECT * FROM arbitros WHERE activo = 1 OR id = ? ORDER BY nombre COLLATE ES", (incluir,)
    ).fetchall()


def de_partido(conn: sqlite3.Connection, partido_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT a.*, x.calificacion FROM arbitrajes x JOIN arbitros a ON a.id = x.arbitro_id
           WHERE x.partido_id = ?""",
        (partido_id,),
    ).fetchone()


def asignar(
    conn: sqlite3.Connection,
    partido_id: int,
    arbitro_id: int | None,
    calificacion: int | None = None,
    conservar_calificacion: bool = False,
) -> None:
    """Pone (o quita, con None) el árbitro del partido y su calificación de 1 a 5 estrellas.

    Con `conservar_calificacion`, si el árbitro no cambia se respeta la calificación que ya tenía;
    al cambiar de árbitro siempre se pierde, porque era de otra persona.
    """
    if calificacion is not None and not 1 <= calificacion <= ESTRELLAS_MAX:
        raise ValueError(f"La calificación va de 1 a {ESTRELLAS_MAX} estrellas.")
    if arbitro_id is None:
        if calificacion is not None:
            raise ValueError("Para calificar, primero elige al árbitro del partido.")
        with conn:
            conn.execute("DELETE FROM arbitrajes WHERE partido_id = ?", (partido_id,))
        return
    if conn.execute("SELECT 1 FROM partidos WHERE id = ?", (partido_id,)).fetchone() is None:
        raise ValueError("El partido ya no existe.")
    if conn.execute("SELECT 1 FROM arbitros WHERE id = ?", (arbitro_id,)).fetchone() is None:
        raise ValueError("Ese árbitro ya no está registrado.")
    previo = conn.execute("SELECT * FROM arbitrajes WHERE partido_id = ?", (partido_id,)).fetchone()
    if conservar_calificacion and previo and previo["arbitro_id"] == arbitro_id:
        calificacion = previo["calificacion"]
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO arbitrajes (partido_id, arbitro_id, calificacion) VALUES (?, ?, ?)",
            (partido_id, arbitro_id, calificacion),
        )


def resumen(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Cada árbitro con sus partidos, cuántos se calificaron y su promedio de estrellas."""
    return conn.execute(
        """SELECT a.*, COUNT(x.partido_id) AS partidos, COUNT(x.calificacion) AS calificados,
                  AVG(x.calificacion) AS promedio
           FROM arbitros a LEFT JOIN arbitrajes x ON x.arbitro_id = a.id
           GROUP BY a.id ORDER BY a.activo DESC, a.nombre COLLATE ES"""
    ).fetchall()


def historial(conn: sqlite3.Connection, arbitro_id: int) -> list[sqlite3.Row]:
    """Los partidos del árbitro, del más reciente al más antiguo, con marcador y calificación."""
    return conn.execute(
        """SELECT p.*, l.nombre AS local, v.nombre AS visitante, c.nombre AS categoria,
                  r.goles_local, r.goles_visitante, x.calificacion
           FROM arbitrajes x JOIN partidos p ON p.id = x.partido_id
           JOIN equipos l ON l.id = p.local_id JOIN equipos v ON v.id = p.visitante_id
           JOIN categorias c ON c.id = p.categoria_id
           LEFT JOIN resultados r ON r.partido_id = p.id
           WHERE x.arbitro_id = ?
           ORDER BY p.fecha IS NULL, p.fecha DESC, p.hora DESC""",
        (arbitro_id,),
    ).fetchall()
