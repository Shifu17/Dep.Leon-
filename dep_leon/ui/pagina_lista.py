"""Página de pase de lista: estadísticas generales de asistencia y la lista por equipo o por partido."""

import sqlite3
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import asistencia, rol
from . import diseno
from .chips import DORADO, GRIS, VERDE, chips_en
from .comun import (
    al_activar,
    boton,
    confirmar,
    error,
    id_seleccionado,
    listo,
    llenar,
    poner_vacio,
    tabla,
)
from .controles import Segmentado
from .filtros import FiltrosLiga
from .lista import AYUDA_CUADRICULA, CuadriculaLista, pasar_lista

POR_EQUIPO = "Por equipo"
POR_PARTIDO = "Por partido"


def _chip_porcentaje(texto: str):
    if texto in ("-", ""):
        return GRIS
    valor = int(texto.rstrip("%"))
    return VERDE if valor >= 80 else DORADO if valor >= 50 else GRIS


class Cifra(QFrame):
    """Un número grande con su nombre y una línea que lo explica."""

    def __init__(self, titulo: str):
        super().__init__(objectName="tarjeta")
        diseno.sombra(self)
        self.numero = QLabel("-", objectName="tarjetaNumero")
        self.detalle = QLabel(objectName="ayuda", wordWrap=True)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(16, 10, 16, 10)
        columna.setSpacing(0)
        columna.addWidget(QLabel(titulo, objectName="tarjetaTexto"))
        columna.addWidget(self.numero)
        columna.addWidget(self.detalle)
        columna.addStretch(1)  # las cifras quedan a la misma altura aunque el texto ocupe dos renglones

    def mostrar(self, numero: str, detalle: str = "", alerta: bool = False):
        self.numero.setText(numero)
        self.detalle.setText(detalle)
        nombre = "tarjetaAlerta" if alerta else "tarjetaNumero"
        if self.numero.objectName() != nombre:
            self.numero.setObjectName(nombre)
            self.numero.style().unpolish(self.numero)
            self.numero.style().polish(self.numero)


class PaginaPaseLista(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn
        self.cuadricula: CuadriculaLista | None = None
        self._equipo_mostrado: int | None = None

        self.filtros = FiltrosLiga(conn, con_todas=True)
        self.filtros.cambiado.connect(self.refrescar)
        self.vista = Segmentado([POR_EQUIPO, POR_PARTIDO], "Pasar lista")
        self.vista.currentIndexChanged.connect(self._cambiar_vista)
        self.filtros.agregar("Pasar lista", self.vista, 0)

        # --- Estadísticas generales
        self.general = Cifra("Asistencia general")
        self.partidos = Cifra("Partidos con lista")
        self.perfectos = Cifra("Asistencia perfecta")
        self.faltistas = Cifra(f"Con {asistencia.FALTAS_ALERTA} faltas o más")
        cifras = QHBoxLayout()
        cifras.setSpacing(12)
        for cifra in (self.general, self.partidos, self.perfectos, self.faltistas):
            cifras.addWidget(cifra, 1)

        # --- Por equipo: equipos con su porcentaje, quiénes faltan más y la cuadrícula del elegido
        self.tabla_equipos = tabla(["Equipo", "Categoría", "Con lista", "Asistencia"], estirar=0)
        chips_en(self.tabla_equipos, 3, _chip_porcentaje, pequeno=True)
        self.tabla_equipos.horizontalHeaderItem(2).setToolTip("Partidos en los que se pasó lista al equipo")
        self.tabla_equipos.itemSelectionChanged.connect(self._mostrar_equipo)
        poner_vacio(self.tabla_equipos, "No hay equipos en este torneo.")
        self.tabla_faltas = tabla(["Jugador", "Equipo", "Faltas"], estirar=0)
        poner_vacio(self.tabla_faltas, f"Nadie lleva {asistencia.FALTAS_ALERTA} faltas o más.")

        izquierda = QVBoxLayout()
        izquierda.addWidget(QLabel("Equipos", objectName="seccion"))
        izquierda.addWidget(self.tabla_equipos, 3)
        izquierda.addWidget(QLabel("Jugadores que más faltan", objectName="seccion"))
        izquierda.addWidget(self.tabla_faltas, 2)

        self.titulo_cuadricula = QLabel("Lista del equipo", objectName="seccion")
        self.ayuda_cuadricula = QLabel(AYUDA_CUADRICULA, objectName="ayuda", wordWrap=True)
        self.lugar_cuadricula = QVBoxLayout()
        self.sin_equipo = QLabel(
            "Toca un equipo de la izquierda para ver su lista.", objectName="vacio",
            alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True,
        )
        self.lugar_cuadricula.addWidget(self.sin_equipo, 1)
        self.guardar_lista = boton("Guardar lista", self.guardar, icono="listo")
        self.guardar_lista.setEnabled(False)
        fila = QHBoxLayout()
        fila.addWidget(self.guardar_lista)
        self.aviso_cambios = QLabel(objectName="ayuda")
        fila.addWidget(self.aviso_cambios, 1)
        derecha = QVBoxLayout()
        derecha.addWidget(self.titulo_cuadricula)
        derecha.addWidget(self.ayuda_cuadricula)
        derecha.addLayout(self.lugar_cuadricula, 1)
        derecha.addLayout(fila)

        por_equipo = QWidget()
        columnas = QHBoxLayout(por_equipo)
        columnas.setContentsMargins(0, 0, 0, 0)
        columnas.setSpacing(14)
        columnas.addLayout(izquierda, 2)
        columnas.addLayout(derecha, 3)

        # --- Por partido: la lista de partidos y el pase de lista de cada uno
        self.tabla_partidos = tabla(["Fecha", "Hora", "Local", "Visitante", "Categoría", "Vinieron"], estirar=2)
        self.tabla_partidos.horizontalHeader().setSectionResizeMode(
            3, self.tabla_partidos.horizontalHeader().ResizeMode.Stretch
        )
        al_activar(self.tabla_partidos, self.pasar_lista_partido)
        poner_vacio(self.tabla_partidos, "Todavía no hay partidos con fecha. Se crean en «Rol de juegos».")
        acciones = diseno.FilaBotones()
        acciones.addWidget(boton("Pasar lista del partido", self.pasar_lista_partido, icono="lista"))
        por_partido = QWidget()
        caja = QVBoxLayout(por_partido)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.addWidget(QLabel(
            "Elige un partido y pulsa «Pasar lista del partido», o haz doble clic en él. Sirve para anotar "
            "quién llegó aunque el partido no haya terminado.", objectName="ayuda", wordWrap=True,
        ))
        caja.addLayout(acciones)
        caja.addWidget(self.tabla_partidos, 1)

        self.pila = QStackedWidget()
        self.pila.addWidget(por_equipo)
        self.pila.addWidget(por_partido)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(diseno.encabezado(
            "Pase de lista",
            "Quién vino a cada partido. Arriba ves cómo va la asistencia; abajo pasas lista por equipo "
            "(todos sus partidos) o por partido (los dos equipos).",
        ))
        raiz.addWidget(self.filtros)
        raiz.addLayout(cifras)
        raiz.addWidget(self.pila, 1)
        self.refrescar()

    def showEvent(self, evento):
        super().showEvent(evento)
        self.filtros.refrescar()  # lo marcado al capturar resultados también cuenta

    def _cambiar_vista(self, indice: int):
        self.pila.setCurrentIndex(indice)

    # --- Datos

    def refrescar(self):
        datos = asistencia.estadisticas(self.conn, self.filtros.torneo_id, self.filtros.categoria_id)
        porcentaje = datos.porcentaje
        self.general.mostrar(
            "-" if porcentaje is None else f"{porcentaje}%",
            "de los jugadores vino a sus partidos" if porcentaje is not None else "Aún no se pasa lista",
        )
        self.partidos.mostrar(
            str(datos.partidos_con_lista),
            f"de {datos.partidos_jugados} partidos jugados" if datos.partidos_jugados else "Aún no hay partidos jugados",
        )
        self.perfectos.mostrar(str(datos.perfectos), "jugadores no han faltado")
        faltistas = datos.con_muchas_faltas
        self.faltistas.mostrar(str(len(faltistas)), "jugadores; conviene hablar con su equipo", bool(faltistas))

        self._equipos = {e.equipo_id: e for e in datos.equipos}
        llenar(
            self.tabla_equipos,
            [
                (e.equipo_id, [e.nombre, e.categoria, f"{e.con_lista} de {e.jugados}" if e.jugados else e.con_lista,
                               "-" if e.porcentaje is None else f"{e.porcentaje}%"])
                for e in datos.equipos
            ],
        )
        self.tabla_equipos.setColumnHidden(1, self.filtros.categoria_id is not None)
        llenar(self.tabla_faltas, [(j.jugador_id, [j.nombre, j.equipo, j.faltas]) for j in faltistas[:20]])
        llenar(
            self.tabla_partidos,
            [
                (
                    p["id"],
                    [
                        date.fromisoformat(p["fecha"]).strftime("%d/%m/%Y"), p["hora"] or "-", p["local"],
                        p["visitante"], p["categoria"],
                        p["presentes"] if p["presentes"] else ("Sin lista" if p["estado"] != rol.PROGRAMADO else "-"),
                    ],
                )
                for p in asistencia.partidos_para_lista(self.conn, self.filtros.torneo_id, self.filtros.categoria_id)
            ],
        )
        if id_seleccionado(self.tabla_equipos) is None and self.tabla_equipos.rowCount():
            self.tabla_equipos.selectRow(0)
        else:
            self._mostrar_equipo(forzar=True)

    def _mostrar_equipo(self, forzar: bool = False):
        equipo_id = id_seleccionado(self.tabla_equipos)
        if equipo_id == self._equipo_mostrado and not forzar:
            return
        if self.cuadricula is not None and self.cuadricula.modificada and equipo_id != self._equipo_mostrado:
            anterior = self._equipos.get(self._equipo_mostrado)
            if anterior and confirmar(self, f"No guardaste la lista de «{anterior.nombre}». ¿Guardarla ahora?"):
                self.guardar()
        self._equipo_mostrado = equipo_id
        if self.cuadricula is not None:
            self.cuadricula.setParent(None)
            self.cuadricula.deleteLater()
            self.cuadricula = None
        equipo = self._equipos.get(equipo_id)
        self.aviso_cambios.setText("")
        if equipo is None:
            self.titulo_cuadricula.setText("Lista del equipo")
            self.sin_equipo.setText("Toca un equipo de la izquierda para ver su lista.")
            self.sin_equipo.show()
            self.guardar_lista.setEnabled(False)
            return
        self.titulo_cuadricula.setText(f"Lista de {equipo.nombre}")
        cuadricula = CuadriculaLista(self.conn, equipo_id)
        if not cuadricula.partidos or not cuadricula.jugadores:
            cuadricula.deleteLater()
            self.sin_equipo.setText(
                f"«{equipo.nombre}» todavía no tiene partidos en el rol."
                if not cuadricula.partidos else f"«{equipo.nombre}» todavía no tiene jugadores."
            )
            self.sin_equipo.show()
            self.guardar_lista.setEnabled(False)
            return
        self.sin_equipo.hide()
        self.cuadricula = cuadricula
        cuadricula.cambiada.connect(lambda: self.aviso_cambios.setText("Hay cambios sin guardar."))
        self.lugar_cuadricula.addWidget(cuadricula, 1)
        self.guardar_lista.setEnabled(True)

    # --- Acciones

    def guardar(self):
        if self.cuadricula is None:
            return
        equipo = self._equipos.get(self._equipo_mostrado)
        try:
            self.cuadricula.guardar()
        except ValueError as exc:
            error(self, str(exc))
            return
        self.aviso_cambios.setText("")
        self.refrescar()
        listo(self, f"pase de lista de «{equipo.nombre if equipo else ''}» guardado.")

    def pasar_lista_partido(self):
        partido_id = id_seleccionado(self.tabla_partidos)
        if partido_id is None:
            error(self, "Primero selecciona un partido.")
            return
        partido = self.conn.execute(
            """SELECT p.*, l.nombre AS local, v.nombre AS visitante FROM partidos p
               JOIN equipos l ON l.id = p.local_id JOIN equipos v ON v.id = p.visitante_id WHERE p.id = ?""",
            (partido_id,),
        ).fetchone()
        if pasar_lista(self, self.conn, partido):
            self.refrescar()
            listo(self, "pase de lista guardado.")
