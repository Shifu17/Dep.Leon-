"""Pase de lista: por partido (una columna por equipo) o por equipo (cuadrícula J1, J2...)."""

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QAbstractItemView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import asistencia, colores
from .comun import AvisoCampo, boton, botones_dialogo, error, tabla

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


class CuadriculaLista(QWidget):
    """Pase de lista de un equipo en todos sus partidos, como las columnas J1, J2... de la hoja de registro.

    Basta un clic en la celda (o la barra espaciadora) para marcar o desmarcar: es más fácil de atinar
    que una casilla pequeña.
    """

    ANCHO_PARTIDO = 64
    MARCA = "Sí"  # texto, no un símbolo: se lee igual con cualquier fuente
    cambiada = Signal()

    def __init__(self, conn, equipo_id: int, padre=None):
        super().__init__(padre)
        self.conn = conn
        self.equipo_id = equipo_id
        self.modificada = False
        self.partidos = asistencia.partidos_de_equipo(conn, equipo_id)
        asistio = asistencia.de_equipo(conn, equipo_id)
        self.jugadores = conn.execute(
            "SELECT * FROM jugadores WHERE equipo_id = ? ORDER BY numero IS NULL, numero, nombre COLLATE ES",
            (equipo_id,),
        ).fetchall()

        self.rejilla = tabla(["Jugador", *[p.etiqueta for p in self.partidos], "Total"], estirar=0, ordenable=False)
        self.rejilla.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.rejilla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        cabecera = self.rejilla.horizontalHeader()
        for c, p in enumerate(self.partidos, start=1):
            self.rejilla.horizontalHeaderItem(c).setToolTip(p.descripcion)
            cabecera.setSectionResizeMode(c, cabecera.ResizeMode.Fixed)
            self.rejilla.setColumnWidth(c, max(self.ANCHO_PARTIDO, cabecera.sectionSizeHint(c)))
        self.rejilla.setRowCount(len(self.jugadores))
        for r, j in enumerate(self.jugadores):
            celda = QTableWidgetItem(_nombre_con_numero(j))
            celda.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.rejilla.setItem(r, 0, celda)
            for c, p in enumerate(self.partidos, start=1):
                casilla = QTableWidgetItem()
                casilla.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                casilla.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                casilla.setToolTip(f"{j['nombre']}: {p.descripcion}")
                self.rejilla.setItem(r, c, casilla)
                self._poner(r, c, p.id in asistio.get(j["id"], set()))
            total = QTableWidgetItem()
            total.setFlags(Qt.ItemFlag.ItemIsEnabled)
            total.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rejilla.setItem(r, len(self.partidos) + 1, total)
            self._contar(r)
        self.rejilla.cellClicked.connect(self.alternar)
        if self.jugadores and self.partidos:
            self.rejilla.setCurrentCell(0, 1)  # el teclado empieza en el primer partido, no en el nombre
        espacio = QShortcut(QKeySequence(Qt.Key.Key_Space), self.rejilla)
        espacio.setContext(Qt.ShortcutContext.WidgetShortcut)
        espacio.activated.connect(lambda: self.alternar(self.rejilla.currentRow(), self.rejilla.currentColumn()))
        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.addWidget(self.rejilla)

    def marcado(self, fila: int, columna: int) -> bool:
        return bool(self.rejilla.item(fila, columna).data(Qt.ItemDataRole.UserRole))

    def _poner(self, fila: int, columna: int, valor: bool):
        celda = self.rejilla.item(fila, columna)
        celda.setData(Qt.ItemDataRole.UserRole, valor)
        celda.setText(self.MARCA if valor else "")
        celda.setBackground(QColor(colores.VERDE_SUAVE) if valor else QColor(0, 0, 0, 0))
        celda.setForeground(QColor(colores.VERDE_ACTIVO))
        fuente = self.rejilla.font()
        fuente.setBold(True)
        celda.setFont(fuente)
        celda.setData(Qt.ItemDataRole.AccessibleTextRole, "vino" if valor else "no vino")

    def alternar(self, fila: int, columna: int):
        if fila < 0 or not 1 <= columna <= len(self.partidos):
            return
        self._poner(fila, columna, not self.marcado(fila, columna))
        self._contar(fila)
        self.modificada = True
        self.cambiada.emit()

    def _contar(self, fila: int):
        vino = sum(self.marcado(fila, c) for c in range(1, len(self.partidos) + 1))
        self.rejilla.item(fila, len(self.partidos) + 1).setText(str(vino))

    def guardar(self) -> None:
        """Lanza ValueError si algo no cuadra."""
        marcas = {p.id: set() for p in self.partidos}
        for r, j in enumerate(self.jugadores):
            for c, p in enumerate(self.partidos, start=1):
                if self.marcado(r, c):
                    marcas[p.id].add(j["id"])
        asistencia.guardar_de_equipo(self.conn, self.equipo_id, marcas)
        self.modificada = False


class DialogoListaEquipo(QDialog):
    """La cuadrícula del equipo en una ventana aparte."""

    def __init__(self, padre, conn, equipo_id: int, nombre: str):
        super().__init__(padre)
        self.setWindowTitle(f"Pase de lista: {nombre}")
        self.resize(980, 600)
        self.cuadricula = CuadriculaLista(conn, equipo_id)
        self.rejilla = self.cuadricula.rejilla
        self.marcado = self.cuadricula.marcado
        self.alternar = self.cuadricula.alternar
        raiz = QVBoxLayout(self)
        raiz.addWidget(QLabel(nombre, objectName="seccion"))
        raiz.addWidget(QLabel(AYUDA_CUADRICULA, objectName="ayuda", wordWrap=True))
        raiz.addWidget(self.cuadricula, 1)
        raiz.addWidget(botones_dialogo(self, self._aceptar, "Guardar lista"))

    def _aceptar(self):
        try:
            self.cuadricula.guardar()
        except ValueError as exc:
            error(self, str(exc))
            return
        self.accept()


AYUDA_CUADRICULA = (
    "Haz clic en la celda del partido al que vino cada jugador; otro clic la desmarca. "
    "Pasa el mouse por el encabezado para ver la fecha y el rival de cada partido."
)
