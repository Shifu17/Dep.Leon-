"""Generación del rol de juegos: enfrentamientos, horarios y control de empalmes.

Todas las canchas están en el mismo terreno: Fut 7 usa la Cancha 1 y la Cancha 2, y un partido
de Fut 11 ocupa el terreno completo, por lo que se empalma con cualquier otro partido.
"""

import json
import random
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

CANCHA_FUT_11 = "11"
CANCHAS_FUT_7 = ["1", "2"]
MINUTOS_PARTIDO = 50
HORA_INICIO = 9 * 60
HORA_FIN = 14 * 60
SEMANAS_MAXIMAS = 156

PROGRAMADO = "Programado"
POSPUESTO = "Pospuesto"
JUGADO = "Jugado"
DEFAULT = "Default"

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def fecha_larga(fecha: date) -> str:
    return f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]} del {fecha.year}"


def nombre_cancha(cancha: str | None) -> str:
    if not cancha:
        return "Por definir"
    return "Fut 11" if cancha == CANCHA_FUT_11 else cancha


def canchas_de_modalidad(modalidad: str) -> list[str]:
    return [CANCHA_FUT_11] if modalidad == "Fut 11" else list(CANCHAS_FUT_7)


def a_minutos(hora: str) -> int:
    horas, minutos = hora.split(":")
    return int(horas) * 60 + int(minutos)


def a_hora(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def dias_de_texto(texto: str) -> list[int]:
    """Convierte el texto de la liga (como «Viernes y sábado») en días de la semana."""

    def limpiar(valor: str) -> str:
        sin_acentos = unicodedata.normalize("NFKD", valor)
        return "".join(c for c in sin_acentos if not unicodedata.combining(c)).casefold()

    normalizado = limpiar(texto)
    return [i for i, dia in enumerate(DIAS) if limpiar(dia) in normalizado]


def jornadas_todos_contra_todos(
    equipos: list[int], ida_y_vuelta: bool = False
) -> list[list[tuple[int, int]]]:
    """Enfrentamientos por jornada, con el método de rotación y localías equilibradas.

    Con un número impar de equipos, en cada jornada descansa uno.
    """
    lista: list[int | None] = list(equipos)
    if len(lista) < 2:
        return []
    if len(lista) % 2:
        # El descanso ocupa el lugar fijo, así todos los equipos rotan por igual.
        lista.insert(0, None)
    total = len(lista)

    jornadas = []
    for ronda in range(total - 1):
        partidos = []
        for i in range(total // 2):
            a, b = lista[i], lista[total - 1 - i]
            if a is None or b is None:
                continue
            # El equipo fijo alterna localía; los demás la alternan según su posición.
            local_primero = ronda % 2 == 0 if i == 0 else i % 2 == 1
            partidos.append((a, b) if local_primero else (b, a))
        jornadas.append(partidos)
        lista.insert(1, lista.pop())

    if ida_y_vuelta:
        jornadas += [[(b, a) for a, b in jornada] for jornada in jornadas]
    return jornadas


@dataclass(frozen=True)
class Horario:
    fecha_inicio: date
    dias: dict[int, tuple[int, int]]  # día de la semana -> (minuto de inicio, minuto de fin)
    minutos: int = MINUTOS_PARTIDO
    canchas: tuple[str, ...] = tuple(CANCHAS_FUT_7)


@dataclass(frozen=True)
class PartidoPlan:
    categoria_id: int
    jornada: int
    local_id: int
    visitante_id: int
    fecha: date
    hora: int
    minutos: int
    cancha: str


@dataclass(frozen=True)
class Ocupado:
    fecha: date
    hora: int
    minutos: int
    cancha: str


def se_empalman(a_hora_: int, a_minutos_: int, a_cancha: str, b_hora: int, b_minutos: int, b_cancha: str) -> bool:
    misma_zona = a_cancha == b_cancha or CANCHA_FUT_11 in (a_cancha, b_cancha)
    return misma_zona and a_hora_ < b_hora + b_minutos and b_hora < a_hora_ + a_minutos_


def _espacios_de_la_semana(horario: Horario, lunes: date):
    """Espacios de una semana en orden: fecha, hora y cancha."""
    for dia in sorted(horario.dias):
        fecha = lunes + timedelta(days=dia)
        if fecha < horario.fecha_inicio:
            continue
        inicio, fin = horario.dias[dia]
        hora = inicio
        while hora + horario.minutos <= fin:
            for cancha in horario.canchas:
                yield fecha, hora, cancha
            hora += horario.minutos


def _intercalar(listas: list[list]) -> list:
    """Alterna elementos de cada lista para que las categorías queden repartidas en el día."""
    resultado = []
    for i in range(max((len(l) for l in listas), default=0)):
        resultado += [l[i] for l in listas if i < len(l)]
    return resultado


def programar(
    jornadas_por_categoria: dict[int, list[list[tuple[int, int]]]],
    horario: Horario,
    ocupados: list[Ocupado],
) -> tuple[list[PartidoPlan], list[str]]:
    """Asigna fecha, hora y cancha. Cada jornada empieza en una semana nueva.

    Devuelve los partidos y los avisos. Lanza ValueError si los partidos no caben.
    """
    if not horario.dias or not horario.canchas or horario.minutos <= 0:
        raise ValueError("Elige al menos un día y una cancha.")

    por_fecha: dict[date, list[Ocupado]] = {}
    for o in ocupados:
        por_fecha.setdefault(o.fecha, []).append(o)

    total_jornadas = max((len(j) for j in jornadas_por_categoria.values()), default=0)
    plan: list[PartidoPlan] = []
    avisos: list[str] = []
    lunes = horario.fecha_inicio - timedelta(days=horario.fecha_inicio.weekday())
    semanas_usadas = 0

    for numero in range(1, total_jornadas + 1):
        pendientes = _intercalar(
            [
                [(categoria, *p) for p in jornadas[numero - 1]]
                for categoria, jornadas in jornadas_por_categoria.items()
                if numero <= len(jornadas)
            ]
        )
        semanas_de_jornada = 0
        while pendientes:
            if semanas_usadas >= SEMANAS_MAXIMAS:
                raise ValueError(
                    "Los partidos no caben en el calendario. Agrega días, canchas o más horas."
                )
            usados_en_semana = False
            for fecha, hora, cancha in _espacios_de_la_semana(horario, lunes):
                if not pendientes:
                    break
                ya_hay = por_fecha.get(fecha, [])
                if any(
                    se_empalman(hora, horario.minutos, cancha, o.hora, o.minutos, o.cancha)
                    for o in ya_hay
                ):
                    continue
                categoria, local, visitante = pendientes.pop(0)
                plan.append(
                    PartidoPlan(categoria, numero, local, visitante, fecha, hora, horario.minutos, cancha)
                )
                por_fecha.setdefault(fecha, []).append(
                    Ocupado(fecha, hora, horario.minutos, cancha)
                )
                usados_en_semana = True
            lunes += timedelta(days=7)
            semanas_usadas += 1
            if usados_en_semana:
                semanas_de_jornada += 1
        if semanas_de_jornada > 1:
            avisos.append(
                f"La jornada {numero} no cupo en una semana y ocupa {semanas_de_jornada} semanas."
            )
    return plan, avisos


def _ocupados(conn: sqlite3.Connection, excluir_torneo_categorias: tuple[int, list[int]] | None = None):
    filas = conn.execute(
        "SELECT torneo_id, categoria_id, fecha, hora, minutos, cancha FROM partidos "
        "WHERE fecha IS NOT NULL"
    ).fetchall()
    resultado = []
    for f in filas:
        if excluir_torneo_categorias:
            torneo, categorias = excluir_torneo_categorias
            if f["torneo_id"] == torneo and f["categoria_id"] in categorias:
                continue
        resultado.append(
            Ocupado(date.fromisoformat(f["fecha"]), a_minutos(f["hora"]), f["minutos"], f["cancha"])
        )
    return resultado


def generar(
    conn: sqlite3.Connection,
    torneo_id: int,
    categoria_ids: list[int],
    horario: Horario,
    ida_y_vuelta: bool = False,
    azar: random.Random | None = None,
) -> tuple[int, list[str]]:
    """Crea el rol de las categorías y reemplaza el que tuvieran.

    Devuelve (partidos creados, avisos). Lanza ValueError si no se puede generar.
    """
    azar = azar or random.Random()
    marcas = ",".join("?" * len(categoria_ids))
    con_resultados = conn.execute(
        f"""SELECT DISTINCT c.nombre FROM resultados r JOIN partidos p ON p.id = r.partido_id
            JOIN categorias c ON c.id = p.categoria_id
            WHERE p.torneo_id = ? AND p.categoria_id IN ({marcas}) ORDER BY c.nombre""",
        (torneo_id, *categoria_ids),
    ).fetchall()
    if con_resultados:
        nombres = ", ".join(f["nombre"] for f in con_resultados)
        raise ValueError(
            f"No se puede generar de nuevo el rol de {nombres}: ya tiene resultados capturados. "
            "Agrega o edita los partidos a mano."
        )
    jornadas: dict[int, list] = {}
    avisos: list[str] = []
    for categoria_id in categoria_ids:
        equipos = [
            f["id"]
            for f in conn.execute(
                "SELECT id FROM equipos WHERE torneo_id = ? AND categoria_id = ? ORDER BY id",
                (torneo_id, categoria_id),
            )
        ]
        if len(equipos) < 2:
            nombre = conn.execute(
                "SELECT nombre FROM categorias WHERE id = ?", (categoria_id,)
            ).fetchone()["nombre"]
            avisos.append(f"La categoría {nombre} se omitió porque tiene menos de 2 equipos.")
            continue
        azar.shuffle(equipos)
        jornadas[categoria_id] = jornadas_todos_contra_todos(equipos, ida_y_vuelta)
    if not jornadas:
        raise ValueError("Ninguna categoría elegida tiene al menos 2 equipos.")

    plan, avisos_plan = programar(
        jornadas, horario, _ocupados(conn, (torneo_id, list(jornadas)))
    )
    with conn:
        marcas = ",".join("?" * len(jornadas))
        conn.execute(
            f"DELETE FROM partidos WHERE torneo_id = ? AND categoria_id IN ({marcas})",
            (torneo_id, *jornadas),
        )
        conn.executemany(
            "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, fecha, "
            "hora, minutos, cancha, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    torneo_id, p.categoria_id, p.jornada, p.local_id, p.visitante_id,
                    p.fecha.isoformat(), a_hora(p.hora), p.minutos, p.cancha, PROGRAMADO,
                )
                for p in plan
            ],
        )
    return len(plan), avisos + avisos_plan


def buscar_conflicto(
    conn: sqlite3.Connection,
    fecha: date,
    hora: int,
    minutos: int,
    cancha: str,
    local_id: int,
    visitante_id: int,
    excluir_id: int | None = None,
) -> str | None:
    """Explica el empalme de cancha o de equipo que provocaría ese horario, si lo hay."""
    filas = conn.execute(
        """SELECT p.id, p.hora, p.minutos, p.cancha, p.local_id, p.visitante_id,
                  l.nombre AS local, v.nombre AS visitante, c.nombre AS categoria
           FROM partidos p JOIN equipos l ON l.id = p.local_id
           JOIN equipos v ON v.id = p.visitante_id JOIN categorias c ON c.id = p.categoria_id
           WHERE p.fecha = ?""",
        (fecha.isoformat(),),
    ).fetchall()
    for f in filas:
        if f["id"] == excluir_id:
            continue
        otro = a_minutos(f["hora"])
        descripcion = f"{f['local']} vs {f['visitante']} ({f['categoria']}) a las {f['hora']}"
        if se_empalman(hora, minutos, cancha, otro, f["minutos"], f["cancha"]):
            return f"La cancha ya está ocupada por {descripcion}."
        if (
            {local_id, visitante_id} & {f["local_id"], f["visitante_id"]}
            and hora < otro + f["minutos"]
            and otro < hora + minutos
        ):
            return f"Un equipo ya juega a esa hora: {descripcion}."
    return None


def descansos(
    conn: sqlite3.Connection, torneo_id: int, fecha: str, categoria_id: int | None = None
) -> list[tuple[str, str]]:
    """Equipos que descansan en las jornadas jugadas en esa fecha: (categoría, equipo)."""
    jornadas = conn.execute(
        "SELECT DISTINCT categoria_id, jornada FROM partidos "
        "WHERE torneo_id = ? AND fecha = ? AND (? IS NULL OR categoria_id = ?)",
        (torneo_id, fecha, categoria_id, categoria_id),
    ).fetchall()
    resultado = []
    for j in jornadas:
        resultado += [
            (f["categoria"], f["nombre"])
            for f in conn.execute(
                """SELECT e.nombre, c.nombre AS categoria FROM equipos e
                   JOIN categorias c ON c.id = e.categoria_id
                   WHERE e.torneo_id = ? AND e.categoria_id = ? AND e.id NOT IN (
                       SELECT local_id FROM partidos
                       WHERE torneo_id = ? AND categoria_id = ? AND jornada = ?
                       UNION
                       SELECT visitante_id FROM partidos
                       WHERE torneo_id = ? AND categoria_id = ? AND jornada = ?)""",
                (
                    torneo_id, j["categoria_id"],
                    torneo_id, j["categoria_id"], j["jornada"],
                    torneo_id, j["categoria_id"], j["jornada"],
                ),
            )
        ]
    return sorted(resultado)


def posponer(conn: sqlite3.Connection, partido_id: int) -> None:
    """Deja el partido pendiente de reprogramar y libera su cancha."""
    if conn.execute("SELECT 1 FROM resultados WHERE partido_id = ?", (partido_id,)).fetchone():
        raise ValueError("Este partido ya tiene resultado. Bórralo antes de posponerlo.")
    with conn:
        conn.execute(
            "UPDATE partidos SET estado = ?, fecha = NULL, hora = NULL, cancha = NULL WHERE id = ?",
            (POSPUESTO, partido_id),
        )


def horario_a_json(horario: Horario, ida_y_vuelta: bool) -> str:
    return json.dumps(
        {
            "dias": {str(d): list(r) for d, r in horario.dias.items()},
            "minutos": horario.minutos,
            "canchas": list(horario.canchas),
            "ida_y_vuelta": ida_y_vuelta,
        }
    )


def configuracion_guardada(conn: sqlite3.Connection, torneo_id: int) -> dict | None:
    fila = conn.execute(
        "SELECT datos FROM config_rol WHERE torneo_id = ?", (torneo_id,)
    ).fetchone()
    if fila is None:
        return None
    datos = json.loads(fila["datos"])
    datos["dias"] = {int(d): tuple(r) for d, r in datos["dias"].items()}
    return datos


def guardar_configuracion(
    conn: sqlite3.Connection, torneo_id: int, horario: Horario, ida_y_vuelta: bool
) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO config_rol (torneo_id, datos) VALUES (?, ?)",
            (torneo_id, horario_a_json(horario, ida_y_vuelta)),
        )


def hoy() -> date:
    return date.today()
