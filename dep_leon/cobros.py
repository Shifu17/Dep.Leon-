"""Montos, cargos, pagos y adeudos. Todo el dinero se maneja en centavos enteros.

- La inscripción se cobra una vez por equipo y torneo.
- El arbitraje se cobra por equipo al capturar el resultado del partido, nunca antes.
- Cambiar un monto no toca los cargos ya pagados, ni siquiera en parte.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date

from . import rol

ARBITRAJE = "Arbitraje"
INSCRIPCION = "Inscripción"

# Quién paga el arbitraje cuando un equipo no se presenta.
PAGA_AUSENTE = "ausente"
PAGA_PRESENTE = "presente"
PAGA_AMBOS = "ambos"
PAGA_NINGUNO = "ninguno"


def dinero(centavos: int) -> str:
    return f"${centavos / 100:,.2f}"


def a_centavos(pesos: float) -> int:
    return round(pesos * 100)


@dataclass(frozen=True)
class Tarifa:
    categoria_id: int
    categoria: str
    arbitraje: int
    inscripcion: int


def tarifas(conn: sqlite3.Connection, torneo_id: int) -> list[Tarifa]:
    filas = conn.execute(
        """SELECT c.id, c.nombre, COALESCE(x.arbitraje, 0), COALESCE(x.inscripcion, 0)
           FROM torneos t JOIN categorias c ON c.liga_id = t.liga_id
           LEFT JOIN tarifas x ON x.torneo_id = t.id AND x.categoria_id = c.id
           WHERE t.id = ? ORDER BY c.nombre COLLATE ES""",
        (torneo_id,),
    ).fetchall()
    return [Tarifa(*f) for f in filas]


def guardar_tarifas(
    conn: sqlite3.Connection,
    torneo_id: int,
    nuevas: dict[int, tuple[int, int]],
    aplicar_a_cargos: bool = False,
) -> None:
    """Guarda {categoría: (arbitraje, inscripción)} y crea los cargos que faltaban.

    Con aplicar_a_cargos, los cargos de las categorías que cambiaron toman el monto nuevo,
    excepto los que ya tienen algún pago.
    """
    if any(a < 0 or i < 0 for a, i in nuevas.values()):
        raise ValueError("Los montos no pueden ser negativos.")
    anteriores = {t.categoria_id: t for t in tarifas(conn, torneo_id)}
    with conn:
        for categoria_id, (arbitraje, inscripcion) in nuevas.items():
            conn.execute(
                "INSERT OR REPLACE INTO tarifas (torneo_id, categoria_id, arbitraje, inscripcion) "
                "VALUES (?, ?, ?, ?)",
                (torneo_id, categoria_id, arbitraje, inscripcion),
            )
            previa = anteriores.get(categoria_id)
            if aplicar_a_cargos and previa:
                if previa.arbitraje != arbitraje:
                    _actualizar_sin_pagos(conn, torneo_id, categoria_id, ARBITRAJE, arbitraje)
                if previa.inscripcion != inscripcion:
                    _actualizar_sin_pagos(conn, torneo_id, categoria_id, INSCRIPCION, inscripcion)
        _sincronizar(conn, torneo_id)


def _actualizar_sin_pagos(conn, torneo_id, categoria_id, concepto, monto) -> None:
    conn.execute(
        """UPDATE cargos SET monto = ? WHERE torneo_id = ? AND concepto = ?
           AND equipo_id IN (SELECT id FROM equipos WHERE categoria_id = ?)
           AND id NOT IN (SELECT cargo_id FROM aplicaciones)""",
        (monto, torneo_id, concepto, categoria_id),
    )


def _tarifa(conn, torneo_id: int, categoria_id: int) -> tuple[int, int]:
    fila = conn.execute(
        "SELECT arbitraje, inscripcion FROM tarifas WHERE torneo_id = ? AND categoria_id = ?",
        (torneo_id, categoria_id),
    ).fetchone()
    return (fila["arbitraje"], fila["inscripcion"]) if fila else (0, 0)


def _equipos_que_pagan(partido, resultado) -> set[int]:
    local, visitante = partido["local_id"], partido["visitante_id"]
    ausente = resultado["ausente_id"]
    if ausente is None:
        return {local, visitante}
    presente = visitante if ausente == local else local
    return {
        PAGA_AUSENTE: {ausente},
        PAGA_PRESENTE: {presente},
        PAGA_AMBOS: {local, visitante},
        PAGA_NINGUNO: set(),
    }[resultado["paga"]]


def sincronizar_partido(conn: sqlite3.Connection, partido_id: int) -> None:
    """Deja los cargos de arbitraje de acuerdo con el resultado. No abre su propia transacción.

    Lanza ValueError si habría que quitar un cargo que ya tiene pagos.
    """
    partido = conn.execute("SELECT * FROM partidos WHERE id = ?", (partido_id,)).fetchone()
    resultado = conn.execute(
        "SELECT * FROM resultados WHERE partido_id = ?", (partido_id,)
    ).fetchone()
    deben = _equipos_que_pagan(partido, resultado) if resultado else set()
    existentes = conn.execute(
        "SELECT id, equipo_id FROM cargos WHERE partido_id = ?", (partido_id,)
    ).fetchall()
    for cargo in existentes:
        if cargo["equipo_id"] in deben:
            continue
        if conn.execute("SELECT 1 FROM aplicaciones WHERE cargo_id = ?", (cargo["id"],)).fetchone():
            raise ValueError(
                "El arbitraje de este partido ya tiene pagos. Anula esos pagos en «Cobros» antes "
                "de hacer este cambio."
            )
        conn.execute("DELETE FROM cargos WHERE id = ?", (cargo["id"],))

    monto = _tarifa(conn, partido["torneo_id"], partido["categoria_id"])[0]
    if monto > 0:
        ya_tienen = {c["equipo_id"] for c in existentes}
        for equipo_id in sorted(deben - ya_tienen):
            conn.execute(
                "INSERT INTO cargos (torneo_id, equipo_id, partido_id, concepto, monto, fecha) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (partido["torneo_id"], equipo_id, partido_id, ARBITRAJE, monto, partido["fecha"]),
            )


def _sincronizar(conn: sqlite3.Connection, torneo_id: int) -> None:
    for equipo in conn.execute(
        """SELECT e.id, e.categoria_id FROM equipos e WHERE e.torneo_id = ? AND e.id NOT IN
           (SELECT equipo_id FROM cargos WHERE partido_id IS NULL)""",
        (torneo_id,),
    ).fetchall():
        monto = _tarifa(conn, torneo_id, equipo["categoria_id"])[1]
        if monto > 0:
            conn.execute(
                "INSERT INTO cargos (torneo_id, equipo_id, partido_id, concepto, monto, fecha) "
                "VALUES (?, ?, NULL, ?, ?, ?)",
                (torneo_id, equipo["id"], INSCRIPCION, monto, rol.hoy().isoformat()),
            )
    for fila in conn.execute(
        "SELECT p.id FROM resultados r JOIN partidos p ON p.id = r.partido_id WHERE p.torneo_id = ?",
        (torneo_id,),
    ).fetchall():
        sincronizar_partido(conn, fila["id"])


def sincronizar_torneo(conn: sqlite3.Connection, torneo_id: int) -> None:
    """Crea los cargos que falten, por ejemplo de equipos o resultados capturados antes."""
    with conn:
        _sincronizar(conn, torneo_id)


def quitar_cargos_de_partido(conn: sqlite3.Connection, partido_id: int) -> None:
    """Quita los cargos de un partido que se va a eliminar. Lanza ValueError si tienen pagos."""
    if conn.execute(
        """SELECT 1 FROM aplicaciones a JOIN cargos c ON c.id = a.cargo_id
           WHERE c.partido_id = ? LIMIT 1""",
        (partido_id,),
    ).fetchone():
        raise ValueError(
            "El arbitraje de este partido ya tiene pagos. Anula esos pagos en «Cobros» primero."
        )
    conn.execute("DELETE FROM cargos WHERE partido_id = ?", (partido_id,))


def tiene_pagos(conn: sqlite3.Connection, equipo_id: int) -> bool:
    return (
        conn.execute("SELECT 1 FROM pagos WHERE equipo_id = ? LIMIT 1", (equipo_id,)).fetchone()
        is not None
    )


@dataclass(frozen=True)
class Adeudo:
    equipo_id: int
    equipo: str
    categoria: str
    cargos: int
    pagado: int

    @property
    def saldo(self) -> int:
        return self.cargos - self.pagado


def adeudos(conn: sqlite3.Connection, torneo_id: int, categoria_id: int | None = None) -> list[Adeudo]:
    filas = conn.execute(
        """SELECT e.id, e.nombre, c.nombre AS categoria,
              COALESCE((SELECT SUM(monto) FROM cargos WHERE equipo_id = e.id), 0),
              COALESCE((SELECT SUM(a.monto) FROM aplicaciones a JOIN cargos x ON x.id = a.cargo_id
                        WHERE x.equipo_id = e.id), 0)
           FROM equipos e JOIN categorias c ON c.id = e.categoria_id
           WHERE e.torneo_id = ? AND (? IS NULL OR e.categoria_id = ?)
           ORDER BY c.nombre COLLATE ES, e.nombre COLLATE ES""",
        (torneo_id, categoria_id, categoria_id),
    ).fetchall()
    return [Adeudo(*f) for f in filas]


@dataclass(frozen=True)
class Resumen:
    cargado: int
    cobrado: int

    @property
    def pendiente(self) -> int:
        return self.cargado - self.cobrado


def resumen(conn: sqlite3.Connection, torneo_id: int, categoria_id: int | None = None) -> Resumen:
    lista = adeudos(conn, torneo_id, categoria_id)
    return Resumen(sum(a.cargos for a in lista), sum(a.pagado for a in lista))


@dataclass(frozen=True)
class Cargo:
    id: int
    concepto: str
    detalle: str
    fecha: str
    monto: int
    pagado: int

    @property
    def saldo(self) -> int:
        return self.monto - self.pagado


def cargos_de_equipo(conn: sqlite3.Connection, equipo_id: int) -> list[Cargo]:
    filas = conn.execute(
        """SELECT c.id, c.concepto, c.fecha, c.monto, p.jornada,
              CASE WHEN p.local_id = c.equipo_id THEN v.nombre ELSE l.nombre END AS rival,
              COALESCE((SELECT SUM(monto) FROM aplicaciones WHERE cargo_id = c.id), 0) AS pagado
           FROM cargos c LEFT JOIN partidos p ON p.id = c.partido_id
           LEFT JOIN equipos l ON l.id = p.local_id LEFT JOIN equipos v ON v.id = p.visitante_id
           WHERE c.equipo_id = ? ORDER BY c.partido_id IS NOT NULL, c.fecha, c.id""",
        (equipo_id,),
    ).fetchall()
    return [
        Cargo(
            f["id"], f["concepto"],
            f"{rol.nombre_jornada(f['jornada'])} contra {f['rival']}" if f["rival"] else "",
            f["fecha"], f["monto"], f["pagado"],
        )
        for f in filas
    ]


def ajustar_cargo(conn: sqlite3.Connection, cargo_id: int, monto: int) -> None:
    """Cambia un cargo, incluso a cero para perdonarlo, sin bajar de lo ya pagado."""
    pagado = conn.execute(
        "SELECT COALESCE(SUM(monto), 0) FROM aplicaciones WHERE cargo_id = ?", (cargo_id,)
    ).fetchone()[0]
    if monto < pagado:
        raise ValueError(f"El monto no puede ser menor a lo ya pagado ({dinero(pagado)}).")
    with conn:
        conn.execute("UPDATE cargos SET monto = ? WHERE id = ?", (monto, cargo_id))


def registrar_pago(
    conn: sqlite3.Connection,
    equipo_id: int,
    monto: int,
    fecha: date,
    nota: str = "",
    primero: int | None = None,
) -> int:
    """Registra un abono y devuelve su folio.

    Se aplica primero al cargo indicado y después a los demás, del más antiguo al más nuevo.
    Lanza ValueError si el monto es cero o supera lo que debe el equipo.
    """
    if monto <= 0:
        raise ValueError("Escribe un monto mayor a cero.")
    pendientes = [c for c in cargos_de_equipo(conn, equipo_id) if c.saldo > 0]
    deuda = sum(c.saldo for c in pendientes)
    if monto > deuda:
        raise ValueError(f"El pago supera lo que debe el equipo ({dinero(deuda)}).")
    pendientes.sort(key=lambda c: c.id != primero)  # el orden original se conserva en los demás
    with conn:
        folio = conn.execute(
            "INSERT INTO pagos (equipo_id, fecha, monto, nota) VALUES (?, ?, ?, ?)",
            (equipo_id, fecha.isoformat(), monto, nota.strip()),
        ).lastrowid
        restante = monto
        for cargo in pendientes:
            if restante == 0:
                break
            parte = min(restante, cargo.saldo)
            conn.execute(
                "INSERT INTO aplicaciones (pago_id, cargo_id, monto) VALUES (?, ?, ?)",
                (folio, cargo.id, parte),
            )
            restante -= parte
    return folio


def pagos_de_equipo(conn: sqlite3.Connection, equipo_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM pagos WHERE equipo_id = ? ORDER BY fecha DESC, id DESC", (equipo_id,)
    ).fetchall()


def anular_pago(conn: sqlite3.Connection, folio: int) -> None:
    """El folio se conserva marcado como anulado, y lo que cubría vuelve a quedar pendiente."""
    with conn:
        conn.execute("UPDATE pagos SET anulado = 1 WHERE id = ?", (folio,))
        conn.execute("DELETE FROM aplicaciones WHERE pago_id = ?", (folio,))


def detalle_de_pago(conn: sqlite3.Connection, folio: int) -> list[tuple[str, int]]:
    """Lo que cubrió un pago: (descripción, monto)."""
    filas = conn.execute(
        """SELECT c.concepto, a.monto, p.jornada,
              CASE WHEN p.local_id = c.equipo_id THEN v.nombre ELSE l.nombre END AS rival
           FROM aplicaciones a JOIN cargos c ON c.id = a.cargo_id
           LEFT JOIN partidos p ON p.id = c.partido_id
           LEFT JOIN equipos l ON l.id = p.local_id LEFT JOIN equipos v ON v.id = p.visitante_id
           WHERE a.pago_id = ? ORDER BY c.partido_id IS NOT NULL, c.fecha, c.id""",
        (folio,),
    ).fetchall()
    return [
        (
            f"{f['concepto']}: {rol.nombre_jornada(f['jornada']).lower()} contra {f['rival']}"
            if f["rival"]
            else f["concepto"],
            f["monto"],
        )
        for f in filas
    ]
