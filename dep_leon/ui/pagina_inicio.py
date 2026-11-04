"""Pantalla de inicio: números de la liga, próximos juegos y equipos por jugar."""

import sqlite3
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from .. import estadisticas, inicio, rol
from .comun import llenar, tabla


def _solo_lectura(columnas: list[str], estirar: int) -> QTableWidget:
    resultado = tabla(columnas, estirar=estirar)
    resultado.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    resultado.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return resultado


class Tarjeta(QFrame):
    def __init__(self, texto: str):
        super().__init__(objectName="tarjeta")
        self.numero = QLabel("0", objectName="tarjetaNumero")
        columna = QVBoxLayout(self)
        columna.setContentsMargins(16, 10, 16, 10)
        columna.setSpacing(0)
        columna.addWidget(self.numero)
        columna.addWidget(QLabel(texto, objectName="tarjetaTexto"))

    def poner(self, valor: int):
        self.numero.setText(f"{valor:,}")


class PaginaInicio(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn

        self.liga = QComboBox()
        self.liga.setMinimumWidth(220)
        self.liga.currentIndexChanged.connect(self.refrescar_datos)
        encabezado = QHBoxLayout()
        titulo = QLabel("Inicio", objectName="titulo")
        titulo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        encabezado.addWidget(titulo, 1)
        encabezado.addWidget(QLabel("Ver:"))
        encabezado.addWidget(self.liga)

        self.equipos = Tarjeta("Equipos")
        self.jugadores = Tarjeta("Jugadores")
        self.por_jugar = Tarjeta("Partidos por jugar")
        self.jugados = Tarjeta("Partidos jugados")
        self.pospuestos = Tarjeta("Partidos pospuestos")
        tarjetas = QHBoxLayout()
        for tarjeta in (self.equipos, self.jugadores, self.por_jugar, self.jugados, self.pospuestos):
            tarjetas.addWidget(tarjeta)

        self.proximos = _solo_lectura(
            ["Día", "Hora", "Equipo", "Equipo", "Categoría", "Cancha"], estirar=2
        )
        self.proximos.horizontalHeader().setSectionResizeMode(
            3, self.proximos.horizontalHeader().ResizeMode.Stretch
        )
        self.sin_proximos = QLabel(
            "No hay juegos programados. Créalos en «Rol de juegos».", objectName="ayuda", wordWrap=True
        )
        izquierda = QVBoxLayout()
        izquierda.addWidget(QLabel("Próximos juegos", objectName="seccion"))
        izquierda.addWidget(self.sin_proximos)
        izquierda.addWidget(self.proximos, 1)

        self.titulo_equipos = QLabel("Equipos por jugar", objectName="seccion")
        self.equipos_jugar = _solo_lectura(["Hora", "Equipo", "Contra", "Categoría"], estirar=1)
        self.sin_equipos = QLabel(
            "Aquí verás los equipos del próximo día de juego.", objectName="ayuda", wordWrap=True
        )
        derecha = QVBoxLayout()
        derecha.addWidget(self.titulo_equipos)
        derecha.addWidget(self.sin_equipos)
        derecha.addWidget(self.equipos_jugar, 1)

        columnas = QHBoxLayout()
        columnas.addLayout(izquierda, 3)
        columnas.addLayout(derecha, 2)

        self.ligas = _solo_lectura(
            ["Liga", "Categorías", "Equipos", "Jugadores", "Por jugar", "Jugados", "Pospuestos"],
            estirar=0,
        )
        self.ligas.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        abajo_izquierda = QVBoxLayout()
        abajo_izquierda.addWidget(QLabel("Resumen por liga", objectName="seccion"))
        abajo_izquierda.addWidget(self.ligas)
        abajo_izquierda.addStretch(1)

        self.lideres = _solo_lectura(["Categoría", "Líder", "Pts", "Goleador", "Goles"], estirar=3)
        self.sin_lideres = QLabel(
            "Aquí verás al líder y al goleador de cada categoría cuando captures resultados.",
            objectName="ayuda", wordWrap=True,
        )
        abajo_derecha = QVBoxLayout()
        abajo_derecha.addWidget(QLabel("Líderes por categoría", objectName="seccion"))
        abajo_derecha.addWidget(self.sin_lideres)
        abajo_derecha.addWidget(self.lideres)
        abajo_derecha.addStretch(1)

        abajo = QHBoxLayout()
        abajo.addLayout(abajo_izquierda, 3)
        abajo.addLayout(abajo_derecha, 2)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addLayout(encabezado)
        raiz.addLayout(tarjetas)
        raiz.addLayout(columnas, 1)
        raiz.addLayout(abajo)
        self.refrescar()

    def showEvent(self, evento):
        # Los datos pueden cambiar en cualquier página, así que se leen al volver aquí.
        super().showEvent(evento)
        self.refrescar()

    def refrescar(self):
        actual = self.liga.currentData()
        self.liga.blockSignals(True)
        self.liga.clear()
        self.liga.addItem("Todas las ligas", None)
        for l in self.conn.execute("SELECT id, nombre FROM ligas ORDER BY id"):
            self.liga.addItem(l["nombre"], l["id"])
        self.liga.setCurrentIndex(max(self.liga.findData(actual), 0))
        self.liga.blockSignals(False)
        self.refrescar_datos()

    def refrescar_datos(self):
        hoy = rol.hoy()
        liga_id = self.liga.currentData()
        resumen = inicio.resumen_por_liga(self.conn, hoy)
        elegidas = [r for r in resumen if liga_id is None or r.liga_id == liga_id]
        self.equipos.poner(sum(r.equipos for r in elegidas))
        self.jugadores.poner(sum(r.jugadores for r in elegidas))
        self.por_jugar.poner(sum(r.por_jugar for r in elegidas))
        self.jugados.poner(sum(r.jugados for r in elegidas))
        self.pospuestos.poner(sum(r.pospuestos for r in elegidas))

        partidos = inicio.proximos_partidos(self.conn, hoy, liga_id)
        llenar(
            self.proximos,
            [
                (
                    i,
                    [
                        inicio.dia_corto(date.fromisoformat(p["fecha"]), hoy), p["hora"],
                        p["local"], p["visitante"], p["categoria"], rol.nombre_cancha(p["cancha"]),
                    ],
                )
                for i, p in enumerate(partidos)
            ],
        )
        self.proximos.setVisible(bool(partidos))
        self.sin_proximos.setVisible(not partidos)

        fecha, equipos = inicio.equipos_proxima_fecha(self.conn, hoy, liga_id)
        self.titulo_equipos.setText(
            f"Equipos por jugar: {rol.fecha_larga(fecha)}" if fecha else "Equipos por jugar"
        )
        llenar(
            self.equipos_jugar,
            [
                (i, [e["hora"], e["equipo"], e["rival"], e["categoria"]])
                for i, e in enumerate(equipos)
            ],
        )
        self.equipos_jugar.setVisible(bool(equipos))
        self.sin_equipos.setVisible(not equipos)

        llenar(
            self.ligas,
            [
                (
                    r.liga_id,
                    [
                        r.nombre, r.categorias, r.equipos, r.jugadores,
                        r.por_jugar, r.jugados, r.pospuestos,
                    ],
                )
                for r in resumen
            ],
        )
        self._ajustar_alto(self.ligas)

        lideres = estadisticas.lideres(self.conn, liga_id)
        llenar(
            self.lideres,
            [
                (i, [l.categoria, l.equipo, l.puntos, l.goleador or "-", l.goles or "-"])
                for i, l in enumerate(lideres)
            ],
        )
        self.lideres.setVisible(bool(lideres))
        self.sin_lideres.setVisible(not lideres)
        self.lideres.setFixedHeight(self.ligas.height())

    @staticmethod
    def _ajustar_alto(tabla_: QTableWidget):
        tabla_.resizeRowsToContents()
        alto = tabla_.horizontalHeader().height() + 2
        alto += sum(tabla_.rowHeight(f) for f in range(tabla_.rowCount()))
        tabla_.setFixedHeight(alto)
