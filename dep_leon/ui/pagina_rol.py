"""Página del rol de juegos, con el formato de la hoja de la liga."""

import sqlite3
from datetime import date

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .. import rol
from .comun import boton, botones_dialogo, confirmar, error, id_seleccionado, info, llenar, tabla


def _a_qtime(minutos: int) -> QTime:
    return QTime(minutos // 60, minutos % 60)


def _a_minutos(hora: QTime) -> int:
    return hora.hour() * 60 + hora.minute()


class DialogoGenerar(QDialog):
    def __init__(self, padre, liga, categorias, guardada: dict | None):
        super().__init__(padre)
        self.setWindowTitle("Generar rol de juegos")
        raiz = QVBoxLayout(self)

        raiz.addWidget(QLabel("Categorías", objectName="seccion"))
        rejilla = QGridLayout()
        self.categorias = []
        for i, c in enumerate(categorias):
            casilla = QCheckBox(f"{c['nombre']} ({c['equipos']} equipos)", checked=c["equipos"] >= 2)
            casilla.setEnabled(c["equipos"] >= 2)
            self.categorias.append((c["id"], casilla))
            rejilla.addWidget(casilla, i // 3, i % 3)
        raiz.addLayout(rejilla)

        raiz.addWidget(QLabel("Días y horarios de juego", objectName="seccion"))
        dias_liga = rol.dias_de_texto(liga["dias"])
        dias_guardados = guardada["dias"] if guardada else {}
        tabla_dias = QGridLayout()
        tabla_dias.addWidget(QLabel("Primer partido"), 0, 1)
        tabla_dias.addWidget(QLabel("Terminar antes de"), 0, 2)
        self.dias = []
        for i, nombre in enumerate(rol.DIAS):
            activo = i in dias_guardados if guardada else i in dias_liga
            inicio, fin = dias_guardados.get(i, (rol.HORA_INICIO, rol.HORA_FIN))
            casilla = QCheckBox(nombre, checked=activo)
            desde = QTimeEdit(_a_qtime(inicio), displayFormat="HH:mm")
            hasta = QTimeEdit(_a_qtime(fin), displayFormat="HH:mm")
            for control in (desde, hasta):
                control.setEnabled(activo)
                casilla.toggled.connect(control.setEnabled)
            self.dias.append((i, casilla, desde, hasta))
            tabla_dias.addWidget(casilla, i + 1, 0)
            tabla_dias.addWidget(desde, i + 1, 1)
            tabla_dias.addWidget(hasta, i + 1, 2)
        raiz.addLayout(tabla_dias)

        forma = QFormLayout()
        self.fecha = QDateEdit(QDate.currentDate(), calendarPopup=True, displayFormat="dd/MM/yyyy")
        self.minutos = QSpinBox(
            minimum=10, maximum=180, value=guardada["minutos"] if guardada else rol.MINUTOS_PARTIDO,
            suffix=" minutos",
        )
        forma.addRow("Empezar a partir del:", self.fecha)
        forma.addRow("Un partido cada:", self.minutos)

        self.canchas = []
        posibles = rol.canchas_de_modalidad(liga["modalidad"])
        guardadas = guardada["canchas"] if guardada else posibles
        fila_canchas = QHBoxLayout()
        for cancha in posibles:
            texto = "Terreno completo (Fut 11)" if cancha == rol.CANCHA_FUT_11 else f"Cancha {cancha}"
            casilla = QCheckBox(texto, checked=cancha in guardadas)
            self.canchas.append((cancha, casilla))
            fila_canchas.addWidget(casilla)
        fila_canchas.addStretch(1)
        forma.addRow("Canchas:", fila_canchas)

        self.ida_y_vuelta = QCheckBox(
            "Jugar ida y vuelta", checked=bool(guardada and guardada["ida_y_vuelta"])
        )
        forma.addRow("", self.ida_y_vuelta)
        raiz.addLayout(forma)

        raiz.addWidget(
            QLabel(
                "Cada jornada se juega en una semana. Si la categoría ya tiene rol, se reemplaza "
                "por completo, incluidos los cambios hechos a mano y los partidos pospuestos.",
                objectName="ayuda", wordWrap=True,
            )
        )
        raiz.addWidget(botones_dialogo(self, self._aceptar, "Generar"))

    def categorias_elegidas(self) -> list[int]:
        return [i for i, casilla in self.categorias if casilla.isChecked()]

    def horario(self) -> rol.Horario:
        return rol.Horario(
            fecha_inicio=self.fecha.date().toPython(),
            dias={
                i: (_a_minutos(desde.time()), _a_minutos(hasta.time()))
                for i, casilla, desde, hasta in self.dias
                if casilla.isChecked()
            },
            minutos=self.minutos.value(),
            canchas=tuple(c for c, casilla in self.canchas if casilla.isChecked()),
        )

    def _aceptar(self):
        horario = self.horario()
        if not self.categorias_elegidas():
            error(self, "Elige al menos una categoría con 2 equipos o más.")
        elif not horario.dias:
            error(self, "Elige al menos un día de juego.")
        elif not horario.canchas:
            error(self, "Elige al menos una cancha.")
        elif any(fin - inicio < horario.minutos for inicio, fin in horario.dias.values()):
            error(self, "En cada día, el horario debe alcanzar para al menos un partido.")
        else:
            self.accept()


class DialogoPartido(QDialog):
    def __init__(self, padre, conn, torneo_id, modalidad, categorias, partido=None, categoria_id=None):
        super().__init__(padre)
        self.setWindowTitle("Partido")
        self.conn = conn
        self.torneo_id = torneo_id
        self.partido = partido

        self.categoria = QComboBox()
        for c in categorias:
            self.categoria.addItem(c["nombre"], c["id"])
        self.local = QComboBox()
        self.visitante = QComboBox()
        self.jornada = QSpinBox(minimum=1, maximum=200)
        self.fecha = QDateEdit(QDate.currentDate(), calendarPopup=True, displayFormat="dd/MM/yyyy")
        self.hora = QTimeEdit(_a_qtime(rol.HORA_INICIO), displayFormat="HH:mm")
        self.minutos = QSpinBox(minimum=10, maximum=180, value=rol.MINUTOS_PARTIDO, suffix=" minutos")
        self.cancha = QComboBox()
        for cancha in rol.canchas_de_modalidad(modalidad):
            self.cancha.addItem(rol.nombre_cancha(cancha), cancha)

        self.categoria.currentIndexChanged.connect(self._cargar_equipos)
        inicial = partido["categoria_id"] if partido else categoria_id
        if inicial is not None:
            self.categoria.setCurrentIndex(max(self.categoria.findData(inicial), 0))
        self._cargar_equipos()

        if partido:
            self.categoria.setEnabled(False)
            self.local.setCurrentIndex(self.local.findData(partido["local_id"]))
            self.visitante.setCurrentIndex(self.visitante.findData(partido["visitante_id"]))
            self.jornada.setValue(partido["jornada"])
            self.minutos.setValue(partido["minutos"])
            if partido["fecha"]:
                self.fecha.setDate(QDate.fromString(partido["fecha"], "yyyy-MM-dd"))
                self.hora.setTime(_a_qtime(rol.a_minutos(partido["hora"])))
                if self.cancha.findData(partido["cancha"]) < 0:
                    self.cancha.addItem(rol.nombre_cancha(partido["cancha"]), partido["cancha"])
                self.cancha.setCurrentIndex(self.cancha.findData(partido["cancha"]))
        elif self.visitante.count() > 1:
            self.visitante.setCurrentIndex(1)

        forma = QFormLayout(self)
        forma.addRow("Categoría:", self.categoria)
        forma.addRow("Equipo:", self.local)
        forma.addRow("Equipo:", self.visitante)
        forma.addRow("Jornada:", self.jornada)
        forma.addRow("Fecha:", self.fecha)
        forma.addRow("Hora:", self.hora)
        forma.addRow("Duración:", self.minutos)
        forma.addRow("Cancha:", self.cancha)
        forma.addRow(botones_dialogo(self, self._aceptar))

    def _cargar_equipos(self):
        filas = self.conn.execute(
            "SELECT id, nombre FROM equipos WHERE torneo_id = ? AND categoria_id = ? ORDER BY nombre",
            (self.torneo_id, self.categoria.currentData()),
        ).fetchall()
        for control in (self.local, self.visitante):
            control.clear()
            for f in filas:
                control.addItem(f["nombre"], f["id"])
        if len(filas) > 1:
            self.visitante.setCurrentIndex(1)

    def valores(self):
        return (
            self.fecha.date().toPython(), _a_minutos(self.hora.time()), self.minutos.value(),
            self.cancha.currentData(), self.local.currentData(), self.visitante.currentData(),
        )

    def _aceptar(self):
        fecha, hora, minutos, cancha, local, visitante = self.valores()
        if local is None or visitante is None:
            error(self, "Esta categoría todavía no tiene equipos.")
            return
        if local == visitante:
            error(self, "Un equipo no puede jugar contra sí mismo.")
            return
        conflicto = rol.buscar_conflicto(
            self.conn, fecha, hora, minutos, cancha, local, visitante,
            self.partido["id"] if self.partido else None,
        )
        if conflicto:
            error(self, conflicto)
            return
        self.accept()


class PaginaRol(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn

        self.titulo = QLabel(
            "Rol de juegos", objectName="titulo", alignment=Qt.AlignmentFlag.AlignCenter
        )
        self.liga = QComboBox()
        self.torneo = QComboBox()
        self.categoria = QComboBox()
        self.fecha = QComboBox()
        self.liga.currentIndexChanged.connect(self._al_cambiar_liga)
        self.torneo.currentIndexChanged.connect(self._al_cambiar_torneo)
        self.categoria.currentIndexChanged.connect(self._al_cambiar_torneo)
        self.fecha.currentIndexChanged.connect(self.refrescar_partidos)

        filtros = QHBoxLayout()
        for texto, control in (
            ("Liga:", self.liga), ("Torneo:", self.torneo),
            ("Categoría:", self.categoria), ("Fecha:", self.fecha),
        ):
            filtros.addWidget(QLabel(texto))
            filtros.addWidget(control, 1)

        self.tabla = tabla(
            ["Fecha", "Hora", "Equipo", "Equipo", "Categoría", "Cancha", "Jornada", "Estado"], estirar=2
        )
        self.tabla.horizontalHeader().setSectionResizeMode(
            3, self.tabla.horizontalHeader().ResizeMode.Stretch
        )
        self.descansan = QLabel(objectName="ayuda", wordWrap=True)

        acciones = QHBoxLayout()
        acciones.addWidget(boton("Generar rol", self.generar))
        acciones.addWidget(boton("Agregar partido", self.agregar, "secundario"))
        acciones.addWidget(boton("Editar o reprogramar", self.editar, "secundario"))
        acciones.addWidget(boton("Posponer", self.posponer, "secundario"))
        acciones.addWidget(boton("Eliminar", self.eliminar, "peligro"))
        acciones.addStretch(1)

        raiz = QVBoxLayout(self)
        raiz.addWidget(self.titulo)
        raiz.addLayout(filtros)
        raiz.addLayout(acciones)
        raiz.addWidget(self.tabla, 1)
        raiz.addWidget(self.descansan)
        self.refrescar()

    def _liga(self):
        return self.conn.execute("SELECT * FROM ligas WHERE id = ?", (self.liga.currentData(),)).fetchone()

    def _categorias(self):
        return self.conn.execute(
            """SELECT c.id, c.nombre,
                      (SELECT COUNT(*) FROM equipos e
                       WHERE e.categoria_id = c.id AND e.torneo_id = ?) AS equipos
               FROM categorias c WHERE c.liga_id = ? ORDER BY c.nombre""",
            (self.torneo.currentData(), self.liga.currentData()),
        ).fetchall()

    def refrescar(self):
        actual = self.liga.currentData()
        self.liga.blockSignals(True)
        self.liga.clear()
        for l in self.conn.execute("SELECT * FROM ligas ORDER BY id"):
            self.liga.addItem(l["nombre"], l["id"])
        indice = self.liga.findData(actual)
        if indice < 0:
            # Empieza en la primera liga que ya tiene categorías cargadas.
            con_datos = self.conn.execute(
                "SELECT liga_id FROM categorias ORDER BY liga_id LIMIT 1"
            ).fetchone()
            indice = self.liga.findData(con_datos["liga_id"]) if con_datos else 0
        self.liga.setCurrentIndex(max(indice, 0))
        self.liga.blockSignals(False)
        self._al_cambiar_liga()

    def _al_cambiar_liga(self):
        torneo, categoria = self.torneo.currentData(), self.categoria.currentData()
        for control in (self.torneo, self.categoria):
            control.blockSignals(True)
            control.clear()
        for t in self.conn.execute(
            "SELECT * FROM torneos WHERE liga_id = ? ORDER BY nombre", (self.liga.currentData(),)
        ):
            self.torneo.addItem(t["nombre"], t["id"])
        self.categoria.addItem("Todas", None)
        for c in self.conn.execute(
            "SELECT * FROM categorias WHERE liga_id = ? ORDER BY nombre", (self.liga.currentData(),)
        ):
            self.categoria.addItem(c["nombre"], c["id"])
        self.torneo.setCurrentIndex(max(self.torneo.findData(torneo), 0))
        self.categoria.setCurrentIndex(max(self.categoria.findData(categoria), 0))
        for control in (self.torneo, self.categoria):
            control.blockSignals(False)
        self._al_cambiar_torneo()

    def _al_cambiar_torneo(self):
        """Recarga las fechas: conserva la elegida o, si ya no existe, va a la próxima por jugarse."""
        actual = self.fecha.currentData()
        viendo_todas = self.fecha.count() > 0 and self.fecha.currentIndex() == 0
        fechas = [
            f["fecha"]
            for f in self.conn.execute(
                "SELECT DISTINCT fecha FROM partidos WHERE torneo_id = ? AND fecha IS NOT NULL "
                "AND (? IS NULL OR categoria_id = ?) ORDER BY fecha",
                (self.torneo.currentData(), self.categoria.currentData(), self.categoria.currentData()),
            )
        ]
        self.fecha.blockSignals(True)
        self.fecha.clear()
        self.fecha.addItem("Todas", None)
        for f in fechas:
            self.fecha.addItem(date.fromisoformat(f).strftime("%d/%m/%Y"), f)
        indice = 0 if viendo_todas else self.fecha.findData(actual) if actual else -1
        if indice < 0:
            proxima = next((f for f in fechas if f >= rol.hoy().isoformat()), None)
            indice = self.fecha.findData(proxima) if proxima else 0
        self.fecha.setCurrentIndex(max(indice, 0))
        self.fecha.blockSignals(False)
        self.refrescar_partidos()

    def refrescar_partidos(self):
        torneo, categoria, fecha = (
            self.torneo.currentData(), self.categoria.currentData(), self.fecha.currentData(),
        )
        # Con una fecha elegida también se ven los pospuestos, para no perderlos de vista.
        filas = self.conn.execute(
            """SELECT p.*, l.nombre AS local, v.nombre AS visitante, c.nombre AS categoria
               FROM partidos p JOIN equipos l ON l.id = p.local_id
               JOIN equipos v ON v.id = p.visitante_id JOIN categorias c ON c.id = p.categoria_id
               WHERE p.torneo_id = ? AND (? IS NULL OR p.categoria_id = ?)
                 AND (? IS NULL OR p.fecha = ? OR p.fecha IS NULL)
               ORDER BY p.fecha IS NULL, p.fecha, p.cancha, p.hora""",
            (torneo, categoria, categoria, fecha, fecha),
        ).fetchall()
        llenar(
            self.tabla,
            [
                (
                    p["id"],
                    [
                        date.fromisoformat(p["fecha"]).strftime("%d/%m/%Y") if p["fecha"] else "Por definir",
                        p["hora"] or "Por definir",
                        p["local"], p["visitante"], p["categoria"],
                        rol.nombre_cancha(p["cancha"]), p["jornada"], p["estado"],
                    ],
                )
                for p in filas
            ],
        )

        linea = self.torneo.currentText()
        partes = ["Rol de juegos"]
        if fecha:
            partes = [rol.fecha_larga(date.fromisoformat(fecha))]
        if linea:
            partes.append(f"Torneo {linea}")
        self.titulo.setText("\n".join(partes))

        if fecha and torneo:
            lista = rol.descansos(self.conn, torneo, fecha, categoria)
            self.descansan.setText(
                "Descansan: " + ", ".join(f"{e} ({c})" for c, e in lista) if lista else ""
            )
        else:
            self.descansan.setText("")

    def _exigir_torneo(self) -> bool:
        if self.torneo.currentData() is None:
            error(self, "Primero crea un torneo para esta liga en «Ligas y categorías».")
            return False
        return True

    def generar(self):
        if not self._exigir_torneo():
            return
        torneo = self.torneo.currentData()
        categorias = self._categorias()
        if not any(c["equipos"] >= 2 for c in categorias):
            error(self, "Registra al menos 2 equipos en una categoría de este torneo.")
            return
        dialogo = DialogoGenerar(
            self, self._liga(), categorias, rol.configuracion_guardada(self.conn, torneo)
        )
        if not dialogo.exec():
            return
        elegidas = dialogo.categorias_elegidas()
        marcas = ",".join("?" * len(elegidas))
        existentes = self.conn.execute(
            f"SELECT COUNT(*) FROM partidos WHERE torneo_id = ? AND categoria_id IN ({marcas})",
            (torneo, *elegidas),
        ).fetchone()[0]
        if existentes and not confirmar(
            self,
            f"Las categorías elegidas ya tienen {existentes} partidos. "
            "Se borrarán para crear el rol nuevo. ¿Continuar?",
        ):
            return
        horario = dialogo.horario()
        try:
            creados, avisos = rol.generar(
                self.conn, torneo, elegidas, horario, dialogo.ida_y_vuelta.isChecked()
            )
        except ValueError as exc:
            error(self, str(exc))
            return
        rol.guardar_configuracion(self.conn, torneo, horario, dialogo.ida_y_vuelta.isChecked())
        self.fecha.blockSignals(True)
        self.fecha.setCurrentIndex(-1)
        self.fecha.blockSignals(False)
        self._al_cambiar_torneo()
        info(self, "\n\n".join([f"Rol generado: {creados} partidos.", *avisos]))

    def _partido_seleccionado(self):
        partido_id = id_seleccionado(self.tabla)
        if partido_id is None:
            error(self, "Primero selecciona un partido.")
            return None
        return self.conn.execute("SELECT * FROM partidos WHERE id = ?", (partido_id,)).fetchone()

    def agregar(self):
        if not self._exigir_torneo():
            return
        categorias = self.conn.execute(
            "SELECT * FROM categorias WHERE liga_id = ? ORDER BY nombre", (self.liga.currentData(),)
        ).fetchall()
        if not categorias:
            error(self, "Primero crea una categoría para esta liga.")
            return
        dialogo = DialogoPartido(
            self, self.conn, self.torneo.currentData(), self._liga()["modalidad"], categorias,
            categoria_id=self.categoria.currentData(),
        )
        if dialogo.exec():
            fecha, hora, minutos, cancha, local, visitante = dialogo.valores()
            with self.conn:
                self.conn.execute(
                    "INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, "
                    "fecha, hora, minutos, cancha, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        self.torneo.currentData(), dialogo.categoria.currentData(),
                        dialogo.jornada.value(), local, visitante, fecha.isoformat(),
                        rol.a_hora(hora), minutos, cancha, rol.PROGRAMADO,
                    ),
                )
            self._al_cambiar_torneo()

    def editar(self):
        partido = self._partido_seleccionado()
        if partido is None:
            return
        categorias = self.conn.execute(
            "SELECT * FROM categorias WHERE liga_id = ? ORDER BY nombre", (self.liga.currentData(),)
        ).fetchall()
        dialogo = DialogoPartido(
            self, self.conn, self.torneo.currentData(), self._liga()["modalidad"], categorias, partido
        )
        if dialogo.exec():
            fecha, hora, minutos, cancha, local, visitante = dialogo.valores()
            with self.conn:
                self.conn.execute(
                    "UPDATE partidos SET jornada = ?, local_id = ?, visitante_id = ?, fecha = ?, "
                    "hora = ?, minutos = ?, cancha = ?, estado = ? WHERE id = ?",
                    (
                        dialogo.jornada.value(), local, visitante, fecha.isoformat(), rol.a_hora(hora),
                        minutos, cancha, rol.PROGRAMADO, partido["id"],
                    ),
                )
            self._al_cambiar_torneo()

    def posponer(self):
        partido = self._partido_seleccionado()
        if partido is None:
            return
        if partido["estado"] == rol.POSPUESTO:
            error(self, "Este partido ya está pospuesto. Usa «Editar o reprogramar» para darle fecha.")
            return
        if confirmar(self, "¿Posponer este partido? Quedará sin fecha y se liberará su cancha."):
            rol.posponer(self.conn, partido["id"])
            self._al_cambiar_torneo()

    def eliminar(self):
        partido = self._partido_seleccionado()
        if partido is not None and confirmar(self, "¿Eliminar este partido del rol?"):
            with self.conn:
                self.conn.execute("DELETE FROM partidos WHERE id = ?", (partido["id"],))
            self._al_cambiar_torneo()
