"""Página de reportes: vista previa, PDF e imagen para WhatsApp."""

import os
import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import lienzo, reportes
from .comun import boton, error, etiqueta, info
from .filtros import FiltrosLiga

ROL = "Rol de juegos"
TABLA = "Tabla de posiciones"
GOLEADORES = "Goleadores y portería"
ADEUDOS = "Adeudos"
LLAVE = "Llave de liguilla"
CON_IMAGEN = (ROL, TABLA, LLAVE)  # los demás solo van en PDF; los adeudos no son para compartir


class PaginaReportes(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn
        self.hoja = None

        self.filtros = FiltrosLiga(conn, con_todas=True)
        self.filtros.cambiado.connect(self._al_cambiar_filtros)

        self.reporte = QComboBox()
        self.reporte.addItems([ROL, TABLA, GOLEADORES, ADEUDOS, LLAVE])
        self.reporte.currentIndexChanged.connect(self._al_cambiar_filtros)
        self.fecha = QComboBox()
        self.fecha.currentIndexChanged.connect(self.actualizar_vista)
        self.etiqueta_fecha = etiqueta("Fecha:", self.fecha)

        self.boton_pdf = boton("Guardar PDF", self.guardar_pdf)
        self.boton_imagen = boton("Guardar imagen", self.guardar_imagen, "secundario")
        self.boton_copiar: QPushButton = boton("Copiar imagen", self.copiar_imagen, "secundario")

        fila = QHBoxLayout()
        fila.addWidget(etiqueta("Reporte:", self.reporte))
        fila.addWidget(self.reporte)
        fila.addWidget(self.etiqueta_fecha)
        fila.addWidget(self.fecha)
        fila.addStretch(1)
        fila.addWidget(self.boton_pdf)
        fila.addWidget(self.boton_imagen)
        fila.addWidget(self.boton_copiar)

        self.aviso = QLabel(objectName="ayuda", wordWrap=True)
        self.vista = QLabel(alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        contenedor = QWidget(objectName="lienzoLlave")
        columna = QVBoxLayout(contenedor)
        columna.addWidget(self.vista)
        columna.addStretch(1)
        self.area = QScrollArea(frameShape=QFrame.Shape.NoFrame)
        self.area.setWidgetResizable(True)
        self.area.setWidget(contenedor)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(QLabel("Reportes", objectName="titulo"))
        raiz.addWidget(self.filtros)
        raiz.addLayout(fila)
        raiz.addWidget(self.aviso)
        raiz.addWidget(self.area, 1)
        self._al_cambiar_filtros()

    def showEvent(self, evento):
        super().showEvent(evento)
        self.filtros.refrescar()

    def _al_cambiar_filtros(self):
        es_rol = self.reporte.currentText() == ROL
        self.etiqueta_fecha.setVisible(es_rol)
        self.fecha.setVisible(es_rol)
        actual = self.fecha.currentData()
        self.fecha.blockSignals(True)
        self.fecha.clear()
        self.fecha.addItem("Todas", None)
        torneo = self.filtros.torneo_id
        if torneo is not None:
            for f in reportes.fechas_de_rol(self.conn, torneo, self.filtros.categoria_id):
                self.fecha.addItem(date.fromisoformat(f).strftime("%d/%m/%Y"), f)
        self.fecha.setCurrentIndex(max(self.fecha.findData(actual), 0))
        self.fecha.blockSignals(False)
        self.actualizar_vista()

    def _construir(self):
        """Devuelve (hoja, motivo si no se puede mostrar)."""
        torneo, categoria = self.filtros.torneo_id, self.filtros.categoria_id
        if torneo is None:
            return None, "Primero crea un torneo para esta liga en «Ligas y categorías»."
        tipo = self.reporte.currentText()
        if tipo == LLAVE and categoria is None:
            return None, "Elige una categoría para ver su llave."
        if tipo == ROL:
            hoja = reportes.hoja_rol(self.conn, torneo, categoria, self.fecha.currentData())
        elif tipo == TABLA:
            hoja = reportes.hoja_tabla(self.conn, torneo, categoria)
        elif tipo == GOLEADORES:
            hoja = reportes.hoja_goleadores(self.conn, torneo, categoria)
        elif tipo == ADEUDOS:
            hoja = reportes.hoja_adeudos(self.conn, torneo, categoria)
        else:
            hoja = reportes.hoja_llave(self.conn, torneo, categoria)
        if hoja.vacia:
            return None, "Todavía no hay datos para este reporte."
        return hoja, ""

    def actualizar_vista(self):
        self.hoja, motivo = self._construir()
        hay = self.hoja is not None
        con_imagen = hay and self.reporte.currentText() in CON_IMAGEN
        self.boton_pdf.setEnabled(hay)
        self.boton_imagen.setEnabled(con_imagen)
        self.boton_copiar.setEnabled(con_imagen)
        self.aviso.setText(motivo)
        self.aviso.setVisible(bool(motivo))
        if not hay:
            self.vista.clear()
            return
        imagen = lienzo.a_imagen(self.hoja).scaledToWidth(
            760, Qt.TransformationMode.SmoothTransformation
        )
        self.vista.setPixmap(QPixmap.fromImage(imagen))

    def _sugerido(self, extension: str) -> str:
        partes = [self.reporte.currentText(), self.filtros.torneo.currentText()]
        if self.filtros.categoria_id is not None:
            partes.append(self.filtros.categoria.currentText())
        if self.reporte.currentText() == ROL and self.fecha.currentData():
            partes.append(self.fecha.currentData())
        return str(Path.home() / f"{reportes.nombre_archivo(' - '.join(partes))}.{extension}")

    def guardar_pdf(self):
        if self.hoja is None:
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar PDF", self._sugerido("pdf"), "PDF (*.pdf)")
        if not ruta:
            return
        try:
            lienzo.guardar_pdf(self.hoja, ruta)
        except OSError as exc:
            error(self, str(exc))
            return
        os.startfile(ruta)

    def guardar_imagen(self):
        if self.hoja is None:
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar imagen", self._sugerido("png"), "Imagen (*.png)")
        if not ruta:
            return
        try:
            lienzo.guardar_imagen(self.hoja, ruta)
        except OSError as exc:
            error(self, str(exc))
            return
        os.startfile(ruta)

    def copiar_imagen(self):
        if self.hoja is None:
            return
        QGuiApplication.clipboard().setImage(lienzo.a_imagen(self.hoja))
        info(self, "Imagen copiada. Ya puedes pegarla en WhatsApp.")
