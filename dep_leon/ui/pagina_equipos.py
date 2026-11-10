"""Página de equipos y jugadores, con importación desde Excel y credenciales."""

import os
import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .. import asistencia, cobros, colores, credenciales, excel, registro, rol
from ..db import clave_orden
from ..jugadores import (
    NUMERO_MAX,
    POSICIONES,
    borrar_foto,
    error_de_edad,
    faltantes,
    guardar_foto,
    motivo_no_elegible,
)
from ..paths import fotos_dir
from . import campos
from .avatar import GRIS, VERDE, avatar
from .chips import DORADO as CHIP_DORADO, GRIS as CHIP_GRIS, VERDE as CHIP_VERDE, chips_en
from . import diseno
from .comun import (
    AccionesDeFila,
    AvisoCampo,
    actualizar_vacio,
    al_activar,
    boton,
    boton_mas,
    botones_dialogo,
    campo_busqueda,
    confirmar,
    error,
    fila_con_error,
    filtrar,
    id_seleccionado,
    id_seleccionado_en,
    info,
    listo,
    llenar,
    menu_de_fila,
    poner_vacio,
    tabla,
)
from .filtros import FiltrosLiga


class DialogoEquipo(QDialog):
    def __init__(self, padre, categorias, equipo=None):
        super().__init__(padre)
        self.setWindowTitle("Equipo")
        self.categoria = QComboBox()
        for c in categorias:
            self.categoria.addItem(c["nombre"], c["id"])
        self.nombre = QLineEdit(equipo["nombre"] if equipo else "")
        self.responsable = QLineEdit(equipo["responsable"] if equipo else "")
        self.asistente = QLineEdit(equipo["asistente"] if equipo else "")
        self.director = QLineEdit(equipo["director"] if equipo else "")
        self.telefono = QLineEdit(equipo["telefono"] if equipo else "")
        campos.solo_nombre_de_equipo(self.nombre, "Ejemplo: Club Deportivo León")
        for persona in (self.responsable, self.asistente, self.director):
            campos.solo_nombre(persona)
        campos.solo_telefono(self.telefono)
        self.rama = QComboBox()
        self.rama.addItem("Sin indicar", "")
        for rama in credenciales.RAMAS:
            self.rama.addItem(rama.capitalize(), rama)
        if equipo:
            self.categoria.setCurrentIndex(self.categoria.findData(equipo["categoria_id"]))
            self.rama.setCurrentIndex(max(0, self.rama.findData(equipo["rama"])))
        forma = QFormLayout(self)
        forma.addRow("Categoría:", self.categoria)
        self.error_nombre = fila_con_error(forma, "Nombre del club:", self.nombre)
        forma.addRow("Rama:", self.rama)
        forma.addRow("Entrenador:", self.responsable)
        forma.addRow("Asistente:", self.asistente)
        forma.addRow("Director general:", self.director)
        self.error_telefono = fila_con_error(forma, "Teléfono:", self.telefono)
        forma.addRow(botones_dialogo(self, self._aceptar))

    def _aceptar(self):
        if not self.nombre.text().strip():
            self.error_nombre.mostrar("Escribe el nombre del equipo.")
            return
        motivo = campos.error_telefono(self.telefono.text())
        if motivo:
            self.error_telefono.mostrar(motivo)
            return
        self.accept()


class DialogoDisponibilidad(QDialog):
    HORA_INICIO = 8 * 60
    HORA_FIN = 22 * 60

    def __init__(self, padre, equipo: str, dias: dict[int, tuple[int, int]]):
        super().__init__(padre)
        self.setWindowTitle("Disponibilidad del equipo")
        self.siempre = QCheckBox("Puede jugar cualquier día y a cualquier hora", checked=not dias)
        self.filas = []
        rejilla = QGridLayout()
        rejilla.addWidget(QLabel("Puede jugar"), 0, 0)
        rejilla.addWidget(QLabel("Desde"), 0, 1)
        rejilla.addWidget(QLabel("Hasta"), 0, 2)
        for i, nombre in enumerate(rol.DIAS):
            desde, hasta = dias.get(i, (self.HORA_INICIO, self.HORA_FIN))
            casilla = QCheckBox(nombre, checked=i in dias)
            inicio = QTimeEdit(QTime(desde // 60, desde % 60), displayFormat="HH:mm")
            fin = QTimeEdit(QTime(hasta // 60, hasta % 60), displayFormat="HH:mm")
            inicio.setAccessibleName(f"{nombre}: desde")
            fin.setAccessibleName(f"{nombre}: hasta")
            self.filas.append((i, casilla, inicio, fin))
            rejilla.addWidget(casilla, i + 1, 0)
            rejilla.addWidget(inicio, i + 1, 1)
            rejilla.addWidget(fin, i + 1, 2)
            casilla.toggled.connect(self._actualizar)
        self.siempre.toggled.connect(self._actualizar)

        raiz = QVBoxLayout(self)
        raiz.addWidget(QLabel(equipo, objectName="seccion"))
        raiz.addWidget(self.siempre)
        raiz.addLayout(rejilla)
        raiz.addWidget(
            QLabel(
                "El rol automático solo programa a este equipo en estos horarios.",
                objectName="ayuda", wordWrap=True,
            )
        )
        self.aviso = AvisoCampo()
        raiz.addWidget(self.aviso)
        raiz.addWidget(botones_dialogo(self, self._aceptar))
        self._actualizar()

    def _actualizar(self):
        libre = not self.siempre.isChecked()
        for _, casilla, inicio, fin in self.filas:
            casilla.setEnabled(libre)
            inicio.setEnabled(libre and casilla.isChecked())
            fin.setEnabled(libre and casilla.isChecked())

    def valores(self) -> dict[int, tuple[int, int]]:
        if self.siempre.isChecked():
            return {}
        return {
            i: (
                inicio.time().hour() * 60 + inicio.time().minute(),
                fin.time().hour() * 60 + fin.time().minute(),
            )
            for i, casilla, inicio, fin in self.filas
            if casilla.isChecked()
        }

    def _aceptar(self):
        valores = self.valores()
        if not self.siempre.isChecked() and not valores:
            self.aviso.mostrar("Marca al menos un día, o la opción de cualquier día.")
            return
        if any(desde >= hasta for desde, hasta in valores.values()):
            self.aviso.mostrar("En cada día, la hora «desde» debe ser menor que la hora «hasta».")
            return
        self.accept()


class DialogoJugador(QDialog):
    def __init__(self, padre, categoria, jugador=None):
        super().__init__(padre)
        self.setWindowTitle("Jugador")
        self.categoria = categoria
        self.ruta_foto: Path | None = None
        self.nombre = QLineEdit(jugador["nombre"] if jugador else "")
        self.fecha = QDateEdit(calendarPopup=True, displayFormat="dd/MM/yyyy")
        self.fecha.setMaximumDate(QDate.currentDate())
        anio = categoria["anio_min"] or date.today().year - 18
        self.fecha.setDate(QDate(anio, 1, 1))
        # -1 se muestra como «Sin número»: la hoja de registro de los clubes a veces no lo trae.
        self.numero = QSpinBox(minimum=-1, maximum=NUMERO_MAX, value=-1, specialValueText="Sin número")
        self.curp = QLineEdit(jugador["curp"] if jugador else "", maxLength=18)
        self.curp.setPlaceholderText("18 letras y números (opcional)")
        campos.solo_nombre(self.nombre, "Nombre y apellidos")
        campos.solo_curp(self.curp)
        self.posicion = QComboBox()
        self.posicion.addItems([""] + POSICIONES)
        self.vista_foto = QLabel("Sin foto", objectName="marcoFoto", alignment=Qt.AlignmentFlag.AlignCenter)
        self.vista_foto.setFixedSize(110, 130)
        if jugador:
            self.fecha.setDate(QDate.fromString(jugador["fecha_nacimiento"], "yyyy-MM-dd"))
            self.numero.setValue(-1 if jugador["numero"] is None else jugador["numero"])
            self.posicion.setCurrentText(jugador["posicion"])
            if jugador["foto"]:
                self._mostrar_foto(fotos_dir() / jugador["foto"])

        forma = QFormLayout(self)
        self.error_nombre = fila_con_error(forma, "Nombre completo:", self.nombre)
        self.error_fecha = fila_con_error(forma, "Fecha de nacimiento:", self.fecha)
        forma.addRow("Número de playera:", self.numero)
        self.error_curp = fila_con_error(forma, "CURP:", self.curp)
        forma.addRow("Posición:", self.posicion)
        forma.addRow("Foto:", self.vista_foto)
        forma.addRow("", boton("Elegir foto...", self._elegir_foto, "secundario"))
        forma.addRow(botones_dialogo(self, self._aceptar))

    def _mostrar_foto(self, ruta: Path):
        imagen = QPixmap(str(ruta))
        if imagen.isNull():
            return False
        self.vista_foto.setPixmap(
            imagen.scaled(
                self.vista_foto.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        return True

    def _elegir_foto(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Elegir foto", "", "Imágenes (*.jpg *.jpeg *.png)")
        if not ruta:
            return
        if self._mostrar_foto(Path(ruta)):
            self.ruta_foto = Path(ruta)
        else:
            error(self, "No se pudo leer esa imagen.")

    def fecha_nacimiento(self) -> date:
        return self.fecha.date().toPython()

    def numero_playera(self) -> int | None:
        return None if self.numero.value() < 0 else self.numero.value()

    def curp_limpia(self) -> str:
        return self.curp.text().strip().upper().replace(" ", "")

    def _aceptar(self):
        if not self.nombre.text().strip():
            self.error_nombre.mostrar("Escribe el nombre del jugador.")
            return
        motivo = error_de_edad(
            self.fecha_nacimiento(), self.categoria["anio_min"], self.categoria["anio_max"]
        )
        if motivo:
            self.error_fecha.mostrar(motivo)
            return
        curp = self.curp_limpia()
        if curp and (len(curp) != 18 or not curp.isalnum()):
            self.error_curp.mostrar("La CURP tiene 18 letras y números; revísala o déjala vacía.")
            return
        self.accept()


class DialogoImportacion(QDialog):
    """Vista previa: muestra cada renglón y deja importar solo los válidos."""

    def __init__(self, padre, filas: list[excel.Fila]):
        super().__init__(padre)
        self.setWindowTitle("Vista previa de la importación")
        self.resize(980, 560)
        validas = sum(f.valida for f in filas)
        con_error = len(filas) - validas
        resumen = QLabel(
            f"{validas} jugadores listos para registrar · {con_error} renglones con error.",
            objectName="seccion",
        )
        ayuda = QLabel(
            "Los renglones con error no se registran; corrígelos en Excel y vuelve a importar.",
            objectName="ayuda",
        )
        vista = tabla(["Renglón", "Categoría", "Equipo", "Jugador", "Núm.", "Estado"])
        estados = []
        for f in filas:
            if f.errores:
                estado = "Error: " + " ".join(f.errores)
            elif f.avisos:
                estado = "Aviso: " + " ".join(f.avisos)
            else:
                estado = "Actualizar" if f.jugador_id else "Nuevo"
            estados.append((f.renglon, [f.renglon, f.categoria, f.equipo, f.nombre, f.numero, estado]))
        llenar(vista, estados)
        for r, f in enumerate(filas):
            if f.errores:
                for c in range(vista.columnCount()):
                    vista.item(r, c).setForeground(QColor(colores.ROJO))

        caja = QDialogButtonBox()
        importar = caja.addButton(
            f"Importar {validas} jugadores", QDialogButtonBox.ButtonRole.AcceptRole
        )
        importar.setEnabled(validas > 0)
        cancelar = caja.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        cancelar.setObjectName("secundario")
        caja.accepted.connect(self.accept)
        caja.rejected.connect(self.reject)

        raiz = QVBoxLayout(self)
        raiz.addWidget(resumen)
        raiz.addWidget(ayuda)
        raiz.addWidget(vista)
        raiz.addWidget(caja)


class DialogoRegistros(QDialog):
    """Vista previa de las hojas de registro: un renglón por equipo, con su categoría y sus jugadores."""

    def __init__(self, padre, conn, registros: list[registro.Registro], torneo_id: int, categorias):
        super().__init__(padre)
        self.setWindowTitle("Revisa antes de importar")
        self.resize(1040, 640)
        self.conn = conn
        self.registros = registros
        self.torneo_id = torneo_id

        self.resumen = QLabel(objectName="seccion")
        self.equipos = tabla(["Archivo", "Equipo", "Categoría en el Excel", "Categoría en el programa", "Listos", "Con error"], estirar=1)
        self.equipos.setSortingEnabled(False)
        self.jugadores = tabla(["Renglón", "Núm.", "Jugador", "Nacimiento", "CURP", "Estado"], estirar=5)
        self.jugadores.setSortingEnabled(False)

        self.equipos.setRowCount(len(registros))
        for r, reg in enumerate(registros):
            for c, valor in enumerate([reg.archivo, reg.equipo, " ".join(x for x in (reg.categoria, reg.rama) if x)]):
                self.equipos.setItem(r, c, QTableWidgetItem(valor))
            combo = QComboBox()
            for cat in categorias:
                combo.addItem(cat["nombre"], cat["id"])
            combo.addItem(f"Crear nueva: «{registro.nombre_sugerido(reg)}»", registro.CATEGORIA_NUEVA)
            combo.setCurrentIndex(combo.findData(reg.categoria_id))
            combo.setAccessibleName(f"Categoría para {reg.equipo}")
            combo.currentIndexChanged.connect(lambda _=0, fila=r, cb=combo: self._cambiar_categoria(fila, cb))
            self.equipos.setCellWidget(r, 3, combo)
        self.equipos.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.equipos.itemSelectionChanged.connect(self._mostrar_jugadores)

        caja = QDialogButtonBox()
        self.importar = caja.addButton("Importar", QDialogButtonBox.ButtonRole.AcceptRole)
        cancelar = caja.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        cancelar.setObjectName("secundario")
        caja.accepted.connect(self.accept)
        caja.rejected.connect(self.reject)

        raiz = QVBoxLayout(self)
        raiz.addWidget(self.resumen)
        raiz.addWidget(
            QLabel(
                "Revisa que cada equipo quede en la categoría correcta; si no existe, se crea al importar. "
                "Toca un equipo para ver sus jugadores. Los renglones con error no se registran: corrígelos "
                "en Excel y vuelve a importar, sin miedo a duplicar.",
                objectName="ayuda", wordWrap=True,
            )
        )
        raiz.addWidget(self.equipos, 2)
        raiz.addWidget(QLabel("Jugadores del equipo elegido", objectName="seccion"))
        raiz.addWidget(self.jugadores, 3)
        raiz.addWidget(caja)
        self._actualizar()
        self.equipos.selectRow(0)

    def _cambiar_categoria(self, fila: int, combo: QComboBox):
        reg = self.registros[fila]
        reg.categoria_id = combo.currentData()
        reg.nombre_categoria_nueva = registro.nombre_sugerido(reg)
        registro.validar(self.conn, reg, self.torneo_id)
        self._actualizar()
        self.equipos.selectRow(fila)
        self._mostrar_jugadores()

    def _actualizar(self):
        for r, reg in enumerate(self.registros):
            con_error = len(reg.filas) - reg.validas if not reg.errores else len(reg.crudos)
            for c, valor in ((4, reg.validas), (5, con_error)):
                celda = QTableWidgetItem(str(valor))
                celda.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 5 and valor:
                    celda.setForeground(QColor(colores.ROJO))
                self.equipos.setItem(r, c, celda)
        listos = sum(reg.validas for reg in self.registros)
        equipos = sum(1 for reg in self.registros if reg.validas)
        self.resumen.setText(
            f"{_cuantos(len(self.registros), 'equipo encontrado', 'equipos encontrados')} · "
            f"{_cuantos(listos, 'jugador listo', 'jugadores listos')} para registrar"
        )
        self.importar.setText(
            f"Importar {_cuantos(listos, 'jugador', 'jugadores')} de {_cuantos(equipos, 'equipo', 'equipos')}"
        )
        self.importar.setEnabled(listos > 0)

    def _mostrar_jugadores(self):
        fila = self.equipos.currentRow()
        if fila < 0:
            return
        reg = self.registros[fila]
        renglones = []
        for f in reg.filas:
            if reg.errores:
                estado = "Error: " + " ".join(reg.errores)
            elif f.errores:
                estado = "Error: " + " ".join(f.errores)
            elif f.avisos:
                estado = "Aviso: " + " ".join(f.avisos)
            else:
                estado = "Actualizar" if f.jugador_id else "Nuevo"
            nacimiento = f.fecha.strftime("%d/%m/%Y") if f.fecha else "-"
            renglones.append((f.renglon, [f.renglon, f.numero, f.nombre, nacimiento, f.curp, estado]))
        llenar(self.jugadores, renglones)
        for r, f in enumerate(reg.filas):
            if f.errores or reg.errores:
                for c in range(self.jugadores.columnCount()):
                    self.jugadores.item(r, c).setForeground(QColor(colores.ROJO))


class DialogoListaEquipo(QDialog):
    """Pase de lista del equipo en todos sus partidos, como las columnas J1, J2... de la hoja de registro.

    Basta un clic en la celda (o la barra espaciadora) para marcar o desmarcar: es más fácil de atinar
    que una casilla pequeña.
    """

    ANCHO_PARTIDO = 64
    MARCA = "Sí"  # texto, no un símbolo: se lee igual con cualquier fuente

    def __init__(self, padre, conn, equipo_id: int, nombre: str):
        super().__init__(padre)
        self.setWindowTitle(f"Pase de lista: {nombre}")
        self.resize(980, 600)
        self.conn = conn
        self.equipo_id = equipo_id
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
            nombre_jugador = f"{j['numero']}  {j['nombre']}" if j["numero"] is not None else j["nombre"]
            celda = QTableWidgetItem(nombre_jugador)
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

        raiz = QVBoxLayout(self)
        raiz.addWidget(QLabel(nombre, objectName="seccion"))
        raiz.addWidget(
            QLabel(
                "Haz clic en la celda del partido al que vino cada jugador; otro clic la desmarca. "
                "Pasa el mouse por el encabezado para ver la fecha y el rival de cada partido.",
                objectName="ayuda", wordWrap=True,
            )
        )
        raiz.addWidget(self.rejilla, 1)
        raiz.addWidget(botones_dialogo(self, self._aceptar, "Guardar lista"))

    def marcado(self, fila: int, columna: int) -> bool:
        return bool(self.rejilla.item(fila, columna).data(Qt.ItemDataRole.UserRole))

    def _poner(self, fila: int, columna: int, valor: bool):
        celda = self.rejilla.item(fila, columna)
        celda.setData(Qt.ItemDataRole.UserRole, valor)
        celda.setText(self.MARCA if valor else "")
        celda.setBackground(QColor(colores.VERDE_SUAVE) if valor else QColor(0, 0, 0, 0))
        celda.setForeground(QColor(colores.VERDE_ACTIVO))
        celda.setFont(self._fuente_marca())
        celda.setData(Qt.ItemDataRole.AccessibleTextRole, "vino" if valor else "no vino")

    def _fuente_marca(self):
        fuente = self.rejilla.font()
        fuente.setBold(True)
        return fuente

    def alternar(self, fila: int, columna: int):
        if fila < 0 or not 1 <= columna <= len(self.partidos):
            return
        self._poner(fila, columna, not self.marcado(fila, columna))
        self._contar(fila)

    def _contar(self, fila: int):
        vino = sum(self.marcado(fila, c) for c in range(1, len(self.partidos) + 1))
        self.rejilla.item(fila, len(self.partidos) + 1).setText(str(vino))

    def _aceptar(self):
        marcas = {p.id: set() for p in self.partidos}
        for r, j in enumerate(self.jugadores):
            for c, p in enumerate(self.partidos, start=1):
                if self.marcado(r, c):
                    marcas[p.id].add(j["id"])
        try:
            asistencia.guardar_de_equipo(self.conn, self.equipo_id, marcas)
        except ValueError as exc:
            error(self, str(exc))
            return
        self.accept()


def expedientes(conn, equipo_ids) -> dict[int, sqlite3.Row]:
    """Por equipo: jugadores, cuántos con foto, con CURP, con número y con todo completo."""
    ids = list(equipo_ids)
    if not ids:
        return {}
    marcas = ",".join("?" * len(ids))
    return {
        f["equipo_id"]: f
        for f in conn.execute(
            f"""SELECT equipo_id, COUNT(*) AS total, SUM(foto <> '') AS con_foto, SUM(curp <> '') AS con_curp,
                       SUM(numero IS NOT NULL) AS con_numero,
                       SUM(foto <> '' AND curp <> '' AND numero IS NOT NULL) AS completos
                FROM jugadores WHERE equipo_id IN ({marcas}) GROUP BY equipo_id""",
            ids,
        )
    }


def porcentaje(resumen) -> int | None:
    """Porcentaje de jugadores con expediente completo; None si el equipo no tiene jugadores."""
    if resumen is None or not resumen["total"]:
        return None
    return round(100 * resumen["completos"] / resumen["total"])


def _chip_completo(texto: str):
    if texto == "100%":
        return CHIP_VERDE
    return CHIP_GRIS if texto in ("0%", "-") else CHIP_DORADO


class DatosEquipo(QFrame):
    """Los datos del equipo como vienen en la hoja de registro, cada uno en su lugar."""

    CAMPOS = [
        ("club", "Club"), ("categoria", "Categoría"), ("rama", "Rama"), ("telefono", "Teléfono"),
        ("responsable", "Entrenador"), ("asistente", "Asistente"), ("director", "Director general"),
        ("disponible", "Puede jugar"),
    ]

    def __init__(self):
        super().__init__(objectName="tarjeta")
        diseno.sombra(self)
        rejilla = QGridLayout(self)
        rejilla.setContentsMargins(16, 12, 16, 12)
        rejilla.setHorizontalSpacing(18)
        rejilla.setVerticalSpacing(8)
        self.valores: dict[str, QLabel] = {}
        for i, (clave, titulo) in enumerate(self.CAMPOS):
            caja = QVBoxLayout()
            caja.setSpacing(0)
            caja.addWidget(QLabel(titulo, objectName="datoTitulo"))
            valor = QLabel("-", objectName="datoValor")
            valor.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            valor.setAccessibleName(titulo)
            caja.addWidget(valor)
            self.valores[clave] = valor
            rejilla.addLayout(caja, i // 4, i % 4)
        for c in range(4):
            rejilla.setColumnStretch(c, 1)
        self.resumen = QLabel(objectName="datoValor")
        self.resumen.setAccessibleName("Resumen de expedientes")
        self.avance = QProgressBar(objectName="avance", textVisible=False, maximum=100)
        self.avance.setAccessibleName("Expedientes completos")
        self.avance_texto = QLabel(objectName="ayuda")
        resumen = QHBoxLayout()
        resumen.setSpacing(12)
        resumen.addWidget(self.resumen)
        resumen.addWidget(self.avance, 1)
        resumen.addWidget(self.avance_texto)
        rejilla.addLayout(resumen, 2, 0, 1, 4)

    def mostrar(self, conn, equipo_id):
        equipo = None
        if equipo_id is not None:
            equipo = conn.execute(
                """SELECT e.*, c.nombre AS categoria FROM equipos e JOIN categorias c ON c.id = e.categoria_id
                   WHERE e.id = ?""",
                (equipo_id,),
            ).fetchone()
        for clave, valor in self.valores.items():
            if equipo is None:
                texto = "-"
            elif clave == "club":
                texto = equipo["nombre"]
            elif clave == "disponible":
                texto = rol.resumen_disponibilidad(rol.disponibilidad_de_equipo(conn, equipo_id))
            elif clave == "rama":
                texto = equipo["rama"].capitalize()
            else:
                texto = equipo[clave]
            vacio = not texto or texto == "-"
            valor.setText("Sin dato" if vacio and equipo is not None else (texto or "-"))
            valor.setToolTip(texto or "")
            nombre = "datoVacio" if vacio else "datoValor"
            if valor.objectName() != nombre:
                valor.setObjectName(nombre)
                valor.style().unpolish(valor)
                valor.style().polish(valor)
        self._mostrar_resumen(expedientes(conn, [equipo_id]).get(equipo_id) if equipo is not None else None)

    def _mostrar_resumen(self, fila):
        total = fila["total"] if fila else 0
        if not total:
            self.resumen.setText("Sin jugadores todavía")
            self.avance.setValue(0)
            self.avance_texto.setText("")
            return
        jugadores = "jugador" if total == 1 else "jugadores"
        self.resumen.setText(f"{total} {jugadores} · {fila['con_foto']} con foto · {fila['con_curp']} con CURP")
        valor = porcentaje(fila)
        self.avance.setValue(valor)
        self.avance_texto.setText(f"{valor}% con expediente completo")
        self.avance.setToolTip(
            f"{fila['completos']} de {total} tienen foto, CURP y número. "
            f"Con número: {fila['con_numero']}."
        )


class DelegadoNumero(QStyledItemDelegate):
    """Edita el número de playera en la misma celda; `guardar(jugador_id, numero)` decide si vale."""

    def __init__(self, padre, guardar):
        super().__init__(padre)
        self.guardar = guardar

    def createEditor(self, padre, _opcion, _indice):  # noqa: N802 (nombre de Qt)
        control = QSpinBox(padre, minimum=-1, maximum=NUMERO_MAX, specialValueText="Sin número")
        control.setAccessibleName("Número de playera")
        return control

    def setEditorData(self, control, indice):  # noqa: N802
        texto = indice.data()
        control.setValue(int(texto) if texto and texto.isdigit() else -1)

    def setModelData(self, control, _modelo, indice):  # noqa: N802
        control.interpretText()
        numero = None if control.value() < 0 else control.value()
        jugador_id = indice.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        # La tabla se vuelve a llenar después de cerrar el editor, nunca mientras está abierto.
        QTimer.singleShot(0, lambda: self.guardar(jugador_id, numero))


class PaginaEquipos(QWidget):
    datos_cambiados = Signal()

    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn

        self.filtros = FiltrosLiga(conn, con_todas=True)
        self.liga, self.torneo, self.categoria = self.filtros.liga, self.filtros.torneo, self.filtros.categoria
        self.filtros.cambiado.connect(self.refrescar_equipos)

        excel_fila = diseno.FilaBotones()
        acciones = QPushButton("Acciones", objectName="mas")
        acciones.setIcon(diseno.icono("lista", colores.VERDE_ACTIVO, aire=6))
        acciones.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        acciones.setToolTip("Importar o exportar las hojas de registro de Excel y generar credenciales.")
        menu = QMenu(acciones)
        menu.setToolTipsVisible(True)
        importar = menu.addAction(diseno.icono("importar", colores.VERDE_ACTIVO), "Importar Excel...")
        importar.setToolTip("Registra equipos y jugadores desde las hojas de registro de los clubes, con sus fotos.")
        importar.triggered.connect(lambda: self.importar_excel())
        exportar = menu.addMenu(diseno.icono("exportar", colores.VERDE_ACTIVO), "Exportar Excel")
        exportar.addAction("Solo el equipo elegido...").triggered.connect(lambda: self.exportar_registro())
        exportar.addAction("Todos los equipos de la lista (un archivo por equipo)...").triggered.connect(
            lambda: self.exportar_todos()
        )
        menu.addSeparator()
        pdf = menu.addAction(diseno.icono("credencial", colores.VERDE_ACTIVO), "Credenciales PDF...")
        pdf.setToolTip("Credenciales del equipo elegido, listas para imprimir y recortar.")
        pdf.triggered.connect(lambda: self.generar_credenciales())
        acciones.setMenu(menu)
        self.boton_acciones = acciones
        excel_fila.addWidget(acciones)

        self.tabla_equipos = tabla(["Equipo", "Categoría", "Jug.", "%"], estirar=0)
        self.tabla_equipos.setIconSize(QSize(26, 26))
        chips_en(self.tabla_equipos, 3, _chip_completo, pequeno=True)
        self.tabla_equipos.horizontalHeaderItem(2).setToolTip("Jugadores registrados")
        self.tabla_equipos.horizontalHeaderItem(3).setToolTip(
            "Porcentaje de jugadores con expediente completo: foto, CURP y número"
        )
        self.tabla_jugadores = tabla(
            ["Foto", "Núm.", "Nombre completo", "Nacimiento", "CURP", "Asist.", "Avisos", ""], estirar=2
        )
        # Foto y avisos llevan icono en lugar de título: así esas columnas ocupan solo lo de su icono.
        for columna, icono, ayuda in (
            (0, "persona", "Foto"),
            (6, "aviso", "Avisos: rojo si no entra en su categoría; ámbar si le falta CURP, foto o número"),
        ):
            encabezado = self.tabla_jugadores.horizontalHeaderItem(columna)
            encabezado.setText("")
            encabezado.setIcon(diseno.icono(icono, colores.TEXTO_SUAVE, 14))
            encabezado.setToolTip(ayuda)
            encabezado.setData(Qt.ItemDataRole.AccessibleTextRole, ayuda)
        self.acciones_jugador = AccionesDeFila(self.tabla_jugadores, 7, [
            ("editar", "Editar jugador", self.editar_jugador, "secundario"),
            ("eliminar", "Eliminar jugador", self.borrar_jugador, "peligro"),
        ])
        menu_de_fila(self.tabla_jugadores, [
            ("Editar jugador", self.editar_jugador),
            ("Cambiar número", self._editar_numero),
            ("Eliminar jugador", self.borrar_jugador),
        ])
        self.tabla_jugadores.setIconSize(QSize(26, 26))
        self.tabla_jugadores.horizontalHeaderItem(5).setToolTip("Asistencias a los partidos con pase de lista")
        self.tabla_jugadores.horizontalHeaderItem(6).setToolTip(
            "Rojo: no entra en su categoría por año de nacimiento. Ámbar: le falta CURP, foto o número."
        )
        self.tabla_jugadores.setItemDelegateForColumn(1, DelegadoNumero(self.tabla_jugadores, self._cambiar_numero))
        self.tabla_equipos.itemSelectionChanged.connect(self.refrescar_jugadores)
        al_activar(self.tabla_equipos, self.editar_equipo)
        al_activar(self.tabla_jugadores, self.editar_jugador, self._doble_clic_jugador)
        poner_vacio(self.tabla_equipos, "No hay equipos en este torneo.")
        poner_vacio(self.tabla_jugadores, "Selecciona un equipo para ver sus jugadores.")
        self.busqueda = campo_busqueda(self.tabla_equipos, "Buscar equipo o jugador", self._buscar)
        excel_fila.addWidget(self.busqueda)
        self.solo_incompletos = QCheckBox("Solo incompletos")
        self.solo_incompletos.setToolTip("Muestra solo a los jugadores a los que les falta CURP, foto o número.")
        self.solo_incompletos.toggled.connect(self._filtrar_jugadores)
        excel_fila.addWidget(self.solo_incompletos)

        izquierda = QVBoxLayout()
        izquierda.addWidget(QLabel("Equipos", objectName="seccion"))
        izquierda.addWidget(self.tabla_equipos)
        fila = diseno.FilaBotones()
        editar = boton("Editar", self.editar_equipo, "secundario")
        editar.setToolTip("Editar los datos del equipo elegido")
        fila.addWidget(editar)
        fila.addWidget(
            boton_mas(
                "Más",
                [
                    ("Días y horas en que puede jugar", self.editar_disponibilidad),
                    ("Descargar plantilla de Excel vacía", self.descargar_plantilla),
                    ("Eliminar equipo", self.borrar_equipo),
                ],
            )
        )
        izquierda.addLayout(fila)

        self.datos_equipo = DatosEquipo()
        derecha = QVBoxLayout()
        derecha.addWidget(self.datos_equipo)
        derecha.addSpacing(6)
        derecha.addWidget(QLabel("Jugadores", objectName="seccion"))
        derecha.addWidget(self.tabla_jugadores, 1)
        fila = diseno.FilaBotones()
        fila.addWidget(boton("Agregar jugador", self.nuevo_jugador))
        lista = boton("Pase de lista", self.pase_de_lista, "secundario")
        lista.setToolTip("Asistencia de los jugadores del equipo en cada partido (J1, J2...).")
        fila.addWidget(lista)
        derecha.addLayout(fila)

        columnas = QHBoxLayout()
        columnas.setSpacing(14)
        columnas.addLayout(izquierda, 2)
        columnas.addLayout(derecha, 5)

        raiz = QVBoxLayout(self)
        raiz.addWidget(diseno.encabezado(
            "Equipos y jugadores",
            "Toca un equipo para ver sus datos y sus jugadores. Para registrar equipos completos de una vez, "
            "pulsa «Importar Excel» y elige las hojas de registro de los clubes.",
            [boton("Agregar equipo", self.nuevo_equipo)],
        ))
        raiz.addWidget(self.filtros)
        raiz.addLayout(excel_fila)
        raiz.addLayout(columnas, 1)
        self.refrescar()

    def _torneo_id(self):
        return self.torneo.currentData()

    def _liga_id(self):
        return self.liga.currentData()

    def _categorias(self):
        return self.conn.execute(
            "SELECT * FROM categorias WHERE liga_id = ? ORDER BY nombre COLLATE ES", (self._liga_id(),)
        ).fetchall()

    def refrescar(self):
        self.filtros.refrescar()

    def showEvent(self, evento):
        super().showEvent(evento)
        self.filtros.refrescar()

    def _equipos_con_jugador(self, texto: str) -> set:
        buscado = clave_orden(texto.strip())
        if not buscado:
            return set()
        filas = self.conn.execute(
            """SELECT j.equipo_id, j.nombre FROM jugadores j JOIN equipos e ON e.id = j.equipo_id
               WHERE e.torneo_id = ?""",
            (self._torneo_id(),),
        ).fetchall()
        return {f["equipo_id"] for f in filas if buscado in clave_orden(f["nombre"])}

    def _buscar(self, texto: str):
        """Busca en equipos y en sus jugadores; si nada está elegido, abre la primera coincidencia."""
        filtrar(self.tabla_equipos, texto, self._equipos_con_jugador(texto))
        if texto.strip() and id_seleccionado(self.tabla_equipos) is None:
            for r in range(self.tabla_equipos.rowCount()):
                if not self.tabla_equipos.isRowHidden(r):
                    self.tabla_equipos.selectRow(r)
                    break
        self._filtrar_jugadores()

    def _filtrar_jugadores(self):
        """Si el equipo coincide por nombre se ven todos; si no, solo los jugadores que coinciden."""
        texto = self.busqueda.text()
        fila = self.tabla_equipos.currentRow()
        celda = self.tabla_equipos.item(fila, 0) if fila >= 0 else None
        por_equipo = celda is not None and clave_orden(texto.strip()) in clave_orden(celda.text())
        filtrar(self.tabla_jugadores, "" if por_equipo else texto)
        if self.solo_incompletos.isChecked():
            avisos = getattr(self, "_avisos", {})
            for r in range(self.tabla_jugadores.rowCount()):
                jugador_id = self.tabla_jugadores.item(r, 0).data(Qt.ItemDataRole.UserRole)
                if not avisos.get(jugador_id, (None, []))[1]:
                    self.tabla_jugadores.setRowHidden(r, True)
            actualizar_vacio(self.tabla_jugadores)

    def refrescar_equipos(self):
        filas = self.conn.execute(
            """SELECT e.id, e.nombre, e.rama, c.nombre AS categoria, COUNT(j.id) AS total
               FROM equipos e JOIN categorias c ON c.id = e.categoria_id
               LEFT JOIN jugadores j ON j.equipo_id = e.id
               WHERE e.torneo_id = ? AND (? IS NULL OR e.categoria_id = ?)
               GROUP BY e.id ORDER BY c.nombre COLLATE ES, e.nombre COLLATE ES""",
            (self._torneo_id(), self.categoria.currentData(), self.categoria.currentData()),
        ).fetchall()
        resumen = expedientes(self.conn, (f["id"] for f in filas))
        llenar(
            self.tabla_equipos,
            [
                (
                    f["id"],
                    [
                        f["nombre"], f["categoria"], f["total"],
                        "-" if porcentaje(resumen.get(f["id"])) is None else f"{porcentaje(resumen[f['id']])}%",
                    ],
                )
                for f in filas
            ],
        )
        for r in range(self.tabla_equipos.rowCount()):
            celda = self.tabla_equipos.item(r, 0)
            celda.setIcon(QIcon(avatar(None, celda.text(), 26, VERDE)))
        # Con una categoría elegida, esa columna diría lo mismo en todos los renglones.
        self.tabla_equipos.setColumnHidden(1, self.categoria.currentData() is not None)
        poner_vacio(
            self.tabla_equipos,
            "No hay equipos en este torneo. Pulsa «Agregar equipo» o «Importar Excel»."
            if self._torneo_id()
            else "Primero crea un torneo en «Ligas y categorías».",
        )
        filtrar(self.tabla_equipos, self.busqueda.text(), self._equipos_con_jugador(self.busqueda.text()))
        if id_seleccionado(self.tabla_equipos) is None:
            # Con un equipo ya elegido, sus jugadores se ven de inmediato y los botones funcionan.
            for r in range(self.tabla_equipos.rowCount()):
                if not self.tabla_equipos.isRowHidden(r):
                    self.tabla_equipos.selectRow(r)
                    break
        self.refrescar_jugadores()

    def refrescar_jugadores(self):
        equipo_id = id_seleccionado(self.tabla_equipos)
        self.datos_equipo.mostrar(self.conn, equipo_id)
        filas = self.conn.execute(
            "SELECT * FROM jugadores WHERE equipo_id = ? ORDER BY numero IS NULL, numero, nombre COLLATE ES",
            (equipo_id,),
        ).fetchall()
        categoria = self._categoria_del_equipo(equipo_id) if equipo_id is not None else None
        asistencias, con_lista = (
            asistencia.resumen_de_equipo(self.conn, equipo_id) if equipo_id is not None else ({}, 0)
        )
        self._jugadores = {j["id"]: j for j in filas}
        self._avisos: dict[int, tuple[str | None, list[str]]] = {}
        for j in filas:
            fecha = date.fromisoformat(j["fecha_nacimiento"])
            fuera = motivo_no_elegible(fecha, categoria["anio_min"], categoria["anio_max"]) if categoria else None
            self._avisos[j["id"]] = (fuera, faltantes(j))
        llenar(
            self.tabla_jugadores,
            [
                (
                    j["id"],
                    [
                        "", j["numero"], j["nombre"],
                        date.fromisoformat(j["fecha_nacimiento"]).strftime("%d/%m/%Y"),
                        j["curp"] or "-",
                        f"{asistencias.get(j['id'], 0)} de {con_lista}" if con_lista else "-",
                        "",
                    ],
                )
                for j in filas
            ],
        )
        self._decorar_jugadores()
        self.acciones_jugador.colocar()
        poner_vacio(
            self.tabla_jugadores,
            "Este equipo no tiene jugadores. Pulsa «Agregar jugador» o importa su hoja de registro."
            if id_seleccionado(self.tabla_equipos)
            else "Selecciona un equipo para ver sus jugadores.",
        )
        self._filtrar_jugadores()

    def _decorar_jugadores(self):
        """Foto redonda, avisos del expediente y la marca roja de quien no entra en su categoría."""
        aviso_rojo = diseno.icono("aviso", colores.ROJO, 18)
        aviso_ambar = diseno.icono("aviso", colores.DORADO_TEXTO, 18)
        for r in range(self.tabla_jugadores.rowCount()):
            jugador_id = self.tabla_jugadores.item(r, 0).data(Qt.ItemDataRole.UserRole)
            j = self._jugadores[jugador_id]
            foto = self.tabla_jugadores.item(r, 0)
            foto.setIcon(QIcon(avatar(fotos_dir() / j["foto"] if j["foto"] else None, j["nombre"], 26, GRIS)))
            foto.setToolTip("Con foto" if j["foto"] else "Sin foto")
            numero = self.tabla_jugadores.item(r, 1)
            numero.setToolTip("Doble clic para cambiar el número")
            fuera, falta = self._avisos[jugador_id]
            avisos = self.tabla_jugadores.item(r, 6)
            partes = []
            if fuera:
                partes.append(fuera)
                nacimiento = self.tabla_jugadores.item(r, 3)
                nacimiento.setForeground(QColor(colores.ROJO))
                nacimiento.setToolTip(fuera)
            if falta:
                partes.append("Le falta: " + ", ".join(falta) + ".")
            if partes:
                avisos.setIcon(aviso_rojo if fuera else aviso_ambar)
                avisos.setToolTip("\n".join(partes))
                avisos.setData(Qt.ItemDataRole.AccessibleTextRole, " ".join(partes))
            else:
                avisos.setToolTip("Expediente completo")

    def _editar_numero(self):
        fila = self.tabla_jugadores.currentRow()
        if fila >= 0:
            self.tabla_jugadores.editItem(self.tabla_jugadores.item(fila, 1))

    def _doble_clic_jugador(self, indice):
        if indice.column() == 1:
            self.tabla_jugadores.editItem(self.tabla_jugadores.item(indice.row(), 1))
        else:
            self.editar_jugador()

    def _cambiar_numero(self, jugador_id, numero):
        jugador = self._jugadores.get(jugador_id)
        if jugador is None or jugador["numero"] == numero:
            self.refrescar_jugadores()
            return
        try:
            with self.conn:
                self.conn.execute("UPDATE jugadores SET numero = ? WHERE id = ?", (numero, jugador_id))
        except sqlite3.IntegrityError:
            self.refrescar_jugadores()
            error(self, f"El número {numero} ya lo tiene otro jugador de este equipo.")
            return
        self.refrescar_jugadores()
        listo(self, "número guardado.")

    def _avisar_cambio(self, mensaje: str = "cambios guardados."):
        self.refrescar_equipos()
        self.datos_cambiados.emit()
        listo(self, mensaje)

    def nuevo_equipo(self):
        if self._torneo_id() is None:
            error(self, "Primero crea un torneo para esta liga en «Ligas y categorías».")
            return
        categorias = self._categorias()
        if not categorias:
            error(self, "Primero crea una categoría para esta liga en «Ligas y categorías».")
            return
        dialogo = DialogoEquipo(self, categorias)
        if dialogo.exec():
            self._guardar_equipo(
                "INSERT INTO equipos (categoria_id, nombre, responsable, telefono, asistente, director, rama, "
                "torneo_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                dialogo, self._torneo_id(),
            )

    def editar_equipo(self):
        equipo_id = id_seleccionado(self.tabla_equipos)
        if equipo_id is None:
            error(self, "Primero selecciona un equipo.")
            return
        equipo = self.conn.execute("SELECT * FROM equipos WHERE id = ?", (equipo_id,)).fetchone()
        dialogo = DialogoEquipo(self, self._categorias(), equipo)
        if dialogo.exec():
            if dialogo.categoria.currentData() != equipo["categoria_id"] and self._tiene_partidos(equipo_id):
                error(self, "No se puede cambiar de categoría: el equipo ya tiene partidos en el rol.")
                return
            self._guardar_equipo(
                "UPDATE equipos SET categoria_id = ?, nombre = ?, responsable = ?, telefono = ?, "
                "asistente = ?, director = ?, rama = ? "
                "WHERE id = ?",
                dialogo, equipo_id,
            )

    def _guardar_equipo(self, sql, dialogo, ultimo):
        try:
            with self.conn:
                self.conn.execute(
                    sql,
                    (
                        dialogo.categoria.currentData(), dialogo.nombre.text().strip(),
                        dialogo.responsable.text().strip(), dialogo.telefono.text().strip(),
                        dialogo.asistente.text().strip(), dialogo.director.text().strip(),
                        dialogo.rama.currentData(), ultimo,
                    ),
                )
        except sqlite3.IntegrityError:
            error(self, "Ya existe un equipo con ese nombre en esa categoría.")
            return
        self._avisar_cambio("equipo guardado.")

    def editar_disponibilidad(self):
        equipo_id = id_seleccionado(self.tabla_equipos)
        if equipo_id is None:
            error(self, "Primero selecciona un equipo.")
            return
        nombre = self.tabla_equipos.item(self.tabla_equipos.currentRow(), 0).text()
        dialogo = DialogoDisponibilidad(self, nombre, rol.disponibilidad_de_equipo(self.conn, equipo_id))
        if dialogo.exec():
            rol.guardar_disponibilidad(self.conn, equipo_id, dialogo.valores())
            self._avisar_cambio("días y horas guardados.")

    def borrar_equipo(self):
        equipo_id = id_seleccionado(self.tabla_equipos)
        if equipo_id is None:
            error(self, "Primero selecciona un equipo.")
            return
        if self._tiene_partidos(equipo_id):
            error(
                self,
                "No se puede eliminar: el equipo tiene partidos en el rol. "
                "Elimina esos partidos o genera de nuevo el rol sin él.",
            )
            return
        if cobros.tiene_pagos(self.conn, equipo_id):
            error(self, "No se puede eliminar: el equipo tiene pagos registrados.")
            return
        if not confirmar(self, "¿Eliminar este equipo y todos sus jugadores?"):
            return
        fotos = self.conn.execute(
            "SELECT foto FROM jugadores WHERE equipo_id = ?", (equipo_id,)
        ).fetchall()
        with self.conn:
            self.conn.execute("DELETE FROM equipos WHERE id = ?", (equipo_id,))
        for f in fotos:
            borrar_foto(f["foto"], fotos_dir())
        self._avisar_cambio("equipo eliminado.")

    def _tiene_partidos(self, equipo_id) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM partidos WHERE local_id = ? OR visitante_id = ? "
                "UNION ALL SELECT 1 FROM llaves WHERE equipo_a_id = ? OR equipo_b_id = ? LIMIT 1",
                (equipo_id, equipo_id, equipo_id, equipo_id),
            ).fetchone()
            is not None
        )

    def _categoria_del_equipo(self, equipo_id):
        return self.conn.execute(
            "SELECT c.* FROM categorias c JOIN equipos e ON e.categoria_id = c.id WHERE e.id = ?",
            (equipo_id,),
        ).fetchone()

    def nuevo_jugador(self):
        equipo_id = id_seleccionado(self.tabla_equipos)
        if equipo_id is None:
            error(self, "Primero selecciona un equipo.")
            return
        dialogo = DialogoJugador(self, self._categoria_del_equipo(equipo_id))
        if dialogo.exec():
            self._guardar_jugador(dialogo, equipo_id, None)

    def editar_jugador(self):
        equipo_id = id_seleccionado(self.tabla_equipos)
        jugador_id = id_seleccionado(self.tabla_jugadores)
        if jugador_id is None:
            error(self, "Primero selecciona un jugador.")
            return
        jugador = self.conn.execute("SELECT * FROM jugadores WHERE id = ?", (jugador_id,)).fetchone()
        dialogo = DialogoJugador(self, self._categoria_del_equipo(equipo_id), jugador)
        if dialogo.exec():
            self._guardar_jugador(dialogo, equipo_id, jugador)

    def _guardar_jugador(self, dialogo, equipo_id, jugador):
        foto = jugador["foto"] if jugador else ""
        foto_nueva = None
        if dialogo.ruta_foto:
            try:
                foto_nueva = guardar_foto(dialogo.ruta_foto, fotos_dir())
            except ValueError as exc:
                error(self, str(exc))
                return
        datos = (
            dialogo.nombre.text().strip(), dialogo.fecha_nacimiento().isoformat(),
            dialogo.numero_playera(), dialogo.posicion.currentText(), foto_nueva or foto,
            dialogo.curp_limpia(),
        )
        try:
            with self.conn:
                if jugador:
                    self.conn.execute(
                        "UPDATE jugadores SET nombre = ?, fecha_nacimiento = ?, numero = ?, "
                        "posicion = ?, foto = ?, curp = ? WHERE id = ?",
                        (*datos, jugador["id"]),
                    )
                else:
                    self.conn.execute(
                        "INSERT INTO jugadores (nombre, fecha_nacimiento, numero, posicion, foto, "
                        "curp, equipo_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (*datos, equipo_id),
                    )
        except sqlite3.IntegrityError:
            if foto_nueva:
                borrar_foto(foto_nueva, fotos_dir())
            error(self, "Ese número de playera o ese jugador ya están registrados en el equipo.")
            return
        if foto_nueva and foto:
            borrar_foto(foto, fotos_dir())
        self._avisar_cambio("jugador guardado.")

    def borrar_jugador(self):
        jugador_id = id_seleccionado(self.tabla_jugadores)
        if jugador_id is None:
            error(self, "Primero selecciona un jugador.")
            return
        if self.conn.execute("SELECT 1 FROM goles WHERE jugador_id = ?", (jugador_id,)).fetchone():
            error(self, "No se puede eliminar: el jugador tiene goles registrados en un partido.")
            return
        if not confirmar(self, "¿Eliminar este jugador?"):
            return
        foto = self.conn.execute("SELECT foto FROM jugadores WHERE id = ?", (jugador_id,)).fetchone()
        with self.conn:
            self.conn.execute("DELETE FROM jugadores WHERE id = ?", (jugador_id,))
        borrar_foto(foto["foto"], fotos_dir())
        self._avisar_cambio("jugador eliminado.")

    def descargar_plantilla(self):
        if self._liga_id() is None:
            return
        sugerido = str(Path.home() / f"Plantilla jugadores - {self.liga.currentText()}.xlsx")
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar plantilla", sugerido, "Excel (*.xlsx)")
        if not ruta:
            return
        try:
            excel.crear_plantilla(self.conn, self._liga_id(), ruta)
        except PermissionError:
            error(self, "No se pudo guardar: el archivo está abierto en Excel.")
            return
        os.startfile(ruta)

    def importar_excel(self):
        if self._torneo_id() is None:
            error(self, "Primero crea un torneo para esta liga en «Ligas y categorías».")
            return
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Elige uno o varios archivos de Excel", str(Path.home()), "Excel (*.xlsx)"
        )
        if not rutas:
            return
        if all(registro.es_hoja_de_registro(r) for r in rutas):
            self._importar_registros(rutas)
        elif len(rutas) == 1:
            self._importar_plantilla(rutas[0])
        else:
            error(
                self,
                "Para importar varios archivos a la vez, todos deben ser hojas de registro de equipo "
                "(con «NOMBRE DEL CLUB» y «NOMBRE COMPLETO»). La plantilla del programa se importa sola.",
            )

    def _importar_registros(self, rutas: list[str]):
        try:
            registros = registro.leer(rutas)
        except ValueError as exc:
            error(self, str(exc))
            return
        registro.preparar(self.conn, registros, self._torneo_id())
        if not DialogoRegistros(self, self.conn, registros, self._torneo_id(), self._categorias()).exec():
            return
        nuevos, actualizados, equipos, categorias = registro.importar(
            self.conn, registros, self._torneo_id(), fotos_dir()
        )
        self._avisar_cambio("importación terminada.")
        lineas = [
            f"Importación terminada en el torneo «{self.torneo.currentText()}».", "",
            f"Equipos creados: {equipos}", f"Jugadores nuevos: {nuevos}",
            f"Jugadores actualizados: {actualizados}",
        ]
        if categorias:
            lineas.append(f"Categorías creadas: {categorias}")
        info(self, "\n".join(lineas))

    def _importar_plantilla(self, ruta: str):
        try:
            filas = excel.analizar(self.conn, ruta, self._torneo_id())
        except ValueError as exc:
            error(self, str(exc))
            return
        if not filas:
            error(self, "El archivo no tiene jugadores capturados.")
            return
        if not DialogoImportacion(self, filas).exec():
            return
        nuevos, actualizados, equipos = excel.importar(self.conn, filas, self._torneo_id(), fotos_dir())
        self._avisar_cambio("importación terminada.")
        info(
            self,
            f"Importación terminada en el torneo «{self.torneo.currentText()}».\n\n"
            f"Jugadores nuevos: {nuevos}\nJugadores actualizados: {actualizados}\n"
            f"Equipos creados: {equipos}",
        )

    def _equipo_elegido(self) -> tuple[int, str] | None:
        equipo_id = id_seleccionado(self.tabla_equipos)
        if equipo_id is None:
            error(self, "Primero toca un equipo de la lista.")
            return None
        return equipo_id, self.tabla_equipos.item(self.tabla_equipos.currentRow(), 0).text()

    def pase_de_lista(self):
        elegido = self._equipo_elegido()
        if elegido is None:
            return
        equipo_id, nombre = elegido
        if not asistencia.partidos_de_equipo(self.conn, equipo_id):
            error(self, f"«{nombre}» todavía no tiene partidos en el rol. El pase de lista es por partido.")
            return
        if self.tabla_jugadores.rowCount() == 0:
            error(self, "Este equipo todavía no tiene jugadores.")
            return
        if DialogoListaEquipo(self, self.conn, equipo_id, nombre).exec():
            self.refrescar_jugadores()
            listo(self, f"pase de lista de «{nombre}» guardado.")

    def exportar_registro(self):
        elegido = self._equipo_elegido()
        if elegido is None:
            return
        equipo_id, nombre = elegido
        sugerido = str(Path.home() / f"Registro {_nombre_archivo(nombre)}.xlsx")
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar hoja de registro", sugerido, "Excel (*.xlsx)")
        if not ruta:
            return
        try:
            registro.exportar(self.conn, equipo_id, ruta, fotos_dir())
        except PermissionError:
            error(self, "No se pudo guardar: el archivo está abierto en Excel. Ciérralo e inténtalo de nuevo.")
            return
        listo(self, f"hoja de registro de «{nombre}» guardada.")
        os.startfile(ruta)

    def exportar_todos(self):
        equipos = [
            (id_seleccionado_en(self.tabla_equipos, r), self.tabla_equipos.item(r, 0).text(),
             self.tabla_equipos.item(r, 1).text())
            for r in range(self.tabla_equipos.rowCount())
            if not self.tabla_equipos.isRowHidden(r)
        ]
        if not equipos:
            error(self, "No hay equipos en la lista para exportar.")
            return
        carpeta = QFileDialog.getExistingDirectory(self, "Elige la carpeta donde guardar los archivos", str(Path.home()))
        if not carpeta:
            return
        guardados, abiertos = 0, []
        for equipo_id, nombre, categoria in equipos:
            ruta = Path(carpeta) / f"Registro {_nombre_archivo(nombre)} - {_nombre_archivo(categoria)}.xlsx"
            try:
                registro.exportar(self.conn, equipo_id, ruta, fotos_dir())
                guardados += 1
            except PermissionError:
                abiertos.append(ruta.name)
        mensaje = f"Se guardaron {guardados} hojas de registro en:\n{carpeta}"
        if abiertos:
            mensaje += "\n\nNo se pudieron guardar porque están abiertas en Excel:\n" + "\n".join(abiertos)
        info(self, mensaje)
        os.startfile(carpeta)

    def generar_credenciales(self):
        equipo_id = id_seleccionado(self.tabla_equipos)
        if equipo_id is None:
            error(self, "Primero selecciona un equipo.")
            return
        if self.tabla_jugadores.rowCount() == 0:
            error(self, "Este equipo todavía no tiene jugadores.")
            return
        resumen = expedientes(self.conn, [equipo_id]).get(equipo_id)
        sin_foto, sin_curp = resumen["total"] - resumen["con_foto"], resumen["total"] - resumen["con_curp"]
        if sin_foto or sin_curp:
            faltan = []
            if sin_foto:
                faltan.append(_cuantos(sin_foto, "jugador no tiene foto", "jugadores no tienen foto"))
            if sin_curp:
                faltan.append(_cuantos(sin_curp, "jugador no tiene CURP", "jugadores no tienen CURP"))
            if not confirmar(
                self,
                " y ".join(faltan) + ". Sus credenciales saldrán con ese espacio vacío.\n\n"
                "¿Generar las credenciales de todos modos? Con «Solo incompletos» ves quiénes son.",
            ):
                return
        fila = self.tabla_equipos.currentRow()
        nombre = self.tabla_equipos.item(fila, 0).text()
        sugerido = str(Path.home() / f"Credenciales {_nombre_archivo(nombre)}.pdf")
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar credenciales", sugerido, "PDF (*.pdf)")
        if not ruta:
            return
        try:
            credenciales.generar(self.conn, equipo_id, ruta, fotos_dir())
        except PermissionError:
            error(self, "No se pudo guardar: el archivo está abierto en otro programa.")
            return
        os.startfile(ruta)


def _cuantos(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _nombre_archivo(texto: str) -> str:
    return "".join(c for c in texto if c not in '<>:"/\\|?*').strip()
