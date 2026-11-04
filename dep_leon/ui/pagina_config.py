"""Página de respaldos y actualizaciones."""

import sqlite3
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import __version__, db
from ..paths import fotos_dir
from .comun import boton, confirmar, error, info


class PaginaConfig(QWidget):
    datos_cambiados = Signal()
    buscar_actualizacion = Signal()

    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn

        raiz = QVBoxLayout(self)
        raiz.addWidget(QLabel("Configuración", objectName="titulo"))

        raiz.addWidget(QLabel("Respaldo de la información", objectName="seccion"))
        raiz.addWidget(
            QLabel(
                "El respaldo guarda en un archivo todas las ligas, los equipos, los jugadores y sus "
                "fotos. Guárdalo también fuera de esta computadora, como en una USB.",
                objectName="ayuda", wordWrap=True,
            )
        )
        fila = QHBoxLayout()
        fila.addWidget(boton("Crear respaldo", self.crear_respaldo))
        fila.addWidget(boton("Restaurar respaldo", self.restaurar_respaldo, "peligro"))
        fila.addStretch(1)
        raiz.addLayout(fila)
        raiz.addSpacing(18)

        raiz.addWidget(QLabel("Actualizaciones", objectName="seccion"))
        raiz.addWidget(QLabel(f"Versión instalada: {__version__}"))
        raiz.addWidget(
            QLabel(
                "Con internet, el programa revisa si hay una versión nueva y te avisa; solo se instala "
                "si aceptas. Sin internet sigue funcionando normalmente.",
                objectName="ayuda", wordWrap=True,
            )
        )
        fila = QHBoxLayout()
        fila.addWidget(boton("Buscar actualizaciones", self.buscar_actualizacion.emit, "secundario"))
        fila.addStretch(1)
        raiz.addLayout(fila)
        raiz.addStretch(1)

    def crear_respaldo(self):
        nombre = f"Respaldo Deportivo Leon {datetime.now():%Y-%m-%d %H%M}.zip"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar respaldo", str(Path.home() / nombre), "Respaldo (*.zip)"
        )
        if not ruta:
            return
        try:
            db.respaldar(self.conn, ruta, fotos_dir())
        except OSError as exc:
            error(self, f"No se pudo crear el respaldo: {exc}")
            return
        info(self, "Respaldo creado.")

    def restaurar_respaldo(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Restaurar respaldo", "", "Respaldo (*.zip)")
        if not ruta:
            return
        if not confirmar(self, "Esto reemplaza toda la información actual por la del respaldo. ¿Continuar?"):
            return
        try:
            db.restaurar(self.conn, ruta, fotos_dir())
        except (ValueError, OSError) as exc:
            error(self, str(exc))
            return
        self.datos_cambiados.emit()
        info(self, "Respaldo restaurado.")
