"""Inicio: qué requiere atención hoy, el próximo día de juego y cómo va cada categoría.

El orden responde a lo que se hace al abrir el programa: primero lo pendiente, con un botón que
lleva a resolverlo; luego lo que viene; al final, el panorama de la liga.
"""

import sqlite3
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import cobros, estadisticas, inicio, rol
from . import diseno
from .controles import ROL_DETALLE, con_detalle
from .comun import boton, etiqueta, llenar, tabla


def _solo_lectura(columnas: list[str], estirar: int) -> QTableWidget:
    resultado = tabla(columnas, estirar=estirar, ordenable=False)
    resultado.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    resultado.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # se recorre con Tab y flechas, sin robar el foco al clic
    return resultado


class Dato(QWidget):
    """Una cifra con su nombre, para la franja de resumen."""

    def __init__(self, texto: str):
        super().__init__()
        self.numero = QLabel("0", objectName="datoNumero")
        columna = QVBoxLayout(self)
        columna.setContentsMargins(14, 8, 14, 8)
        columna.setSpacing(0)
        columna.addWidget(self.numero)
        columna.addWidget(QLabel(texto, objectName="datoTexto"))

    def poner(self, valor: int, alerta: bool = False):
        self.numero.setText(f"{valor:,}")
        nombre = "datoAlerta" if alerta else "datoNumero"
        if self.numero.objectName() != nombre:
            self.numero.setObjectName(nombre)
            self.numero.style().unpolish(self.numero)
            self.numero.style().polish(self.numero)


class Pendiente(QFrame):
    """Un renglón de la lista de pendientes: qué pasa y el botón para resolverlo."""

    def __init__(self, texto_boton: str, accion, alerta: bool = False):
        super().__init__(objectName="pendienteAlerta" if alerta else "pendiente")
        diseno.sombra(self)
        self.texto = QLabel(wordWrap=True)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(12, 6, 8, 6)
        fila.addWidget(self.texto, 1)
        fila.addWidget(boton(texto_boton, accion, None if alerta else "secundario"))
        self.setVisible(False)

    def mostrar(self, texto: str | None):
        self.texto.setText(texto or "")
        self.setVisible(bool(texto))


class PaginaInicio(QWidget):
    ir_a = Signal(str, object, object)  # pantalla, liga y torneo a los que conviene ir

    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn
        self._destinos: dict[str, tuple] = {}

        self.titulo = QLabel(objectName="titulo")
        self.titulo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.liga = con_detalle(QComboBox())
        self.liga.setMinimumWidth(200)
        self.liga.currentIndexChanged.connect(self.refrescar_datos)
        encabezado = QHBoxLayout()
        encabezado.addWidget(self.titulo, 1)
        encabezado.addWidget(etiqueta("Ver:", self.liga))
        encabezado.addWidget(self.liga)

        self.equipos = Dato("Equipos")
        self.jugadores = Dato("Jugadores")
        self.por_jugar = Dato("Por jugar")
        self.por_capturar = Dato("Por capturar")
        self.jugados = Dato("Jugados")
        self.pospuestos = Dato("Pospuestos")
        franja = QFrame(objectName="franja")
        diseno.sombra(franja)
        fila_franja = QHBoxLayout(franja)
        fila_franja.setContentsMargins(4, 0, 4, 0)
        fila_franja.setSpacing(0)
        datos = (self.equipos, self.jugadores, self.por_jugar, self.por_capturar, self.jugados, self.pospuestos)
        for i, dato in enumerate(datos):
            if i:
                separador = QFrame(objectName="separador")
                separador.setFixedWidth(1)
                fila_franja.addWidget(separador)
            fila_franja.addWidget(dato, 1)

        self.aviso = Pendiente("Capturar resultados", lambda: self._ir("resultados"), alerta=True)
        self.aviso_texto = self.aviso.texto
        self.pendiente_fecha = Pendiente("Ver en el rol", lambda: self._ir("rol"))
        self.pendiente_cobro = Pendiente("Ir a cobros", lambda: self._ir("cobros"))
        self.pendiente_paso = Pendiente("Empezar", lambda: self._ir("paso"))
        self.al_dia = QLabel("Todo al día: no hay partidos por capturar ni sin fecha.", objectName="ayuda")
        pendientes = QVBoxLayout()
        pendientes.setSpacing(4)
        for renglon in (self.pendiente_paso, self.aviso, self.pendiente_fecha, self.pendiente_cobro):
            pendientes.addWidget(renglon)
        pendientes.addWidget(self.al_dia)

        self.proximos = _solo_lectura(["Día", "Hora", "Equipo", "Equipo", "Categoría", "Cancha"], estirar=2)
        self.proximos.horizontalHeader().setSectionResizeMode(
            3, self.proximos.horizontalHeader().ResizeMode.Stretch
        )
        self.sin_proximos = QLabel(
            "No hay juegos programados. Créalos en «Rol de juegos».", objectName="ayuda", wordWrap=True
        )
        pestana_proximos = QWidget()
        columna = QVBoxLayout(pestana_proximos)
        columna.setContentsMargins(0, 6, 0, 0)
        columna.addWidget(self.sin_proximos)
        columna.addWidget(self.proximos, 1)

        self.titulo_equipos = QLabel("Equipos por jugar", objectName="ayuda", wordWrap=True)
        self.equipos_jugar = _solo_lectura(["Hora", "Equipo", "Contra", "Categoría"], estirar=1)
        self.sin_equipos = QLabel(
            "Aquí verás los equipos del próximo día de juego.", objectName="ayuda", wordWrap=True
        )
        pestana_equipos = QWidget()
        columna = QVBoxLayout(pestana_equipos)
        columna.setContentsMargins(0, 6, 0, 0)
        columna.addWidget(self.titulo_equipos)
        columna.addWidget(self.sin_equipos)
        columna.addWidget(self.equipos_jugar, 1)

        self.pestanas = QTabWidget()
        self.pestanas.addTab(pestana_proximos, "Próximos juegos")
        self.pestanas.addTab(pestana_equipos, "Equipos por jugar")

        self.lideres = _solo_lectura(["Categoría", "Líder", "Pts", "Goleador", "Goles"], estirar=3)
        self.sin_lideres = QLabel(
            "Aquí verás al líder y al goleador de cada categoría cuando captures resultados.",
            objectName="ayuda", wordWrap=True,
        )
        self.ligas = _solo_lectura(["Liga", "Equipos", "Por jugar", "Por capturar"], estirar=0)
        self.titulo_resumen = QLabel("Resumen por liga", objectName="seccion")

        derecha = QVBoxLayout()
        derecha.addWidget(QLabel("Líderes por categoría", objectName="seccion"))
        derecha.addWidget(self.sin_lideres)
        derecha.addWidget(self.lideres, 1)
        derecha.addWidget(self.titulo_resumen)
        derecha.addWidget(self.ligas, 1)
        derecha.addStretch(0)
        for aviso in (self.sin_proximos, self.sin_equipos, self.sin_lideres):
            aviso.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        cuerpo = QHBoxLayout()
        cuerpo.addWidget(self.pestanas, 3)
        cuerpo.addLayout(derecha, 2)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addLayout(encabezado)
        raiz.addWidget(franja)
        raiz.addLayout(pendientes)
        raiz.addLayout(cuerpo, 1)
        self.refrescar()

    def _ir(self, clave: str):
        destino = self._destinos.get(clave)
        if destino:
            self.ir_a.emit(*destino)

    def _capturar(self):
        self._ir("resultados")

    def showEvent(self, evento):
        # Los datos pueden cambiar en cualquier página, así que se leen al volver aquí.
        super().showEvent(evento)
        self.refrescar()

    def refrescar(self):
        actual = self.liga.currentData()
        self.liga.blockSignals(True)
        self.liga.clear()
        self.liga.addItem("Todas las ligas", None)
        for l in rol.ordenar_ligas(self.conn.execute("SELECT id, nombre, dias FROM ligas").fetchall()):
            self.liga.addItem(l["nombre"], l["id"])
            self.liga.setItemData(self.liga.count() - 1, rol.detalle_de_liga(l["nombre"], l["dias"]), ROL_DETALLE)
        self.liga.setCurrentIndex(max(self.liga.findData(actual), 0))
        self.liga.blockSignals(False)
        self.refrescar_datos()

    def refrescar_datos(self):
        hoy = rol.hoy()
        liga_id = self.liga.currentData()
        self.titulo.setText(rol.fecha_larga(hoy))
        resumen = inicio.resumen_por_liga(self.conn, hoy)
        elegidas = [r for r in resumen if liga_id is None or r.liga_id == liga_id]
        atrasados = sum(r.por_capturar for r in elegidas)
        self.equipos.poner(sum(r.equipos for r in elegidas))
        self.jugadores.poner(sum(r.jugadores for r in elegidas))
        self.por_jugar.poner(sum(r.por_jugar for r in elegidas))
        self.por_capturar.poner(atrasados, alerta=atrasados > 0)
        self.jugados.poner(sum(r.jugados for r in elegidas))
        self.pospuestos.poner(sum(r.pospuestos for r in elegidas))
        self._refrescar_pendientes(hoy, liga_id, atrasados)

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
            [(i, [e["hora"], e["equipo"], e["rival"], e["categoria"]]) for i, e in enumerate(equipos)],
        )
        self.equipos_jugar.setVisible(bool(equipos))
        self.sin_equipos.setVisible(not equipos)

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

        # Las ligas sin equipos no aportan nada, y con una sola liga el resumen repite la franja de arriba.
        con_equipos = [r for r in resumen if r.equipos]
        llenar(
            self.ligas,
            [(r.liga_id, [r.nombre, r.equipos, r.por_jugar, r.por_capturar]) for r in con_equipos],
        )
        comparar = liga_id is None and len(con_equipos) >= 2
        self.ligas.setVisible(comparar)
        self.titulo_resumen.setVisible(comparar)

    def _refrescar_pendientes(self, hoy: date, liga_id, atrasados: int):
        self._destinos.clear()
        paso = inicio.siguiente_paso(self.conn, liga_id)
        if paso:
            pantalla, texto, etiqueta_boton = paso
            self._destinos["paso"] = (pantalla, liga_id, None)
            self.pendiente_paso.findChild(type(boton("", lambda: None))).setText(etiqueta_boton)
        self.pendiente_paso.mostrar(paso[1] if paso else None)

        destino = inicio.primer_atrasado(self.conn, hoy, liga_id)
        if destino:
            self._destinos["resultados"] = ("resultados", *destino)
        self.aviso.mostrar(
            None
            if not atrasados
            else "1 partido ya pasó y no tiene resultado."
            if atrasados == 1
            else f"{atrasados} partidos ya pasaron y no tienen resultado."
        )

        sin_fecha, destino = inicio.sin_fecha(self.conn, liga_id)
        if destino:
            self._destinos["rol"] = ("rol", *destino)
        self.pendiente_fecha.mostrar(
            None
            if not sin_fecha
            else "1 partido no tiene fecha (pospuesto o sin horario en común)."
            if sin_fecha == 1
            else f"{sin_fecha} partidos no tienen fecha (pospuestos o sin horario en común)."
        )

        pendiente, destino = inicio.por_cobrar(self.conn, liga_id)
        if destino:
            self._destinos["cobros"] = ("cobros", *destino)
        self.pendiente_cobro.mostrar(
            f"Hay {cobros.dinero(pendiente)} por cobrar en inscripciones y arbitrajes." if pendiente else None
        )
        self.al_dia.setVisible(not (paso or atrasados or sin_fecha))
