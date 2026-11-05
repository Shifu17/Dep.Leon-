"""Página para capturar marcadores, goleadores y equipos que no se presentaron."""

import sqlite3
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import liguilla, resultados, rol
from .comun import boton, botones_dialogo, confirmar, error, etiqueta, id_seleccionado, llenar, tabla
from .filtros import FiltrosLiga

GOLES_MAXIMOS = 99
VER_POR_CAPTURAR = "Por capturar"
VER_CAPTURADOS = "Ya capturados"
VER_TODOS = "Todos"


class DialogoResultado(QDialog):
    def __init__(self, padre, conn: sqlite3.Connection, partido, local: str, visitante: str):
        super().__init__(padre)
        self.setWindowTitle("Capturar resultado")
        self.resize(640, 520)
        self.conn = conn
        self.partido = partido

        previo = conn.execute(
            "SELECT * FROM resultados WHERE partido_id = ?", (partido["id"],)
        ).fetchone()
        goles_previos = {
            g["jugador_id"]: g["cantidad"]
            for g in conn.execute("SELECT * FROM goles WHERE partido_id = ?", (partido["id"],))
        }
        self.marcador_local = QSpinBox(
            minimum=0, maximum=GOLES_MAXIMOS, value=previo["goles_local"] if previo else 0
        )
        self.marcador_visitante = QSpinBox(
            minimum=0, maximum=GOLES_MAXIMOS, value=previo["goles_visitante"] if previo else 0
        )
        self.goles: dict[int, QSpinBox] = {}

        columnas = QHBoxLayout()
        columnas.addLayout(
            self._columna(local, partido["local_id"], self.marcador_local, goles_previos)
        )
        columnas.addLayout(
            self._columna(visitante, partido["visitante_id"], self.marcador_visitante, goles_previos)
        )

        raiz = QVBoxLayout(self)
        raiz.addLayout(columnas, 1)

        # Solo en liguilla decidida por penales: un empate necesita saber quién avanza.
        llave = liguilla.llave_de_partido(conn, partido["id"])
        self.pide_penales = bool(llave and llave["desempate"] == liguilla.PENALES)
        self.penales_local = QSpinBox(minimum=0, maximum=GOLES_MAXIMOS)
        self.penales_visitante = QSpinBox(minimum=0, maximum=GOLES_MAXIMOS)
        if self.pide_penales:
            if llave["penales_local"] is not None:
                self.penales_local.setValue(llave["penales_local"])
                self.penales_visitante.setValue(llave["penales_visitante"])
            fila = QHBoxLayout()
            fila.addWidget(QLabel("Penales, solo si empatan:"))
            fila.addWidget(etiqueta(local, self.penales_local))
            fila.addWidget(self.penales_local)
            fila.addWidget(etiqueta(visitante, self.penales_visitante))
            fila.addWidget(self.penales_visitante)
            self.penales_local.setAccessibleName(f"Penales de {local}")
            self.penales_visitante.setAccessibleName(f"Penales de {visitante}")
            fila.addStretch(1)
            raiz.addLayout(fila)

        raiz.addWidget(
            QLabel(
                "Los goleadores son opcionales. Puedes dejar goles sin jugador (como un autogol), "
                "pero no asignar más goles que los del marcador.",
                objectName="ayuda", wordWrap=True,
            )
        )
        raiz.addWidget(botones_dialogo(self, self._aceptar))

    def _columna(self, nombre: str, equipo_id: int, marcador: QSpinBox, previos: dict[int, int]):
        columna = QVBoxLayout()
        columna.addWidget(QLabel(nombre, objectName="seccion", alignment=Qt.AlignmentFlag.AlignCenter))
        marcador.setObjectName("marcador")
        marcador.setAccessibleName(f"Goles de {nombre}")
        marcador.setAlignment(Qt.AlignmentFlag.AlignCenter)
        columna.addWidget(marcador)
        columna.addWidget(QLabel("Goleadores"))

        contenido = QWidget(objectName="listaGoles")
        rejilla = QGridLayout(contenido)
        jugadores = self.conn.execute(
            "SELECT * FROM jugadores WHERE equipo_id = ? ORDER BY numero", (equipo_id,)
        ).fetchall()
        for i, j in enumerate(jugadores):
            control = QSpinBox(minimum=0, maximum=GOLES_MAXIMOS, value=previos.get(j["id"], 0))
            self.goles[j["id"]] = control
            control.setAccessibleName(f"Goles de {j['nombre']}, número {j['numero']}")
            rejilla.addWidget(QLabel(f"{j['numero']}  {j['nombre']}"), i, 0)
            rejilla.addWidget(control, i, 1)
        rejilla.setRowStretch(len(jugadores), 1)
        rejilla.setColumnStretch(0, 1)
        if not jugadores:
            rejilla.addWidget(QLabel("Sin jugadores registrados.", objectName="ayuda"), 0, 0)

        area = QScrollArea(frameShape=QFrame.Shape.NoFrame)
        area.setWidgetResizable(True)
        area.setWidget(contenido)
        columna.addWidget(area, 1)
        return columna

    def goleadores(self) -> dict[int, int]:
        return {j: c.value() for j, c in self.goles.items() if c.value()}

    def _aceptar(self):
        try:
            resultados.guardar_resultado(
                self.conn, self.partido["id"], self.marcador_local.value(),
                self.marcador_visitante.value(), self.goleadores(),
                (self.penales_local.value(), self.penales_visitante.value())
                if self.pide_penales
                else None,
            )
        except ValueError as exc:
            error(self, str(exc))
            return
        self.accept()


class DialogoNoSePresento(QDialog):
    """Permite posponer el partido o darlo por default indicando quién paga el arbitraje."""

    def __init__(self, padre, partido, local: str, visitante: str, default_goles: int):
        super().__init__(padre)
        self.setWindowTitle("Equipo que no se presentó")
        self.ausente = QComboBox()
        self.ausente.addItem(local, partido["local_id"])
        self.ausente.addItem(visitante, partido["visitante_id"])

        self.posponer = QRadioButton("Posponer el partido (queda pendiente de nueva fecha)")
        self.default = QRadioButton(f"Dar por default: {default_goles}-0 para el equipo presente")
        self.default.setChecked(True)
        grupo = QButtonGroup(self)
        grupo.addButton(self.posponer)
        grupo.addButton(self.default)

        self.paga = QComboBox()
        self.paga.addItem("El equipo que no se presentó", resultados.PAGA_AUSENTE)
        self.paga.addItem("El equipo que sí se presentó", resultados.PAGA_PRESENTE)
        self.paga.addItem("Ambos equipos", resultados.PAGA_AMBOS)
        self.paga.addItem("Ninguno", resultados.PAGA_NINGUNO)
        self.default.toggled.connect(self.paga.setEnabled)

        forma = QFormLayout(self)
        forma.addRow("No se presentó:", self.ausente)
        forma.addRow(self.default)
        forma.addRow("Paga el arbitraje:", self.paga)
        forma.addRow(self.posponer)
        forma.addRow(botones_dialogo(self, self.accept))


def _partido_completo(conn: sqlite3.Connection, partido_id: int) -> sqlite3.Row:
    return conn.execute(
        """SELECT p.*, l.nombre AS local, v.nombre AS visitante
           FROM partidos p JOIN equipos l ON l.id = p.local_id
           JOIN equipos v ON v.id = p.visitante_id WHERE p.id = ?""",
        (partido_id,),
    ).fetchone()


def capturar_partido(padre: QWidget, conn: sqlite3.Connection, partido_id: int) -> bool:
    partido = _partido_completo(conn, partido_id)
    if partido["fecha"] is None:
        error(padre, "Este partido no tiene fecha. Primero prográmalo.")
        return False
    return bool(DialogoResultado(padre, conn, partido, partido["local"], partido["visitante"]).exec())


def marcar_no_presentado(padre: QWidget, conn: sqlite3.Connection, partido_id: int) -> bool:
    partido = _partido_completo(conn, partido_id)
    if partido["fecha"] is None:
        error(padre, "Este partido no tiene fecha. No se puede marcar todavía.")
        return False
    if partido["estado"] in (rol.JUGADO, rol.DEFAULT):
        error(padre, "Este partido ya tiene resultado. Bórralo antes de marcar que no se presentó.")
        return False
    reglas = resultados.obtener_reglas(conn, partido["torneo_id"])
    dialogo = DialogoNoSePresento(
        padre, partido, partido["local"], partido["visitante"], reglas.default_goles
    )
    if not dialogo.exec():
        return False
    try:
        if dialogo.posponer.isChecked():
            rol.posponer(conn, partido["id"])
        else:
            resultados.dar_default(
                conn, partido["id"], dialogo.ausente.currentData(), dialogo.paga.currentData()
            )
    except ValueError as exc:
        error(padre, str(exc))
        return False
    return True


def borrar_resultado(padre: QWidget, conn: sqlite3.Connection, partido_id: int) -> bool:
    partido = _partido_completo(conn, partido_id)
    if partido["estado"] not in (rol.JUGADO, rol.DEFAULT):
        error(padre, "Este partido no tiene resultado.")
        return False
    if not confirmar(padre, "¿Borrar el marcador y los goles de este partido?"):
        return False
    try:
        resultados.borrar_resultado(conn, partido["id"])
    except ValueError as exc:
        error(padre, str(exc))
        return False
    return True


class PaginaResultados(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn

        self.filtros = FiltrosLiga(conn, con_todas=True)
        self.filtros.cambiado.connect(self.refrescar_partidos)
        self.ver = QComboBox()
        self.ver.addItems([VER_POR_CAPTURAR, VER_CAPTURADOS, VER_TODOS])
        self.ver.currentIndexChanged.connect(self.refrescar_partidos)
        filtros = QHBoxLayout()
        filtros.addWidget(self.filtros, 4)
        filtros.addWidget(etiqueta("Ver:", self.ver))
        filtros.addWidget(self.ver, 1)

        acciones = QHBoxLayout()
        acciones.addWidget(boton("Capturar resultado", self.capturar))
        acciones.addWidget(boton("No se presentó", self.no_se_presento, "secundario"))
        acciones.addWidget(boton("Borrar resultado", self.borrar, "peligro"))
        acciones.addStretch(1)

        self.tabla = tabla(
            ["Fecha", "Hora", "Equipo", "Marcador", "Equipo", "Categoría", "Fase", "Estado"], estirar=2
        )
        self.tabla.horizontalHeader().setSectionResizeMode(
            4, self.tabla.horizontalHeader().ResizeMode.Stretch
        )
        self.tabla.doubleClicked.connect(self.capturar)
        self.vacio = QLabel(objectName="ayuda", wordWrap=True)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(QLabel("Resultados", objectName="titulo"))
        raiz.addLayout(filtros)
        raiz.addLayout(acciones)
        raiz.addWidget(self.vacio)
        raiz.addWidget(self.tabla, 1)
        self.refrescar_partidos()

    def showEvent(self, evento):
        super().showEvent(evento)
        self.filtros.refrescar()

    def refrescar_partidos(self):
        condicion = {
            VER_POR_CAPTURAR: f"p.estado = '{rol.PROGRAMADO}'",
            VER_CAPTURADOS: f"p.estado IN ('{rol.JUGADO}', '{rol.DEFAULT}')",
            VER_TODOS: "1 = 1",
        }[self.ver.currentText()]
        categoria = self.filtros.categoria_id
        # Lo más antiguo primero: son los primeros que deberían estar ya capturados.
        filas = self.conn.execute(
            f"""SELECT p.*, l.nombre AS local, v.nombre AS visitante, c.nombre AS categoria,
                       r.goles_local, r.goles_visitante
                FROM partidos p JOIN equipos l ON l.id = p.local_id
                JOIN equipos v ON v.id = p.visitante_id JOIN categorias c ON c.id = p.categoria_id
                LEFT JOIN resultados r ON r.partido_id = p.id
                WHERE p.torneo_id = ? AND (? IS NULL OR p.categoria_id = ?) AND {condicion}
                ORDER BY p.fecha IS NULL, p.fecha, p.hora, p.cancha""",
            (self.filtros.torneo_id, categoria, categoria),
        ).fetchall()
        llenar(
            self.tabla,
            [
                (
                    p["id"],
                    [
                        date.fromisoformat(p["fecha"]).strftime("%d/%m/%Y") if p["fecha"] else "Sin fecha",
                        p["hora"] or "-", p["local"],
                        f"{p['goles_local']} - {p['goles_visitante']}" if p["goles_local"] is not None else "-",
                        p["visitante"], p["categoria"], rol.nombre_jornada(p["jornada"]), p["estado"],
                    ],
                )
                for p in filas
            ],
        )
        self.vacio.setText(
            "" if filas else "No hay partidos en esta vista. Los partidos se crean en «Rol de juegos»."
        )
        self.vacio.setVisible(not filas)

    def _partido(self) -> int | None:
        partido_id = id_seleccionado(self.tabla)
        if partido_id is None:
            error(self, "Primero selecciona un partido.")
        return partido_id

    def capturar(self):
        partido = self._partido()
        if partido is not None and capturar_partido(self, self.conn, partido):
            self.refrescar_partidos()

    def no_se_presento(self):
        partido = self._partido()
        if partido is not None and marcar_no_presentado(self, self.conn, partido):
            self.refrescar_partidos()

    def borrar(self):
        partido = self._partido()
        if partido is not None and borrar_resultado(self, self.conn, partido):
            self.refrescar_partidos()
