"""Página de clasificación, goleadores y portería menos goleada."""

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from .. import estadisticas, resultados
from .comun import ayuda_pagina, boton, botones_dialogo, error, llenar, poner_vacio, tabla
from .filtros import FiltrosLiga


def _solo_lectura(columnas: list[str], estirar: int) -> QTableWidget:
    resultado = tabla(columnas, estirar=estirar)  # se pueden ordenar con el encabezado
    resultado.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    resultado.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # se recorre con Tab y flechas, sin robar el foco al clic
    return resultado


class DialogoReglas(QDialog):
    def __init__(self, padre, reglas: resultados.Reglas):
        super().__init__(padre)
        self.setWindowTitle("Reglas del torneo")
        self.victoria = QSpinBox(minimum=0, maximum=10, value=reglas.victoria)
        self.empate = QSpinBox(minimum=0, maximum=10, value=reglas.empate)
        self.derrota = QSpinBox(minimum=0, maximum=10, value=reglas.derrota)
        self.default_goles = QSpinBox(minimum=1, maximum=20, value=reglas.default_goles)
        forma = QFormLayout(self)
        forma.addRow("Puntos por victoria:", self.victoria)
        forma.addRow("Puntos por empate:", self.empate)
        forma.addRow("Puntos por derrota:", self.derrota)
        forma.addRow("Goles al ganar por default:", self.default_goles)
        forma.addRow(
            QLabel(
                "Los puntos se recalculan en toda la tabla. Los goles por default solo se aplican "
                "a los partidos que se marquen de ahora en adelante.",
                objectName="ayuda", wordWrap=True,
            )
        )
        forma.addRow(botones_dialogo(self, self.accept))

    def valores(self) -> resultados.Reglas:
        return resultados.Reglas(
            self.victoria.value(), self.empate.value(), self.derrota.value(), self.default_goles.value()
        )


class PaginaEstadisticas(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn

        self.filtros = FiltrosLiga(conn, con_todas=False)
        self.filtros.cambiado.connect(self.refrescar_tablas)
        fila_filtros = QHBoxLayout()
        fila_filtros.addWidget(self.filtros, 1)
        fila_filtros.addWidget(boton("Reglas de puntos", self.editar_reglas, "secundario"))

        self.clasificacion = _solo_lectura(
            ["Pos.", "Equipo", "PJ", "PG", "PE", "PP", "GF", "GC", "DG", "Pts"], estirar=1
        )
        self.goleadores = _solo_lectura(["#", "Jugador", "Equipo", "Goles"], estirar=1)
        self.porteria = _solo_lectura(["#", "Equipo", "PJ", "Recibidos", "Promedio"], estirar=1)
        poner_vacio(self.clasificacion, "No hay equipos en esta categoría.")
        poner_vacio(self.goleadores, "Todavía no hay goles registrados.")
        poner_vacio(self.porteria, "Aparecerá cuando haya partidos jugados.")
        self.leyenda = QLabel(
            "PJ jugados · PG ganados · PE empatados · PP perdidos · GF goles a favor · GC goles en contra "
            "· DG diferencia · Pts puntos",
            objectName="ayuda", wordWrap=True,
        )

        izquierda = QVBoxLayout()
        izquierda.addWidget(QLabel("Clasificación", objectName="seccion"))
        izquierda.addWidget(self.clasificacion, 1)
        derecha = QVBoxLayout()
        derecha.addWidget(QLabel("Goleadores", objectName="seccion"))
        derecha.addWidget(self.goleadores, 1)
        derecha.addWidget(QLabel("Portería menos goleada", objectName="seccion"))
        derecha.addWidget(self.porteria, 1)
        columnas = QHBoxLayout()
        columnas.addLayout(izquierda, 3)
        columnas.addLayout(derecha, 2)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(QLabel("Estadísticas", objectName="titulo"))
        raiz.addWidget(ayuda_pagina(
            "Posiciones, goleadores y portería menos goleada. Se calculan solas con los resultados que captures."
        ))
        raiz.addLayout(fila_filtros)
        raiz.addLayout(columnas, 1)
        raiz.addWidget(self.leyenda)
        self.refrescar_tablas()

    def showEvent(self, evento):
        super().showEvent(evento)
        self.filtros.refrescar()

    def refrescar_tablas(self):
        torneo, categoria = self.filtros.torneo_id, self.filtros.categoria_id
        if torneo is None or categoria is None:
            for control in (self.clasificacion, self.goleadores, self.porteria):
                llenar(control, [])
            return
        posiciones = estadisticas.tabla_posiciones(self.conn, torneo, categoria)
        llenar(
            self.clasificacion,
            [
                (f.equipo_id, [i, f.nombre, f.pj, f.pg, f.pe, f.pp, f.gf, f.gc, f"{f.dg:+d}", f.pts])
                for i, f in enumerate(posiciones, start=1)
            ],
        )
        llenar(
            self.goleadores,
            [
                (i, [i, g["nombre"], g["equipo"], g["goles"]])
                for i, g in enumerate(estadisticas.goleadores(self.conn, torneo, categoria), start=1)
            ],
        )
        llenar(
            self.porteria,
            [
                (f.equipo_id, [i, f.nombre, f.pj, f.gc, f"{f.gc / f.pj:.2f}"])
                for i, f in enumerate(estadisticas.menos_goleados(posiciones), start=1)
            ],
        )

    def editar_reglas(self):
        torneo = self.filtros.torneo_id
        if torneo is None:
            error(self, "Primero crea un torneo para esta liga en «Ligas y categorías».")
            return
        dialogo = DialogoReglas(self, resultados.obtener_reglas(self.conn, torneo))
        if dialogo.exec():
            resultados.guardar_reglas(self.conn, torneo, dialogo.valores())
            self.refrescar_tablas()
