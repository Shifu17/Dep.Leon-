"""Liguilla de eliminación directa a partido único.

Los partidos de liguilla son partidos normales ligados a una llave: se programan, se capturan y
se cobran igual, pero no suman a la tabla regular. Si los clasificados no completan una potencia
de 2, los mejores lugares pasan directo a la segunda ronda.
"""

import sqlite3
from dataclasses import dataclass

from . import estadisticas, rol

PENALES = "penales"
TABLA = "tabla"


def posiciones_llave(tamano: int) -> list[int]:
    """Orden de lugares en la llave, de modo que el 1 y el 2 solo se crucen en la final."""
    orden = [1]
    while len(orden) < tamano:
        total = len(orden) * 2 + 1
        orden = [x for lugar in orden for x in (lugar, total - lugar)]
    return orden


def clasificados(
    conn: sqlite3.Connection, torneo_id: int, categoria_id: int, desde: int, hasta: int
) -> list[estadisticas.FilaTabla]:
    """Equipos dentro del rango de lugares. Lanza ValueError si el rango no es válido."""
    tabla = estadisticas.tabla_posiciones(conn, torneo_id, categoria_id)
    if desde < 1 or hasta > len(tabla):
        raise ValueError(f"El rango debe estar entre el lugar 1 y el {len(tabla)}.")
    if hasta - desde + 1 < 2:
        raise ValueError("Deben clasificar al menos 2 equipos.")
    return tabla[desde - 1 : hasta]


def partidos_regulares_pendientes(conn: sqlite3.Connection, torneo_id: int, categoria_id: int) -> int:
    return conn.execute(
        """SELECT COUNT(*) FROM partidos p
           WHERE p.torneo_id = ? AND p.categoria_id = ?
             AND p.id NOT IN (SELECT partido_id FROM resultados)
             AND p.id NOT IN (SELECT partido_id FROM llaves WHERE partido_id IS NOT NULL)""",
        (torneo_id, categoria_id),
    ).fetchone()[0]


def obtener(conn: sqlite3.Connection, torneo_id: int, categoria_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM liguillas WHERE torneo_id = ? AND categoria_id = ?", (torneo_id, categoria_id)
    ).fetchone()


def crear(
    conn: sqlite3.Connection, torneo_id: int, categoria_id: int, desde: int, hasta: int, desempate: str
) -> int:
    """Arma la llave con la tabla actual. Lanza ValueError si no se puede crear."""
    if desempate not in (PENALES, TABLA):
        raise ValueError("Indica cómo se define un empate.")
    if obtener(conn, torneo_id, categoria_id):
        raise ValueError("Esta categoría ya tiene liguilla en este torneo.")
    equipos = clasificados(conn, torneo_id, categoria_id, desde, hasta)

    tamano = 2
    while tamano < len(equipos):
        tamano *= 2
    orden = posiciones_llave(tamano)

    with conn:
        liguilla_id = conn.execute(
            "INSERT INTO liguillas (torneo_id, categoria_id, desde, hasta, desempate) "
            "VALUES (?, ?, ?, ?, ?)",
            (torneo_id, categoria_id, desde, hasta, desempate),
        ).lastrowid
        rondas = 0
        cantidad = tamano // 2
        while cantidad >= 1:
            rondas += 1
            for i in range(cantidad):
                conn.execute(
                    "INSERT INTO llaves (liguilla_id, ronda, orden) VALUES (?, ?, ?)",
                    (liguilla_id, rondas, i),
                )
            cantidad //= 2

        def equipo_de(semilla: int) -> int | None:
            return equipos[semilla - 1].equipo_id if semilla <= len(equipos) else None

        for i in range(tamano // 2):
            a, b = orden[2 * i], orden[2 * i + 1]
            conn.execute(
                "UPDATE llaves SET equipo_a_id = ?, semilla_a = ?, equipo_b_id = ?, semilla_b = ? "
                "WHERE liguilla_id = ? AND ronda = 1 AND orden = ?",
                (
                    equipo_de(a), a if equipo_de(a) else None,
                    equipo_de(b), b if equipo_de(b) else None, liguilla_id, i,
                ),
            )
        for llave in _llaves(conn, liguilla_id, ronda=1):
            if llave["equipo_a_id"] and llave["equipo_b_id"]:
                _crear_partido(conn, llave)
            else:
                # Un solo equipo en la llave: pasa directo a la siguiente ronda.
                _fijar_ganador(conn, llave, llave["equipo_a_id"] or llave["equipo_b_id"])
    return liguilla_id


def _llaves(conn, liguilla_id: int, ronda: int | None = None) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM llaves WHERE liguilla_id = ? AND (? IS NULL OR ronda = ?) ORDER BY ronda, orden",
        (liguilla_id, ronda, ronda),
    ).fetchall()


def _total_rondas(conn, liguilla_id: int) -> int:
    return conn.execute(
        "SELECT MAX(ronda) FROM llaves WHERE liguilla_id = ?", (liguilla_id,)
    ).fetchone()[0]


def _crear_partido(conn, llave: sqlite3.Row) -> None:
    liguilla = conn.execute("SELECT * FROM liguillas WHERE id = ?", (llave["liguilla_id"],)).fetchone()
    restantes = _total_rondas(conn, liguilla["id"]) - llave["ronda"] + 1
    local, visitante = _por_semilla(llave)
    partido = conn.execute(
        "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, "
        "minutos, estado) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            liguilla["torneo_id"], liguilla["categoria_id"], rol.BASE_LIGUILLA + restantes,
            local, visitante, rol.MINUTOS_PARTIDO, rol.POR_PROGRAMAR,
        ),
    ).lastrowid
    conn.execute("UPDATE llaves SET partido_id = ? WHERE id = ?", (partido, llave["id"]))


def _por_semilla(llave) -> tuple[int, int]:
    """El mejor lugar es local."""
    if llave["semilla_a"] < llave["semilla_b"]:
        return llave["equipo_a_id"], llave["equipo_b_id"]
    return llave["equipo_b_id"], llave["equipo_a_id"]


def _fijar_ganador(conn, llave: sqlite3.Row, ganador: int | None) -> None:
    """Registra quién avanza y actualiza la siguiente ronda. No abre transacción."""
    if llave["ganador_id"] == ganador:
        return
    siguiente = conn.execute(
        "SELECT * FROM llaves WHERE liguilla_id = ? AND ronda = ? AND orden = ?",
        (llave["liguilla_id"], llave["ronda"] + 1, llave["orden"] // 2),
    ).fetchone()
    if siguiente and siguiente["partido_id"] and conn.execute(
        "SELECT 1 FROM resultados WHERE partido_id = ?", (siguiente["partido_id"],)
    ).fetchone():
        raise ValueError(
            "La siguiente ronda ya tiene resultado. Bórralo antes de cambiar quién avanza."
        )

    semilla = None
    if ganador is not None:
        semilla = llave["semilla_a"] if ganador == llave["equipo_a_id"] else llave["semilla_b"]
    conn.execute("UPDATE llaves SET ganador_id = ? WHERE id = ?", (ganador, llave["id"]))
    if siguiente is None:
        return

    lado = "a" if llave["orden"] % 2 == 0 else "b"
    conn.execute(
        f"UPDATE llaves SET equipo_{lado}_id = ?, semilla_{lado} = ? WHERE id = ?",
        (ganador, semilla, siguiente["id"]),
    )
    actual = conn.execute("SELECT * FROM llaves WHERE id = ?", (siguiente["id"],)).fetchone()
    completa = actual["equipo_a_id"] and actual["equipo_b_id"]
    if actual["partido_id"] and completa:
        # Cambió quién avanza: se conservan la fecha, la hora y la cancha ya asignadas.
        local, visitante = _por_semilla(actual)
        conn.execute(
            "UPDATE partidos SET local_id = ?, visitante_id = ? WHERE id = ?",
            (local, visitante, actual["partido_id"]),
        )
    elif actual["partido_id"]:
        conn.execute("UPDATE llaves SET partido_id = NULL WHERE id = ?", (actual["id"],))
        conn.execute("DELETE FROM partidos WHERE id = ?", (actual["partido_id"],))
    elif completa:
        _crear_partido(conn, actual)


def llave_de_partido(conn: sqlite3.Connection, partido_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT k.*, g.desempate FROM llaves k JOIN liguillas g ON g.id = k.liguilla_id
           WHERE k.partido_id = ?""",
        (partido_id,),
    ).fetchone()


def es_de_liguilla(conn: sqlite3.Connection, partido_id: int) -> bool:
    return llave_de_partido(conn, partido_id) is not None


def aplicar_resultado(
    conn: sqlite3.Connection, partido_id: int, penales: tuple[int, int] | None = None
) -> None:
    """Define quién avanza según el resultado ya guardado. No abre transacción.

    Lanza ValueError si un empate requiere penales y faltan o también quedan empatados.
    """
    llave = llave_de_partido(conn, partido_id)
    if llave is None:
        return
    partido = conn.execute("SELECT * FROM partidos WHERE id = ?", (partido_id,)).fetchone()
    resultado = conn.execute("SELECT * FROM resultados WHERE partido_id = ?", (partido_id,)).fetchone()
    local, visitante = resultado["goles_local"], resultado["goles_visitante"]

    guardar_penales = (None, None)
    if local != visitante:
        ganador = partido["local_id"] if local > visitante else partido["visitante_id"]
    elif llave["desempate"] == PENALES:
        if penales is None or penales[0] == penales[1]:
            raise ValueError("El partido quedó empatado: captura los penales y debe haber un ganador.")
        guardar_penales = penales
        ganador = partido["local_id"] if penales[0] > penales[1] else partido["visitante_id"]
    else:
        # Avanza el mejor lugar de la tabla, que siempre juega como local.
        ganador = _por_semilla(llave)[0]

    conn.execute(
        "UPDATE llaves SET penales_local = ?, penales_visitante = ? WHERE id = ?",
        (*guardar_penales, llave["id"]),
    )
    _fijar_ganador(conn, llave, ganador)


def retirar_resultado(conn: sqlite3.Connection, partido_id: int) -> None:
    """Deshace el avance de un partido cuyo resultado se borra. No abre transacción."""
    llave = llave_de_partido(conn, partido_id)
    if llave is None:
        return
    conn.execute(
        "UPDATE llaves SET penales_local = NULL, penales_visitante = NULL WHERE id = ?", (llave["id"],)
    )
    _fijar_ganador(conn, llave, None)


def cambiar_desempate(conn: sqlite3.Connection, liguilla_id: int, desempate: str) -> None:
    """Se aplica a los partidos que se capturen de ahora en adelante."""
    if desempate not in (PENALES, TABLA):
        raise ValueError("Indica cómo se define un empate.")
    with conn:
        conn.execute("UPDATE liguillas SET desempate = ? WHERE id = ?", (desempate, liguilla_id))


def eliminar(conn: sqlite3.Connection, liguilla_id: int) -> None:
    """Borra la liguilla y sus partidos. Lanza ValueError si ya hay resultados."""
    partidos = [
        f["partido_id"]
        for f in conn.execute(
            "SELECT partido_id FROM llaves WHERE liguilla_id = ? AND partido_id IS NOT NULL",
            (liguilla_id,),
        )
    ]
    marcas = ",".join("?" * len(partidos))
    if partidos and conn.execute(
        f"SELECT 1 FROM resultados WHERE partido_id IN ({marcas}) LIMIT 1", partidos
    ).fetchone():
        raise ValueError("La liguilla ya tiene resultados. Bórralos antes de eliminarla.")
    with conn:
        conn.execute("DELETE FROM liguillas WHERE id = ?", (liguilla_id,))
        if partidos:
            conn.execute(f"DELETE FROM partidos WHERE id IN ({marcas})", partidos)


@dataclass(frozen=True)
class VistaLlave:
    id: int
    ronda: str
    numero_ronda: int
    partido_id: int | None
    equipo_a: str
    semilla_a: int | None
    equipo_b: str
    semilla_b: int | None
    goles_a: int | None
    goles_b: int | None
    penales_a: int | None
    penales_b: int | None
    ganador: str
    fecha: str | None
    hora: str | None
    cancha: str | None
    estado: str | None
    pasa_directo: bool


def vista(conn: sqlite3.Connection, liguilla_id: int) -> list[VistaLlave]:
    filas = conn.execute(
        """SELECT k.*, a.nombre AS nombre_a, b.nombre AS nombre_b, w.nombre AS ganador,
                  p.local_id, p.fecha, p.hora, p.cancha, p.estado,
                  r.goles_local, r.goles_visitante
           FROM llaves k LEFT JOIN equipos a ON a.id = k.equipo_a_id
           LEFT JOIN equipos b ON b.id = k.equipo_b_id LEFT JOIN equipos w ON w.id = k.ganador_id
           LEFT JOIN partidos p ON p.id = k.partido_id
           LEFT JOIN resultados r ON r.partido_id = k.partido_id
           WHERE k.liguilla_id = ? ORDER BY k.ronda, k.orden""",
        (liguilla_id,),
    ).fetchall()
    total = max((f["ronda"] for f in filas), default=0)
    resultado = []
    for f in filas:
        a_es_local = f["local_id"] == f["equipo_a_id"]
        goles = (f["goles_local"], f["goles_visitante"])
        penales = (f["penales_local"], f["penales_visitante"])
        if not a_es_local:
            goles, penales = goles[::-1], penales[::-1]
        resultado.append(
            VistaLlave(
                f["id"], rol.nombre_ronda(total - f["ronda"] + 1), f["ronda"], f["partido_id"],
                f["nombre_a"] or "", f["semilla_a"], f["nombre_b"] or "", f["semilla_b"],
                goles[0], goles[1], penales[0], penales[1], f["ganador"] or "",
                f["fecha"], f["hora"], f["cancha"], f["estado"],
                f["ronda"] == 1 and not (f["equipo_a_id"] and f["equipo_b_id"]),
            )
        )
    return resultado


def campeon(conn: sqlite3.Connection, liguilla_id: int) -> str:
    fila = conn.execute(
        """SELECT e.nombre FROM llaves k JOIN equipos e ON e.id = k.ganador_id
           WHERE k.liguilla_id = ? AND k.ronda = ?""",
        (liguilla_id, _total_rondas(conn, liguilla_id)),
    ).fetchone()
    return fila["nombre"] if fila else ""
