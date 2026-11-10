"""Árbitros: registro con foto, el árbitro de cada partido y su calificación de 1 a 5 estrellas."""

import sqlite3

ESTRELLAS_MAX = 5
COMENTARIO_MAX = 200
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
        """SELECT a.* FROM arbitrajes x JOIN arbitros a ON a.id = x.arbitro_id WHERE x.partido_id = ?""",
        (partido_id,),
    ).fetchone()


def asignar(conn: sqlite3.Connection, partido_id: int, arbitro_id: int | None) -> None:
    """Pone (o quita, con None) el árbitro del partido.

    Si cambia de árbitro, se borran las calificaciones de los equipos: eran para otra persona.
    """
    if arbitro_id is None:
        with conn:
            conn.execute("DELETE FROM arbitrajes WHERE partido_id = ?", (partido_id,))
        return
    if conn.execute("SELECT 1 FROM partidos WHERE id = ?", (partido_id,)).fetchone() is None:
        raise ValueError("El partido ya no existe.")
    if conn.execute("SELECT 1 FROM arbitros WHERE id = ?", (arbitro_id,)).fetchone() is None:
        raise ValueError("Ese árbitro ya no está registrado.")
    previo = conn.execute("SELECT arbitro_id FROM arbitrajes WHERE partido_id = ?", (partido_id,)).fetchone()
    with conn:
        if previo is None:
            conn.execute("INSERT INTO arbitrajes (partido_id, arbitro_id) VALUES (?, ?)", (partido_id, arbitro_id))
        elif previo["arbitro_id"] != arbitro_id:
            conn.execute("DELETE FROM calificaciones_arbitro WHERE partido_id = ?", (partido_id,))
            conn.execute("UPDATE arbitrajes SET arbitro_id = ? WHERE partido_id = ?", (arbitro_id, partido_id))


def calificar(
    conn: sqlite3.Connection, partido_id: int, notas: dict[int, tuple[int | None, str]]
) -> None:
    """Guarda lo que cada equipo opina del árbitro: {equipo_id: (estrellas o None, comentario)}.

    Sin estrellas ni comentario, la opinión de ese equipo se borra.
    """
    if not notas:
        return
    partido = conn.execute("SELECT local_id, visitante_id FROM partidos WHERE id = ?", (partido_id,)).fetchone()
    if partido is None:
        raise ValueError("El partido ya no existe.")
    if de_partido(conn, partido_id) is None:
        raise ValueError("Para calificar, primero elige al árbitro del partido.")
    for equipo_id, (estrellas, comentario) in notas.items():
        if equipo_id not in (partido["local_id"], partido["visitante_id"]):
            raise ValueError("Solo califican los dos equipos del partido.")
        if estrellas is not None and not 1 <= estrellas <= ESTRELLAS_MAX:
            raise ValueError(f"La calificación va de 1 a {ESTRELLAS_MAX} estrellas.")
        if len(comentario.strip()) > COMENTARIO_MAX:
            raise ValueError(f"El comentario no puede pasar de {COMENTARIO_MAX} letras.")
    with conn:
        for equipo_id, (estrellas, comentario) in notas.items():
            comentario = " ".join(comentario.split())
            if estrellas is None and not comentario:
                conn.execute(
                    "DELETE FROM calificaciones_arbitro WHERE partido_id = ? AND equipo_id = ?",
                    (partido_id, equipo_id),
                )
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO calificaciones_arbitro (partido_id, equipo_id, estrellas, comentario) "
                    "VALUES (?, ?, ?, ?)",
                    (partido_id, equipo_id, estrellas, comentario),
                )


def notas_de_partido(conn: sqlite3.Connection, partido_id: int) -> dict[int, sqlite3.Row]:
    """La calificación y el comentario de cada equipo, por id de equipo."""
    return {
        f["equipo_id"]: f
        for f in conn.execute("SELECT * FROM calificaciones_arbitro WHERE partido_id = ?", (partido_id,))
    }


def resumen(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Cada árbitro con sus partidos, cuántas calificaciones le dieron los equipos y su promedio."""
    return conn.execute(
        """SELECT a.*,
                  (SELECT COUNT(*) FROM arbitrajes x WHERE x.arbitro_id = a.id) AS partidos,
                  COUNT(n.estrellas) AS calificados, AVG(n.estrellas) AS promedio
           FROM arbitros a
           LEFT JOIN arbitrajes x ON x.arbitro_id = a.id
           LEFT JOIN calificaciones_arbitro n ON n.partido_id = x.partido_id
           GROUP BY a.id ORDER BY a.activo DESC, a.nombre COLLATE ES"""
    ).fetchall()


def historial(conn: sqlite3.Connection, arbitro_id: int) -> list[sqlite3.Row]:
    """Lo que opinó cada equipo de cada partido del árbitro, del más reciente al más antiguo.

    Un partido sin opiniones aparece una vez, con el equipo vacío.
    """
    return conn.execute(
        """SELECT p.id AS partido_id, p.fecha, p.estado, l.nombre AS local, v.nombre AS visitante,
                  r.goles_local, r.goles_visitante, e.nombre AS equipo, n.equipo_id, n.estrellas, n.comentario
           FROM arbitrajes x JOIN partidos p ON p.id = x.partido_id
           JOIN equipos l ON l.id = p.local_id JOIN equipos v ON v.id = p.visitante_id
           LEFT JOIN resultados r ON r.partido_id = p.id
           LEFT JOIN calificaciones_arbitro n ON n.partido_id = p.id
           LEFT JOIN equipos e ON e.id = n.equipo_id
           WHERE x.arbitro_id = ?
           ORDER BY p.fecha IS NULL, p.fecha DESC, p.hora DESC, p.id, n.equipo_id = p.visitante_id""",
        (arbitro_id,),
    ).fetchall()
