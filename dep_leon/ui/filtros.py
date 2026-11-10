"""Tarjeta de filtros: liga, torneo, categoría y los filtros propios de cada pantalla.

Cada lista lleva su nombre arriba, en letra chica, y todas comparten el ancho; así la fila se lee como
columnas ordenadas y no como un renglón amontonado de etiquetas y listas.
"""

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import rol
from . import diseno
from .controles import ROL_DETALLE, ajustar_combo, con_detalle


class FiltrosLiga(QFrame):
    cambiado = Signal()
    elegido = Signal()  # solo cuando la persona cambia una lista, no al refrescar

    def __init__(self, conn: sqlite3.Connection, con_todas: bool):
        super().__init__(objectName="filtros")
        diseno.sombra(self)
        self.conn = conn
        self.con_todas = con_todas
        self.liga = con_detalle(QComboBox())
        self.torneo = QComboBox()
        self.categoria = QComboBox()
        self.liga.currentIndexChanged.connect(self._al_cambiar_liga)
        self.torneo.currentIndexChanged.connect(self._al_cambiar_torneo)
        self.categoria.currentIndexChanged.connect(self.cambiado)
        self._categoria_elegida = False
        self.categoria.activated.connect(self._marcar_eleccion)
        for control in (self.liga, self.torneo, self.categoria):
            control.activated.connect(self.elegido)
        self._fila = QHBoxLayout(self)
        self._fila.setContentsMargins(14, 10, 14, 12)
        self._fila.setSpacing(14)
        for texto, control in (("Liga", self.liga), ("Torneo", self.torneo), ("Categoría", self.categoria)):
            self.agregar(texto, control)
        self.refrescar()

    def agregar(self, titulo: str, control: QWidget, estirar: int = 1, primero: bool = False) -> QWidget:
        """Agrega otro filtro a la tarjeta, con su nombre arriba. Devuelve la columna para ocultarla.

        Con `primero`, va antes de la liga: para lo que más se elige en esa pantalla.
        """
        columna = QWidget(objectName="columnaFiltro")
        caja = QVBoxLayout(columna)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(4)
        nombre = QLabel(titulo, objectName="filtroTitulo")
        caja.addWidget(nombre)
        caja.addWidget(control)
        if isinstance(control, QComboBox):
            ajustar_combo(control)
            nombre.setBuddy(control)
            control.setAccessibleName(titulo)
        if primero:
            self._fila.insertWidget(0, columna, estirar)
        else:
            self._fila.addWidget(columna, estirar)
        return columna

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
        ligas = rol.ordenar_ligas(self.conn.execute("SELECT id, nombre, dias FROM ligas").fetchall())
        for l in ligas:
            self.liga.addItem(l["nombre"], l["id"])
            self.liga.setItemData(self.liga.count() - 1, rol.detalle_de_liga(l["nombre"], l["dias"]), ROL_DETALLE)
        indice = self.liga.findData(actual)
        if indice < 0:
            # Empieza en la liga que juega hoy, si ya tiene torneo; si no, en la primera que tenga
            # torneos y, si no hay, en la primera con categorías.
            con_torneo = {f[0] for f in self.conn.execute("SELECT liga_id FROM torneos")}
            hoy = rol.liga_de_hoy([l for l in ligas if l["id"] in con_torneo], rol.hoy().weekday())
            fila = self.conn.execute(
                "SELECT liga_id FROM torneos UNION ALL SELECT liga_id FROM categorias LIMIT 1"
            ).fetchone()
            elegida = hoy if hoy is not None else fila["liga_id"] if fila else None
            indice = self.liga.findData(elegida) if elegida is not None else 0
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
