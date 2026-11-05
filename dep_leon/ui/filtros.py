"""Fila de filtros de liga, torneo y categoría para las páginas de resultados y estadísticas."""

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget

from .comun import etiqueta


class FiltrosLiga(QWidget):
    cambiado = Signal()
    elegido = Signal()  # solo cuando la persona cambia una lista, no al refrescar

    def __init__(self, conn: sqlite3.Connection, con_todas: bool):
        super().__init__()
        self.conn = conn
        self.con_todas = con_todas
        self.liga = QComboBox()
        self.torneo = QComboBox()
        self.categoria = QComboBox()
        self.liga.currentIndexChanged.connect(self._al_cambiar_liga)
        self.torneo.currentIndexChanged.connect(self._al_cambiar_torneo)
        self.categoria.currentIndexChanged.connect(self.cambiado)
        self._categoria_elegida = False
        self.categoria.activated.connect(self._marcar_eleccion)
        for control in (self.liga, self.torneo, self.categoria):
            control.activated.connect(self.elegido)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        for texto, control in (("Liga:", self.liga), ("Torneo:", self.torneo), ("Categoría:", self.categoria)):
            fila.addWidget(etiqueta(texto, control))
            fila.addWidget(control, 1)
        self.refrescar()

    def _marcar_eleccion(self):
        self._categoria_elegida = True

    @property
    def torneo_id(self) -> int | None:
        return self.torneo.currentData()

    @property
    def categoria_id(self) -> int | None:
        return self.categoria.currentData()

    def refrescar(self):
        actual = self.liga.currentData()
        self.liga.blockSignals(True)
        self.liga.clear()
        for l in self.conn.execute("SELECT id, nombre FROM ligas ORDER BY id"):
            self.liga.addItem(l["nombre"], l["id"])
        indice = self.liga.findData(actual)
        if indice < 0:
            # Empieza en la primera liga que ya tiene torneos; si no hay, en la primera con categorías.
            fila = self.conn.execute(
                "SELECT liga_id FROM torneos UNION ALL SELECT liga_id FROM categorias LIMIT 1"
            ).fetchone()
            indice = self.liga.findData(fila["liga_id"]) if fila else 0
        self.liga.setCurrentIndex(max(indice, 0))
        self.liga.blockSignals(False)
        self._al_cambiar_liga()

    def seleccion(self) -> tuple:
        return self.liga.currentData(), self.torneo.currentData(), self.categoria.currentData()

    def aplicar(self, liga_id, torneo_id, categoria_id) -> None:
        """Toma la selección hecha en otra pantalla, sin avisar más de una vez."""
        self.liga.blockSignals(True)
        self.liga.setCurrentIndex(max(self.liga.findData(liga_id), 0))
        self.liga.blockSignals(False)
        self._cargar_torneos(torneo_id)
        self._categoria_elegida = categoria_id is not None
        self._cargar_categorias(categoria_id)
        self.cambiado.emit()

    def _cargar_torneos(self, torneo_id) -> None:
        self.torneo.blockSignals(True)
        self.torneo.clear()
        for t in self.conn.execute(
            "SELECT id, nombre FROM torneos WHERE liga_id = ? ORDER BY nombre COLLATE ES", (self.liga.currentData(),)
        ):
            self.torneo.addItem(t["nombre"], t["id"])
        self.torneo.setCurrentIndex(max(self.torneo.findData(torneo_id), 0))
        self.torneo.blockSignals(False)

    def _al_cambiar_liga(self):
        self._cargar_torneos(self.torneo.currentData())
        self._al_cambiar_torneo()

    def _al_cambiar_torneo(self):
        self._cargar_categorias(self.categoria.currentData())
        self.cambiado.emit()

    def _cargar_categorias(self, actual) -> None:
        self.categoria.blockSignals(True)
        self.categoria.clear()
        if self.con_todas:
            self.categoria.addItem("Todas", None)
        categorias = self.conn.execute(
            """SELECT c.id, c.nombre,
                      (SELECT COUNT(*) FROM equipos e
                       WHERE e.categoria_id = c.id AND e.torneo_id = ?) AS equipos
               FROM categorias c WHERE c.liga_id = ? ORDER BY c.nombre COLLATE ES""",
            (self.torneo.currentData(), self.liga.currentData()),
        ).fetchall()
        for c in categorias:
            self.categoria.addItem(c["nombre"], c["id"])
        indice = self.categoria.findData(actual)
        if not self.con_todas and not self._categoria_elegida:
            # Sin «Todas», y hasta que se elija otra, muestra una categoría con equipos.
            con_equipos = [c["id"] for c in categorias if c["equipos"]]
            if actual not in con_equipos and con_equipos:
                indice = self.categoria.findData(con_equipos[0])
        self.categoria.setCurrentIndex(max(indice, 0))
        self.categoria.blockSignals(False)
