"""Página para capturar marcadores, goleadores y equipos que no se presentaron."""

import sqlite3
from datetime import date

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import arbitros, asistencia, liguilla, resultados, rol
from . import diseno
from .comun import (
    ayuda_pagina,
    AvisoCampo,
    al_activar,
    boton,
    botones_dialogo,
    campo_busqueda,
    confirmar,
    error,
    etiqueta,
    id_seleccionado,
    listo,
    llenar,
    tabla,
)
from .estrellas import NotaEquipo
from .filtros import FiltrosLiga
from .lista import ColumnaEquipo, pasar_lista
from .tema import ROJO

GOLES_MAXIMOS = 99
VER_POR_CAPTURAR = "Por capturar"
VER_CAPTURADOS = "Ya capturados"
VER_TODOS = "Todos"


class DialogoResultado(QDialog):
    def __init__(self, padre, conn: sqlite3.Connection, partido, local: str, visitante: str):
        super().__init__(padre)
        self.setWindowTitle("Capturar resultado")
        self.resize(900, 680)
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
        presentes = asistencia.presentes(conn, partido["id"])
        self.local = ColumnaEquipo(
            conn, local, partido["local_id"], presentes, goles_previos, self.marcador_local
        )
        self.visitante = ColumnaEquipo(
            conn, visitante, partido["visitante_id"], presentes, goles_previos, self.marcador_visitante
        )

        columnas = QHBoxLayout()
        columnas.addWidget(self.local, 1)
        columnas.addSpacing(16)
        columnas.addWidget(self.visitante, 1)

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

        # El árbitro del partido, y lo que cada equipo opina de él (1 a 5 estrellas y un comentario).
        from .pagina_arbitros import combo_arbitros  # aquí, para no crear un ciclo al importar

        previo_arbitro = arbitros.de_partido(conn, partido["id"])
        self._arbitro_previo = previo_arbitro["id"] if previo_arbitro else None
        self._notas_previas = arbitros.notas_de_partido(conn, partido["id"])
        self.arbitro = combo_arbitros(conn, self._arbitro_previo)
        self.arbitro.setMinimumWidth(240)
        self.arbitro.currentIndexChanged.connect(self._al_cambiar_arbitro)
        fila_arbitro = QHBoxLayout()
        fila_arbitro.setSpacing(10)
        fila_arbitro.addWidget(etiqueta("Árbitro:", self.arbitro))
        fila_arbitro.addWidget(self.arbitro)
        if self.arbitro.count() == 1:
            fila_arbitro.addWidget(QLabel("Registra árbitros en la página «Árbitros».", objectName="ayuda"))
        fila_arbitro.addStretch(1)
        raiz.addLayout(fila_arbitro)

        self.notas = {
            partido["local_id"]: NotaEquipo(local),
            partido["visitante_id"]: NotaEquipo(visitante),
        }
        notas = QHBoxLayout()
        notas.setSpacing(16)
        for nota in self.notas.values():
            notas.addWidget(nota, 1)
        raiz.addLayout(notas)
        self._al_cambiar_arbitro()

        raiz.addWidget(
            QLabel(
                "Marca quién vino y, si quieres, quién anotó. Puedes dejar goles sin jugador "
                "(como un autogol), pero no asignar más goles que los del marcador.",
                objectName="ayuda", wordWrap=True,
            )
        )
        self.aviso = AvisoCampo()
        raiz.addWidget(self.aviso)
        raiz.addWidget(botones_dialogo(self, self._aceptar))

    @property
    def goles(self) -> dict:
        """Control de goles de cada jugador de los dos equipos."""
        return {**self.local.goles, **self.visitante.goles}

    def _al_cambiar_arbitro(self):
        # Las calificaciones eran para el árbitro anterior: con otro se empieza de cero.
        mismo = self.arbitro.currentData() is not None and self.arbitro.currentData() == self._arbitro_previo
        for equipo_id, nota in self.notas.items():
            previa = self._notas_previas.get(equipo_id) if mismo else None
            nota.poner(previa["estrellas"] or 0 if previa else 0, previa["comentario"] if previa else "")
            nota.setEnabled(self.arbitro.currentData() is not None)

    def goleadores(self) -> dict[int, int]:
        return {**self.local.goleadores(), **self.visitante.goleadores()}

    def _aceptar(self):
        try:
            resultados.guardar_resultado(
                self.conn, self.partido["id"], self.marcador_local.value(),
                self.marcador_visitante.value(), self.goleadores(),
                (self.penales_local.value(), self.penales_visitante.value())
                if self.pide_penales
                else None,
            )
            # Quien anotó, vino, aunque no lo hayan marcado.
            asistencia.guardar(
                self.conn, self.partido["id"],
                self.local.presentes() | self.visitante.presentes() | set(self.goleadores()),
            )
            arbitro_id = self.arbitro.currentData()
            arbitros.asignar(self.conn, self.partido["id"], arbitro_id)
            if arbitro_id is not None:
                arbitros.calificar(
                    self.conn, self.partido["id"], {e: n.valores() for e, n in self.notas.items()}
                )
        except ValueError as exc:
            self.aviso.mostrar(str(exc))
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


def _arbitro(partido) -> str:
    if not partido["arbitro"]:
        return "-"
    if partido["calificacion"]:
        return f"{partido['arbitro']} ({partido['calificacion']:.1f} de 5)"
    return partido["arbitro"]


def _estado(partido) -> str:
    """Un partido cuya fecha ya pasó y no tiene resultado se señala como atrasado."""
    if partido["estado"] == rol.PROGRAMADO and partido["fecha"] and partido["fecha"] < rol.hoy().isoformat():
        return rol.ATRASADO
    return partido["estado"]


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

        acciones = diseno.FilaBotones()
        for texto, accion, estilo, ayuda in (
            ("Capturar resultado", self.capturar, None, "Anota el marcador, quién vino y quién anotó."),
            ("Pase de lista", self.pase_de_lista, "secundario", "Anota quién llegó, aunque el partido no termine."),
            ("No se presentó", self.no_se_presento, "secundario", "Da el partido por default o lo pospone."),
            ("Borrar resultado", self.borrar, "peligro", "Regresa el partido a «por jugar»."),
        ):
            control = boton(texto, accion, estilo)
            control.setToolTip(ayuda)
            acciones.addWidget(control)
        acciones.addStretch(1)
        self.fila_acciones = acciones

        self.tabla = tabla(
            ["Fecha", "Hora", "Equipo", "Marcador", "Equipo", "Categoría", "Fase", "Estado", "Árbitro"], estirar=2
        )
        self.tabla.horizontalHeader().setSectionResizeMode(
            4, self.tabla.horizontalHeader().ResizeMode.Stretch
        )
        al_activar(self.tabla, self.capturar)
        self.busqueda = campo_busqueda(self.tabla, "Buscar equipo")
        self.fila_acciones.addWidget(self.busqueda)
        self.vacio = QLabel(objectName="ayuda", wordWrap=True)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(QLabel("Resultados", objectName="titulo"))
        raiz.addWidget(ayuda_pagina(
            "Toca un partido y pulsa «Capturar resultado» para anotar el marcador, los goles y quién vino. Con «Pase de lista» anotas la asistencia antes de que termine el partido."
        ))
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
                       r.goles_local, r.goles_visitante, a.nombre AS arbitro,
                       (SELECT AVG(n.estrellas) FROM calificaciones_arbitro n WHERE n.partido_id = p.id)
                           AS calificacion
                FROM partidos p JOIN equipos l ON l.id = p.local_id
                JOIN equipos v ON v.id = p.visitante_id JOIN categorias c ON c.id = p.categoria_id
                LEFT JOIN resultados r ON r.partido_id = p.id
                LEFT JOIN arbitrajes x ON x.partido_id = p.id LEFT JOIN arbitros a ON a.id = x.arbitro_id
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
                        p["visitante"], p["categoria"], rol.nombre_jornada(p["jornada"]), _estado(p),
                        _arbitro(p),
                    ],
                )
                for p in filas
            ],
        )
        for f in range(self.tabla.rowCount()):
            if self.tabla.item(f, 7).text() == rol.ATRASADO:
                self.tabla.item(f, 7).setForeground(QColor(ROJO))
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
            listo(self, "resultado guardado.")

    def pase_de_lista(self):
        partido = self._partido()
        if partido is not None and pasar_lista(self, self.conn, _partido_completo(self.conn, partido)):
            listo(self, "pase de lista guardado.")

    def no_se_presento(self):
        partido = self._partido()
        if partido is not None and marcar_no_presentado(self, self.conn, partido):
            self.refrescar_partidos()
            listo(self, "partido actualizado.")

    def borrar(self):
        partido = self._partido()
        if partido is not None and borrar_resultado(self, self.conn, partido):
            self.refrescar_partidos()
            listo(self, "resultado borrado.")
