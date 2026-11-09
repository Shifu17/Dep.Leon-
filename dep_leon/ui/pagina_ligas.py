"""Página de ligas, categorías y torneos."""

import sqlite3
from datetime import date

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .comun import (
    al_activar,
    boton,
    botones_dialogo,
    confirmar,
    error,
    fila_con_error,
    id_seleccionado,
    llenar,
    poner_vacio,
    tabla,
)

MODALIDADES = ["Fut 7", "Fut 11"]


class DialogoLiga(QDialog):
    def __init__(self, padre, liga=None):
        super().__init__(padre)
        self.setWindowTitle("Liga")
        self.nombre = QLineEdit(liga["nombre"] if liga else "")
        self.modalidad = QComboBox()
        self.modalidad.addItems(MODALIDADES)
        self.dias = QLineEdit(liga["dias"] if liga else "")
        self.dias.setPlaceholderText("Ejemplo: Viernes y sábado")
        if liga:
            self.modalidad.setCurrentText(liga["modalidad"])
        forma = QFormLayout(self)
        self.error_nombre = fila_con_error(forma, "Nombre:", self.nombre)
        forma.addRow("Modalidad:", self.modalidad)
        forma.addRow("Días de juego:", self.dias)
        forma.addRow(botones_dialogo(self, self._aceptar))

    def _aceptar(self):
        if not self.nombre.text().strip():
            self.error_nombre.mostrar("Escribe el nombre de la liga.")
            return
        self.accept()

    def valores(self):
        return self.nombre.text().strip(), self.modalidad.currentText(), self.dias.text().strip()


class DialogoCategoria(QDialog):
    def __init__(self, padre, categoria=None):
        super().__init__(padre)
        self.setWindowTitle("Categoría")
        hoy = date.today().year
        self.nombre = QLineEdit(categoria["nombre"] if categoria else "")
        self.nombre.setPlaceholderText("Ejemplo: 2015-2016 o Libre")
        self.sin_limite = QCheckBox("Sin límite de edad (categoría libre)")
        self.anio_min = QSpinBox(minimum=1940, maximum=hoy, value=hoy - 10)
        self.anio_max = QSpinBox(minimum=1940, maximum=hoy, value=hoy - 10)
        if categoria:
            libre = categoria["anio_min"] is None and categoria["anio_max"] is None
            self.sin_limite.setChecked(libre)
            if categoria["anio_min"] is not None:
                self.anio_min.setValue(categoria["anio_min"])
            if categoria["anio_max"] is not None:
                self.anio_max.setValue(categoria["anio_max"])
        self.sin_limite.toggled.connect(self._actualizar)
        forma = QFormLayout(self)
        self.error_nombre = fila_con_error(forma, "Nombre:", self.nombre)
        forma.addRow(self.sin_limite)
        forma.addRow("Nacidos desde:", self.anio_min)
        self.error_anios = fila_con_error(forma, "Nacidos hasta:", self.anio_max)
        forma.addRow(botones_dialogo(self, self._aceptar))
        self._actualizar()

    def _actualizar(self):
        activo = not self.sin_limite.isChecked()
        self.anio_min.setEnabled(activo)
        self.anio_max.setEnabled(activo)

    def _aceptar(self):
        if not self.nombre.text().strip():
            self.error_nombre.mostrar("Escribe el nombre de la categoría.")
            return
        if not self.sin_limite.isChecked() and self.anio_min.value() > self.anio_max.value():
            self.error_anios.mostrar("El año «desde» no puede ser mayor que el año «hasta».")
            return
        self.accept()

    def valores(self):
        if self.sin_limite.isChecked():
            return self.nombre.text().strip(), None, None
        return self.nombre.text().strip(), self.anio_min.value(), self.anio_max.value()


class DialogoTorneo(QDialog):
    def __init__(self, padre, torneo=None):
        super().__init__(padre)
        self.setWindowTitle("Torneo")
        self.nombre = QLineEdit(torneo["nombre"] if torneo else "")
        self.nombre.setPlaceholderText("Ejemplo: Copa de Verano")
        forma = QFormLayout(self)
        self.error_nombre = fila_con_error(forma, "Nombre:", self.nombre)
        forma.addRow(botones_dialogo(self, self._aceptar))

    def _aceptar(self):
        if not self.nombre.text().strip():
            self.error_nombre.mostrar("Escribe el nombre del torneo.")
            return
        self.accept()


class PaginaLigas(QWidget):
    datos_cambiados = Signal()

    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn

        self.tabla_ligas = tabla(["Liga", "Modalidad", "Días"], estirar=2)
        self.tabla_ligas.setWordWrap(False)
        self.tabla_categorias = tabla(["Categoría", "Años de nacimiento"], estirar=0)
        self.tabla_torneos = tabla(["Torneo"])
        self.tabla_ligas.itemSelectionChanged.connect(self.refrescar_detalle)
        al_activar(self.tabla_ligas, self.editar_liga)
        al_activar(self.tabla_categorias, self.editar_categoria)
        al_activar(self.tabla_torneos, self.editar_torneo)
        poner_vacio(self.tabla_categorias, "Esta liga no tiene categorías. Pulsa «Agregar» debajo de esta lista.")
        poner_vacio(self.tabla_torneos, "Esta liga no tiene torneos. Pulsa «Agregar» para crear uno.")

        columnas = QHBoxLayout()
        columnas.addLayout(
            self._columna("Ligas", self.tabla_ligas, self.nueva_liga, self.editar_liga, self.borrar_liga), 4
        )
        columnas.addLayout(
            self._columna(
                "Categorías", self.tabla_categorias,
                self.nueva_categoria, self.editar_categoria, self.borrar_categoria,
            ), 2,
        )
        columnas.addLayout(
            self._columna(
                "Torneos", self.tabla_torneos,
                self.nuevo_torneo, self.editar_torneo, self.borrar_torneo,
            ), 2,
        )

        titulo = QLabel("Ligas, categorías y torneos", objectName="titulo")
        ayuda = QLabel("Selecciona una liga para ver y editar sus categorías y torneos.", objectName="ayudaPagina")
        raiz = QVBoxLayout(self)
        raiz.addWidget(titulo)
        raiz.addWidget(ayuda)
        raiz.addLayout(columnas)
        self.refrescar()
        self.tabla_ligas.selectRow(0)

    def _columna(self, titulo, tabla_, nuevo, editar, borrar):
        columna = QVBoxLayout()
        columna.addWidget(QLabel(titulo, objectName="seccion"))
        columna.addWidget(tabla_)
        fila = QHBoxLayout()
        fila.addWidget(boton("Agregar", nuevo))
        fila.addWidget(boton("Editar", editar, "secundario"))
        fila.addWidget(boton("Eliminar", borrar, "peligro"))
        columna.addLayout(fila)
        return columna

    def refrescar(self):
        llenar(
            self.tabla_ligas,
            [
                (l["id"], [l["nombre"], l["modalidad"], l["dias"]])
                for l in self.conn.execute("SELECT * FROM ligas ORDER BY id")
            ],
        )
        self.refrescar_detalle()

    def refrescar_detalle(self):
        liga_id = id_seleccionado(self.tabla_ligas)
        categorias = self.conn.execute(
            "SELECT * FROM categorias WHERE liga_id = ? ORDER BY nombre COLLATE ES", (liga_id,)
        )
        llenar(
            self.tabla_categorias,
            [(c["id"], [c["nombre"], _rango(c)]) for c in categorias],
        )
        torneos = self.conn.execute(
            "SELECT * FROM torneos WHERE liga_id = ? ORDER BY nombre COLLATE ES", (liga_id,)
        )
        llenar(self.tabla_torneos, [(t["id"], [t["nombre"]]) for t in torneos])

    def _guardar(self, sql, parametros, duplicado) -> bool:
        try:
            with self.conn:
                self.conn.execute(sql, parametros)
        except sqlite3.IntegrityError:
            error(self, duplicado)
            return False
        self.refrescar()
        self.datos_cambiados.emit()
        return True

    def _borrar(self, tabla_sql, identificador, en_uso):
        try:
            with self.conn:
                self.conn.execute(f"DELETE FROM {tabla_sql} WHERE id = ?", (identificador,))
        except sqlite3.IntegrityError:
            error(self, en_uso)
            return
        self.refrescar()
        self.datos_cambiados.emit()

    def _liga_actual(self):
        liga_id = id_seleccionado(self.tabla_ligas)
        if liga_id is None:
            error(self, "Primero selecciona una liga.")
        return liga_id

    def nueva_liga(self):
        dialogo = DialogoLiga(self)
        if dialogo.exec():
            self._guardar(
                "INSERT INTO ligas (nombre, modalidad, dias) VALUES (?, ?, ?)",
                dialogo.valores(), "Ya existe una liga con ese nombre.",
            )

    def editar_liga(self):
        liga_id = self._liga_actual()
        if liga_id is None:
            return
        liga = self.conn.execute("SELECT * FROM ligas WHERE id = ?", (liga_id,)).fetchone()
        dialogo = DialogoLiga(self, liga)
        if dialogo.exec():
            self._guardar(
                "UPDATE ligas SET nombre = ?, modalidad = ?, dias = ? WHERE id = ?",
                (*dialogo.valores(), liga_id), "Ya existe una liga con ese nombre.",
            )

    def borrar_liga(self):
        liga_id = self._liga_actual()
        if liga_id is not None and confirmar(self, "¿Eliminar esta liga?"):
            self._borrar("ligas", liga_id, "No se puede eliminar: la liga tiene categorías o torneos.")

    def nueva_categoria(self):
        liga_id = self._liga_actual()
        if liga_id is None:
            return
        dialogo = DialogoCategoria(self)
        if dialogo.exec():
            self._guardar(
                "INSERT INTO categorias (nombre, anio_min, anio_max, liga_id) VALUES (?, ?, ?, ?)",
                (*dialogo.valores(), liga_id), "Ya existe esa categoría en esta liga.",
            )

    def editar_categoria(self):
        categoria_id = id_seleccionado(self.tabla_categorias)
        if categoria_id is None:
            error(self, "Primero selecciona una categoría.")
            return
        categoria = self.conn.execute(
            "SELECT * FROM categorias WHERE id = ?", (categoria_id,)
        ).fetchone()
        dialogo = DialogoCategoria(self, categoria)
        if dialogo.exec():
            self._guardar(
                "UPDATE categorias SET nombre = ?, anio_min = ?, anio_max = ? WHERE id = ?",
                (*dialogo.valores(), categoria_id), "Ya existe esa categoría en esta liga.",
            )

    def borrar_categoria(self):
        categoria_id = id_seleccionado(self.tabla_categorias)
        if categoria_id is None:
            error(self, "Primero selecciona una categoría.")
        elif confirmar(self, "¿Eliminar esta categoría?"):
            self._borrar("categorias", categoria_id, "No se puede eliminar: la categoría tiene equipos.")

    def nuevo_torneo(self):
        liga_id = self._liga_actual()
        if liga_id is None:
            return
        dialogo = DialogoTorneo(self)
        if dialogo.exec():
            self._guardar(
                "INSERT INTO torneos (nombre, liga_id) VALUES (?, ?)",
                (dialogo.nombre.text().strip(), liga_id), "Ya existe ese torneo en esta liga.",
            )

    def editar_torneo(self):
        torneo_id = id_seleccionado(self.tabla_torneos)
        if torneo_id is None:
            error(self, "Primero selecciona un torneo.")
            return
        torneo = self.conn.execute("SELECT * FROM torneos WHERE id = ?", (torneo_id,)).fetchone()
        dialogo = DialogoTorneo(self, torneo)
        if dialogo.exec():
            self._guardar(
                "UPDATE torneos SET nombre = ? WHERE id = ?",
                (dialogo.nombre.text().strip(), torneo_id), "Ya existe ese torneo en esta liga.",
            )

    def borrar_torneo(self):
        torneo_id = id_seleccionado(self.tabla_torneos)
        if torneo_id is None:
            error(self, "Primero selecciona un torneo.")
        elif confirmar(self, "¿Eliminar este torneo?"):
            self._borrar("torneos", torneo_id, "No se puede eliminar: el torneo tiene equipos.")


def _rango(categoria) -> str:
    if categoria["anio_min"] is None and categoria["anio_max"] is None:
        return "Sin límite"
    return f"{categoria['anio_min']} a {categoria['anio_max']}"
