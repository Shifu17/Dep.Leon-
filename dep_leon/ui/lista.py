"""Pase de lista de un partido: una columna por equipo con una casilla por jugador."""

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import asistencia
from .comun import AvisoCampo, boton, botones_dialogo, error

GOLES_MAXIMOS = 99


def _nombre_con_numero(jugador) -> str:
    return f"{jugador['numero']}  {jugador['nombre']}" if jugador["numero"] is not None else jugador["nombre"]


class ColumnaEquipo(QWidget):
    """Los jugadores de un equipo con la casilla «vino» y, si se pide, sus goles."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        nombre: str,
        equipo_id: int,
        presentes: set[int],
        goles: dict[int, int] | None = None,
        marcador: QSpinBox | None = None,
    ):
        super().__init__()
        self.casillas: dict[int, QCheckBox] = {}
        self.goles: dict[int, QSpinBox] = {}
        self.contador = QLabel(objectName="ayuda")

        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.addWidget(QLabel(nombre, objectName="seccion", alignment=Qt.AlignmentFlag.AlignCenter))
        if marcador is not None:
            marcador.setObjectName("marcador")
            marcador.setAccessibleName(f"Goles de {nombre}")
            marcador.setAlignment(Qt.AlignmentFlag.AlignCenter)
            columna.addWidget(marcador)

        jugadores = conn.execute(
            "SELECT * FROM jugadores WHERE equipo_id = ? ORDER BY numero IS NULL, numero, nombre COLLATE ES",
            (equipo_id,),
        ).fetchall()
        encabezado = QHBoxLayout()
        encabezado.addWidget(QLabel("¿Quién vino?" if goles is None else "¿Quién vino? y goles"))
        encabezado.addStretch(1)
        if jugadores:
            encabezado.addWidget(boton("Todos", lambda: self._marcar_todos(True), "secundario"))
            encabezado.addWidget(boton("Nadie", lambda: self._marcar_todos(False), "secundario"))
        columna.addLayout(encabezado)

        contenido = QWidget(objectName="listaGoles")
        rejilla = QGridLayout(contenido)
        rejilla.setVerticalSpacing(2)
        for i, j in enumerate(jugadores):
            casilla = QCheckBox(_nombre_con_numero(j), checked=j["id"] in presentes)
            casilla.setToolTip(j["nombre"])
            casilla.setMinimumWidth(1)  # un nombre muy largo se recorta en lugar de esconder los goles
            casilla.setAccessibleName(f"{j['nombre']} vino al partido")
            casilla.toggled.connect(self._contar)
            self.casillas[j["id"]] = casilla
            rejilla.addWidget(casilla, i, 0)
            if goles is not None:
                control = QSpinBox(minimum=0, maximum=GOLES_MAXIMOS, value=goles.get(j["id"], 0))
                control.setFixedWidth(68)
                control.setAccessibleName(f"Goles de {j['nombre']}")
                # Quien anotó, vino: se marca solo para no tener que hacerlo dos veces.
                control.valueChanged.connect(lambda valor, c=casilla: valor and c.setChecked(True))
                self.goles[j["id"]] = control
                rejilla.addWidget(control, i, 1)
        rejilla.setRowStretch(len(jugadores), 1)
        rejilla.setColumnStretch(0, 1)
        if not jugadores:
            rejilla.addWidget(
                QLabel("Este equipo no tiene jugadores registrados.", objectName="ayuda", wordWrap=True), 0, 0
            )

        area = QScrollArea(frameShape=QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidgetResizable(True)
        area.setWidget(contenido)
        columna.addWidget(area, 1)
        columna.addWidget(self.contador)
        self._contar()

    def _marcar_todos(self, valor: bool):
        for casilla in self.casillas.values():
            casilla.setChecked(valor)

    def _contar(self):
        vinieron = len(self.presentes())
        self.contador.setText(f"Vinieron {vinieron} de {len(self.casillas)} jugadores.")

    def presentes(self) -> set[int]:
        return {j for j, c in self.casillas.items() if c.isChecked()}

    def goleadores(self) -> dict[int, int]:
        return {j: c.value() for j, c in self.goles.items() if c.value()}


class DialogoPaseLista(QDialog):
    """Asistencia de un partido, sin tocar el marcador: se puede pasar lista antes de que termine."""

    def __init__(self, padre, conn: sqlite3.Connection, partido):
        super().__init__(padre)
        self.setWindowTitle("Pase de lista")
        self.resize(720, 560)
        self.conn = conn
        self.partido = partido
        presentes = asistencia.presentes(conn, partido["id"])
        self.local = ColumnaEquipo(conn, partido["local"], partido["local_id"], presentes)
        self.visitante = ColumnaEquipo(conn, partido["visitante"], partido["visitante_id"], presentes)

        columnas = QHBoxLayout()
        columnas.addWidget(self.local, 1)
        columnas.addSpacing(16)
        columnas.addWidget(self.visitante, 1)
        raiz = QVBoxLayout(self)
        raiz.addLayout(columnas, 1)
        raiz.addWidget(
            QLabel(
                "Marca a cada jugador que se presentó. Puedes regresar y corregirlo cuando quieras.",
                objectName="ayuda", wordWrap=True,
            )
        )
        self.aviso = AvisoCampo()
        raiz.addWidget(self.aviso)
        raiz.addWidget(botones_dialogo(self, self._aceptar, "Guardar lista"))

    def _aceptar(self):
        try:
            asistencia.guardar(self.conn, self.partido["id"], self.local.presentes() | self.visitante.presentes())
        except ValueError as exc:
            self.aviso.mostrar(str(exc))
            return
        self.accept()


def pasar_lista(padre: QWidget, conn: sqlite3.Connection, partido) -> bool:
    if partido["estado"] not in asistencia.ESTADOS_CON_LISTA:
        error(padre, "Este partido está pospuesto o sin programar; todavía no se puede pasar lista.")
        return False
    return bool(DialogoPaseLista(padre, conn, partido).exec())
