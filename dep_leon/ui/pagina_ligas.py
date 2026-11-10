"""Página de ligas, categorías y torneos."""

import sqlite3
from datetime import date

from PySide6.QtCore import Qt, Signal
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

from .. import colores, rol
from ..jugadores import anios_del_nombre, encimadas, nombre_categoria, rango_anios
from . import campos, diseno
from .chips import ESTADO_TORNEO, MODALIDAD, NEUTRO, chips_en, separar_dias
from .comun import (
    al_activar,
    boton,
    boton_opciones,
    botones_dialogo,
    confirmar,
    error,
    fila_con_error,
    id_seleccionado,
    llenar,
    menu_de_fila,
    poner_vacio,
    tabla,
)



class DialogoLiga(QDialog):
    def __init__(self, padre, liga=None):
        super().__init__(padre)
        self.setWindowTitle("Liga")
        self.nombre = QLineEdit(liga["nombre"] if liga else "")
        self.modalidad = QComboBox()
        self.modalidad.addItems(rol.MODALIDADES_LIGA)
        self.dias = QLineEdit(liga["dias"] if liga else "")
        self.dias.setPlaceholderText("Ejemplo: Viernes y sábado")
        campos.solo_nombre_de_equipo(self.nombre, "Ejemplo: Libre Martes")
        campos.solo_dias(self.dias)
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
    def __init__(self, padre, categoria=None, modalidad_liga: str = "Fut 7"):
        super().__init__(padre)
        self.setWindowTitle("Categoría")
        self.modalidad = QComboBox()
        self.modalidad.addItem(f"Igual que la liga ({modalidad_liga})", "")
        for modalidad in rol.MODALIDADES:
            self.modalidad.addItem(modalidad, modalidad)
        if categoria is not None:
            self.modalidad.setCurrentIndex(max(0, self.modalidad.findData(categoria["modalidad"])))
        hoy = date.today().year
        self.nombre = QLineEdit(categoria["nombre"] if categoria else "")
        self.nombre.setPlaceholderText("Ejemplo: 2015-2016 o Libre")
        campos.solo_categoria(self.nombre)
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
        self.nombre.editingFinished.connect(self._completar_desde_nombre)
        forma = QFormLayout(self)
        self.error_nombre = fila_con_error(forma, "Nombre:", self.nombre)
        forma.addRow("Se juega en:", self.modalidad)
        forma.addRow("", QLabel("Fut 7 y Fut 8 usan la Cancha 1 o la 2; Fut 9 y Fut 11, la cancha completa.",
                                objectName="ayuda", wordWrap=True))
        forma.addRow(self.sin_limite)
        forma.addRow("Nacidos desde:", self.anio_min)
        self.error_anios = fila_con_error(forma, "Nacidos hasta:", self.anio_max)
        forma.addRow(botones_dialogo(self, self._aceptar))
        self._actualizar()

    def _completar_desde_nombre(self):
        """«2009-10» queda como «2009-2010» y, si el nombre son años, se ponen solos abajo."""
        nombre = nombre_categoria(self.nombre.text())
        if nombre != self.nombre.text():
            self.nombre.setText(nombre)
        anios = anios_del_nombre(nombre)
        if anios and not self.sin_limite.isChecked():
            self.anio_min.setValue(anios[0])
            self.anio_max.setValue(anios[1])

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

    def modalidad_elegida(self) -> str:
        return self.modalidad.currentData()

    def valores(self):
        nombre = nombre_categoria(self.nombre.text())
        if self.sin_limite.isChecked():
            return nombre, None, None
        return nombre, self.anio_min.value(), self.anio_max.value()


class DialogoTorneo(QDialog):
    def __init__(self, padre, torneo=None):
        super().__init__(padre)
        self.setWindowTitle("Torneo")
        self.nombre = QLineEdit(torneo["nombre"] if torneo else "")
        self.nombre.setPlaceholderText("Ejemplo: 2026-2027")
        campos.solo_temporada(self.nombre)
        self.temporada = ""
        forma = QFormLayout(self)
        self.error_nombre = fila_con_error(forma, "Temporada:", self.nombre)
        forma.addRow(QLabel("Todos los torneos se escriben igual, con los dos años: 2026-2027.",
                            objectName="ayuda", wordWrap=True))
        forma.addRow(botones_dialogo(self, self._aceptar))

    def _aceptar(self):
        try:
            self.temporada = rol.nombre_torneo(self.nombre.text())
        except ValueError as exc:
            self.error_nombre.mostrar(str(exc))
            return
        self.nombre.setText(self.temporada)
        self.accept()


class PaginaLigas(QWidget):
    datos_cambiados = Signal()

    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn

        self.tabla_ligas = tabla(["Liga", "Modalidad", "Días", "Categorías", "Equipos"], estirar=2)
        self.tabla_ligas.setWordWrap(False)
        chips_en(self.tabla_ligas, 1, lambda texto: MODALIDAD.get(texto, NEUTRO))
        chips_en(self.tabla_ligas, 2, separar=separar_dias, pequeno=True)
        self.tabla_categorias = tabla(["Categoría", "Nacidos", "Juego"], estirar=0)
        chips_en(self.tabla_categorias, 2, lambda texto: MODALIDAD.get(texto, NEUTRO), pequeno=True)
        self.tabla_categorias.horizontalHeaderItem(2).setToolTip("Modalidad en que juega la categoría")
        self.tabla_torneos = tabla(["Temporada", "Estado"], estirar=0)
        chips_en(self.tabla_torneos, 1, lambda texto: ESTADO_TORNEO.get(texto, NEUTRO), pequeno=True)
        self.tabla_torneos.setToolTip(
            "Próximo: aún sin resultados. Activo: ya hay resultados y faltan partidos. "
            "Finalizado: ya se jugaron todos."
        )
        self.tabla_ligas.itemSelectionChanged.connect(self.refrescar_detalle)
        al_activar(self.tabla_ligas, self.editar_liga)
        al_activar(self.tabla_categorias, self.editar_categoria)
        al_activar(self.tabla_torneos, self.editar_torneo)
        menu_de_fila(self.tabla_ligas, [("Editar liga", self.editar_liga), ("Eliminar liga", self.borrar_liga)])
        menu_de_fila(self.tabla_categorias, [
            ("Editar categoría", self.editar_categoria), ("Eliminar categoría", self.borrar_categoria),
        ])
        menu_de_fila(self.tabla_torneos, [("Editar torneo", self.editar_torneo), ("Eliminar torneo", self.borrar_torneo)])
        poner_vacio(self.tabla_categorias, "Esta liga no tiene categorías.", self.nueva_categoria, "Agregar categoría")
        poner_vacio(self.tabla_torneos, "Esta liga no tiene torneos.", self.nuevo_torneo, "Agregar torneo")

        self.titulo_categorias = QLabel("Categorías", objectName="seccion")
        self.titulo_torneos = QLabel("Torneos", objectName="seccion")

        ligas = QVBoxLayout()
        ligas.addWidget(QLabel("Ligas", objectName="seccion"))
        ligas.addWidget(self.tabla_ligas)
        fila = diseno.FilaBotones()
        fila.addWidget(boton("Agregar liga", self.nueva_liga))
        fila.addWidget(boton("Editar", self.editar_liga, "secundario"))
        fila.addWidget(boton("Eliminar", self.borrar_liga, "peligro"))
        ligas.addLayout(fila)

        columnas = QHBoxLayout()
        columnas.setSpacing(14)
        columnas.addLayout(ligas, 7)
        columnas.addLayout(self._columna(
            self.titulo_categorias, self.tabla_categorias, "Agregar", self.nueva_categoria,
            [("Editar categoría", self.editar_categoria), ("Eliminar categoría", self.borrar_categoria)],
            "la categoría",
        ), 4)
        columnas.addLayout(self._columna(
            self.titulo_torneos, self.tabla_torneos, "Agregar", self.nuevo_torneo,
            [("Editar torneo", self.editar_torneo), ("Eliminar torneo", self.borrar_torneo)],
            "el torneo",
        ), 2)

        raiz = QVBoxLayout(self)
        raiz.addWidget(diseno.encabezado(
            "Ligas, categorías y torneos",
            "Toca una liga para ver sus categorías y torneos. Para editar o eliminar, usa el botón «Más» "
            "o el clic derecho sobre la fila.",
        ))
        raiz.addLayout(columnas)
        self.refrescar()
        self.tabla_ligas.selectRow(0)

    def _columna(self, titulo: QLabel, tabla_, texto_agregar, agregar, opciones, de: str):
        columna = QVBoxLayout()
        columna.addWidget(titulo)
        columna.addWidget(tabla_)
        fila = QHBoxLayout()
        fila.setSpacing(8)
        fila.addWidget(boton(texto_agregar, agregar), 1)
        fila.addWidget(boton_opciones(opciones, de))
        columna.addLayout(fila)
        return columna

    def refrescar(self):
        llenar(
            self.tabla_ligas,
            [
                (l["id"], [l["nombre"], l["modalidad"], l["dias"], l["categorias"], l["equipos"]])
                for l in rol.ordenar_ligas(self.conn.execute(
                    """SELECT l.*,
                              (SELECT COUNT(*) FROM categorias c WHERE c.liga_id = l.id) AS categorias,
                              (SELECT COUNT(*) FROM equipos e JOIN torneos t ON t.id = e.torneo_id
                               WHERE t.liga_id = l.id) AS equipos
                       FROM ligas l"""
                ).fetchall())
            ],
        )
        self.refrescar_detalle()

    def refrescar_detalle(self):
        liga_id = id_seleccionado(self.tabla_ligas)
        liga = self.conn.execute("SELECT nombre, modalidad FROM ligas WHERE id = ?", (liga_id,)).fetchone()
        self.titulo_categorias.setText(f"Categorías de {liga['nombre']}" if liga else "Categorías")
        self.titulo_torneos.setText(f"Torneos de {liga['nombre']}" if liga else "Torneos")
        categorias = self.conn.execute(
            "SELECT * FROM categorias WHERE liga_id = ? ORDER BY nombre COLLATE ES", (liga_id,)
        ).fetchall()
        llenar(
            self.tabla_categorias,
            [(c["id"], [c["nombre"], _rango(c), c["modalidad"] or liga["modalidad"]]) for c in categorias],
        )
        self._marcar_encimadas(categorias)
        torneos = self.conn.execute(
            "SELECT * FROM torneos WHERE liga_id = ? ORDER BY nombre COLLATE ES", (liga_id,)
        )
        llenar(self.tabla_torneos, [(t["id"], [t["nombre"], rol.estado_torneo(self.conn, t["id"])]) for t in torneos])

    def _marcar_encimadas(self, categorias):
        """Un aviso en las categorías que comparten años: un jugador cabría en las dos."""
        cruces = encimadas(categorias)
        aviso = diseno.icono("aviso", colores.DORADO_TEXTO, 16)
        for r in range(self.tabla_categorias.rowCount()):
            celda = self.tabla_categorias.item(r, 1)
            otras = cruces.get(self.tabla_categorias.item(r, 0).data(Qt.ItemDataRole.UserRole))
            if otras:
                celda.setIcon(aviso)
                celda.setToolTip("Comparte años con " + ", ".join(otras) + ". Un jugador cabría en las dos.")

    def _aviso_encimada(self, liga_id, nombre, anio_min, anio_max, sin_id=None) -> bool:
        """Antes de guardar: si la categoría comparte años con otra, pregunta. True para seguir."""
        if anio_min is None or anio_max is None:
            return True
        otras = [
            c for c in self.conn.execute("SELECT * FROM categorias WHERE liga_id = ?", (liga_id,))
            if c["id"] != sin_id
        ]
        cruces = encimadas([*otras, {"id": -1, "nombre": nombre, "anio_min": anio_min, "anio_max": anio_max}])
        if -1 not in cruces:
            return True
        return confirmar(
            self,
            f"«{nombre}» comparte años con " + ", ".join(cruces[-1]) + ". Un jugador cabría en las dos "
            "categorías.\n\n¿Guardarla de todos modos?",
        )

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
        liga = self.conn.execute("SELECT modalidad FROM ligas WHERE id = ?", (liga_id,)).fetchone()
        dialogo = DialogoCategoria(self, modalidad_liga=liga["modalidad"])
        if dialogo.exec() and self._aviso_encimada(liga_id, *dialogo.valores()):
            self._guardar(
                "INSERT INTO categorias (nombre, anio_min, anio_max, modalidad, liga_id) VALUES (?, ?, ?, ?, ?)",
                (*dialogo.valores(), dialogo.modalidad_elegida(), liga_id), "Ya existe esa categoría en esta liga.",
            )

    def editar_categoria(self):
        categoria_id = id_seleccionado(self.tabla_categorias)
        if categoria_id is None:
            error(self, "Primero selecciona una categoría.")
            return
        categoria = self.conn.execute(
            "SELECT * FROM categorias WHERE id = ?", (categoria_id,)
        ).fetchone()
        liga = self.conn.execute("SELECT modalidad FROM ligas WHERE id = ?", (categoria["liga_id"],)).fetchone()
        dialogo = DialogoCategoria(self, categoria, liga["modalidad"])
        if dialogo.exec() and self._aviso_encimada(categoria["liga_id"], *dialogo.valores(), sin_id=categoria_id):
            self._guardar(
                "UPDATE categorias SET nombre = ?, anio_min = ?, anio_max = ?, modalidad = ? WHERE id = ?",
                (*dialogo.valores(), dialogo.modalidad_elegida(), categoria_id), "Ya existe esa categoría en esta liga.",
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
                (dialogo.temporada, liga_id), "Ya existe ese torneo en esta liga.",
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
                (dialogo.temporada, torneo_id), "Ya existe ese torneo en esta liga.",
            )

    def borrar_torneo(self):
        torneo_id = id_seleccionado(self.tabla_torneos)
        if torneo_id is None:
            error(self, "Primero selecciona un torneo.")
        elif confirmar(self, "¿Eliminar este torneo?"):
            self._borrar("torneos", torneo_id, "No se puede eliminar: el torneo tiene equipos.")


def _rango(categoria) -> str:
    return rango_anios(categoria["anio_min"], categoria["anio_max"])
