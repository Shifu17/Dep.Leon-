"""Página de equipos y jugadores, con importación desde Excel y credenciales."""

import os
import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import credenciales, excel
from ..jugadores import NUMERO_MAX, POSICIONES, borrar_foto, error_de_edad, guardar_foto
from ..paths import fotos_dir
from .comun import boton, botones_dialogo, confirmar, error, id_seleccionado, info, llenar, tabla


class DialogoEquipo(QDialog):
    def __init__(self, padre, categorias, equipo=None):
        super().__init__(padre)
        self.setWindowTitle("Equipo")
        self.categoria = QComboBox()
        for c in categorias:
            self.categoria.addItem(c["nombre"], c["id"])
        self.nombre = QLineEdit(equipo["nombre"] if equipo else "")
        self.responsable = QLineEdit(equipo["responsable"] if equipo else "")
        self.telefono = QLineEdit(equipo["telefono"] if equipo else "")
        if equipo:
            self.categoria.setCurrentIndex(self.categoria.findData(equipo["categoria_id"]))
        forma = QFormLayout(self)
        forma.addRow("Categoría:", self.categoria)
        forma.addRow("Nombre:", self.nombre)
        forma.addRow("Responsable:", self.responsable)
        forma.addRow("Teléfono:", self.telefono)
        forma.addRow(botones_dialogo(self, self._aceptar))

    def _aceptar(self):
        if not self.nombre.text().strip():
            error(self, "Escribe el nombre del equipo.")
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
        self.numero = QSpinBox(minimum=0, maximum=NUMERO_MAX)
        self.posicion = QComboBox()
        self.posicion.addItems([""] + POSICIONES)
        self.vista_foto = QLabel("Sin foto", alignment=Qt.AlignmentFlag.AlignCenter)
        self.vista_foto.setFixedSize(110, 130)
        self.vista_foto.setStyleSheet("background: white; border: 1px solid #CBD8D0;")
        if jugador:
            self.fecha.setDate(QDate.fromString(jugador["fecha_nacimiento"], "yyyy-MM-dd"))
            self.numero.setValue(jugador["numero"])
            self.posicion.setCurrentText(jugador["posicion"])
            if jugador["foto"]:
                self._mostrar_foto(fotos_dir() / jugador["foto"])

        forma = QFormLayout(self)
        forma.addRow("Nombre completo:", self.nombre)
        forma.addRow("Fecha de nacimiento:", self.fecha)
        forma.addRow("Número de playera:", self.numero)
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

    def _aceptar(self):
        if not self.nombre.text().strip():
            error(self, "Escribe el nombre del jugador.")
            return
        motivo = error_de_edad(
            self.fecha_nacimiento(), self.categoria["anio_min"], self.categoria["anio_max"]
        )
        if motivo:
            error(self, motivo)
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
                    vista.item(r, c).setForeground(QColor("#B3140C"))

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


class PaginaEquipos(QWidget):
    datos_cambiados = Signal()

    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn

        self.liga = QComboBox()
        self.torneo = QComboBox()
        self.categoria = QComboBox()
        self.liga.currentIndexChanged.connect(self._al_cambiar_liga)
        self.torneo.currentIndexChanged.connect(self.refrescar_equipos)
        self.categoria.currentIndexChanged.connect(self.refrescar_equipos)

        filtros = QHBoxLayout()
        for texto, control in (("Liga:", self.liga), ("Torneo:", self.torneo), ("Categoría:", self.categoria)):
            filtros.addWidget(QLabel(texto))
            filtros.addWidget(control, 1)

        excel_fila = QHBoxLayout()
        excel_fila.addWidget(boton("Descargar plantilla de Excel", self.descargar_plantilla, "secundario"))
        excel_fila.addWidget(boton("Importar Excel", self.importar_excel))
        excel_fila.addStretch(1)

        self.tabla_equipos = tabla(["Equipo", "Categoría", "Jugadores"], estirar=0)
        self.tabla_jugadores = tabla(["Núm.", "Jugador", "Nacimiento", "Posición", "Foto"], estirar=1)
        self.tabla_equipos.itemSelectionChanged.connect(self.refrescar_jugadores)

        izquierda = QVBoxLayout()
        izquierda.addWidget(QLabel("Equipos", objectName="seccion"))
        izquierda.addWidget(self.tabla_equipos)
        fila = QHBoxLayout()
        fila.addWidget(boton("Agregar", self.nuevo_equipo))
        fila.addWidget(boton("Editar", self.editar_equipo, "secundario"))
        fila.addWidget(boton("Eliminar", self.borrar_equipo, "peligro"))
        izquierda.addLayout(fila)

        derecha = QVBoxLayout()
        derecha.addWidget(QLabel("Jugadores del equipo", objectName="seccion"))
        derecha.addWidget(self.tabla_jugadores)
        fila = QHBoxLayout()
        fila.addWidget(boton("Agregar", self.nuevo_jugador))
        fila.addWidget(boton("Editar", self.editar_jugador, "secundario"))
        fila.addWidget(boton("Eliminar", self.borrar_jugador, "peligro"))
        fila.addStretch(1)
        fila.addWidget(boton("Credenciales PDF", self.generar_credenciales))
        derecha.addLayout(fila)

        columnas = QHBoxLayout()
        columnas.addLayout(izquierda, 2)
        columnas.addLayout(derecha, 3)

        raiz = QVBoxLayout(self)
        raiz.addWidget(QLabel("Equipos y jugadores", objectName="titulo"))
        raiz.addLayout(filtros)
        raiz.addLayout(excel_fila)
        raiz.addLayout(columnas)
        self.refrescar()

    def _torneo_id(self):
        return self.torneo.currentData()

    def _liga_id(self):
        return self.liga.currentData()

    def _categorias(self):
        return self.conn.execute(
            "SELECT * FROM categorias WHERE liga_id = ? ORDER BY nombre", (self._liga_id(),)
        ).fetchall()

    def refrescar(self):
        actual = self._liga_id()
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
        torneo_actual, categoria_actual = self.torneo.currentData(), self.categoria.currentData()
        for control in (self.torneo, self.categoria):
            control.blockSignals(True)
            control.clear()
        for t in self.conn.execute(
            "SELECT * FROM torneos WHERE liga_id = ? ORDER BY nombre", (self._liga_id(),)
        ):
            self.torneo.addItem(t["nombre"], t["id"])
        self.categoria.addItem("Todas", None)
        for c in self._categorias():
            self.categoria.addItem(c["nombre"], c["id"])
        self.torneo.setCurrentIndex(max(self.torneo.findData(torneo_actual), 0))
        self.categoria.setCurrentIndex(max(self.categoria.findData(categoria_actual), 0))
        for control in (self.torneo, self.categoria):
            control.blockSignals(False)
        self.refrescar_equipos()

    def refrescar_equipos(self):
        filas = self.conn.execute(
            """SELECT e.id, e.nombre, c.nombre AS categoria, COUNT(j.id) AS total
               FROM equipos e JOIN categorias c ON c.id = e.categoria_id
               LEFT JOIN jugadores j ON j.equipo_id = e.id
               WHERE e.torneo_id = ? AND (? IS NULL OR e.categoria_id = ?)
               GROUP BY e.id ORDER BY c.nombre, e.nombre""",
            (self._torneo_id(), self.categoria.currentData(), self.categoria.currentData()),
        )
        llenar(self.tabla_equipos, [(f["id"], [f["nombre"], f["categoria"], f["total"]]) for f in filas])
        self.refrescar_jugadores()

    def refrescar_jugadores(self):
        filas = self.conn.execute(
            "SELECT * FROM jugadores WHERE equipo_id = ? ORDER BY numero",
            (id_seleccionado(self.tabla_equipos),),
        )
        llenar(
            self.tabla_jugadores,
            [
                (
                    j["id"],
                    [
                        j["numero"], j["nombre"],
                        date.fromisoformat(j["fecha_nacimiento"]).strftime("%d/%m/%Y"),
                        j["posicion"], "Sí" if j["foto"] else "No",
                    ],
                )
                for j in filas
            ],
        )

    def _avisar_cambio(self):
        self.refrescar_equipos()
        self.datos_cambiados.emit()

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
                "INSERT INTO equipos (categoria_id, nombre, responsable, telefono, torneo_id) "
                "VALUES (?, ?, ?, ?, ?)",
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
                "UPDATE equipos SET categoria_id = ?, nombre = ?, responsable = ?, telefono = ? "
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
                        dialogo.responsable.text().strip(), dialogo.telefono.text().strip(), ultimo,
                    ),
                )
        except sqlite3.IntegrityError:
            error(self, "Ya existe un equipo con ese nombre en esa categoría.")
            return
        self._avisar_cambio()

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
        if not confirmar(self, "¿Eliminar este equipo y todos sus jugadores?"):
            return
        fotos = self.conn.execute(
            "SELECT foto FROM jugadores WHERE equipo_id = ?", (equipo_id,)
        ).fetchall()
        with self.conn:
            self.conn.execute("DELETE FROM equipos WHERE id = ?", (equipo_id,))
        for f in fotos:
            borrar_foto(f["foto"], fotos_dir())
        self._avisar_cambio()

    def _tiene_partidos(self, equipo_id) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM partidos WHERE local_id = ? OR visitante_id = ? LIMIT 1",
                (equipo_id, equipo_id),
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
            dialogo.numero.value(), dialogo.posicion.currentText(), foto_nueva or foto,
        )
        try:
            with self.conn:
                if jugador:
                    self.conn.execute(
                        "UPDATE jugadores SET nombre = ?, fecha_nacimiento = ?, numero = ?, "
                        "posicion = ?, foto = ? WHERE id = ?",
                        (*datos, jugador["id"]),
                    )
                else:
                    self.conn.execute(
                        "INSERT INTO jugadores (nombre, fecha_nacimiento, numero, posicion, foto, "
                        "equipo_id) VALUES (?, ?, ?, ?, ?, ?)",
                        (*datos, equipo_id),
                    )
        except sqlite3.IntegrityError:
            if foto_nueva:
                borrar_foto(foto_nueva, fotos_dir())
            error(self, "Ese número de playera o ese jugador ya están registrados en el equipo.")
            return
        if foto_nueva and foto:
            borrar_foto(foto, fotos_dir())
        self._avisar_cambio()

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
        self._avisar_cambio()

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
        ruta, _ = QFileDialog.getOpenFileName(self, "Importar jugadores", "", "Excel (*.xlsx)")
        if not ruta:
            return
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
        self._avisar_cambio()
        info(
            self,
            f"Importación terminada en el torneo «{self.torneo.currentText()}».\n\n"
            f"Jugadores nuevos: {nuevos}\nJugadores actualizados: {actualizados}\n"
            f"Equipos creados: {equipos}",
        )

    def generar_credenciales(self):
        equipo_id = id_seleccionado(self.tabla_equipos)
        if equipo_id is None:
            error(self, "Primero selecciona un equipo.")
            return
        if self.tabla_jugadores.rowCount() == 0:
            error(self, "Este equipo todavía no tiene jugadores.")
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


def _nombre_archivo(texto: str) -> str:
    return "".join(c for c in texto if c not in '<>:"/\\|?*').strip()
