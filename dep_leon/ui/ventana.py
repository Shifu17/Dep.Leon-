"""Ventana principal, con encabezado, navegación y aviso de actualizaciones."""

import sqlite3
import threading
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, db, updater
from ..paths import asset, data_dir, fotos_dir
from .acceso import pedir_acceso
from .comun import error, info
from .pagina_cobros import PaginaCobros
from .pagina_config import PaginaConfig
from .pagina_equipos import PaginaEquipos
from .pagina_estadisticas import PaginaEstadisticas
from .pagina_inicio import PaginaInicio
from .pagina_ligas import PaginaLigas
from .pagina_liguilla import PaginaLiguilla
from .pagina_resultados import PaginaResultados
from .pagina_rol import PaginaRol

ANCHO_BARRA = 220
MINUTOS_ENTRE_REVISIONES = 30
ETAPAS_PENDIENTES = ["Reportes"]


class _Senales(QObject):
    encontrada = Signal(object, bool)
    sin_novedad = Signal(bool)
    sin_conexion = Signal(bool)
    descargada = Signal(object)
    descarga_fallida = Signal(str)


class Ventana(QMainWindow):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setWindowTitle(f"Deportivo León - v{__version__}")
        self.setWindowIcon(QIcon(str(asset("icono.ico"))))
        self.resize(1200, 760)
        self.conn = conn
        self._avisada: str | None = None
        self._progreso: QProgressDialog | None = None

        self.pila = QStackedWidget()
        self.inicio = PaginaInicio(conn)
        self.ligas = PaginaLigas(conn)
        self.equipos = PaginaEquipos(conn)
        self.rol = PaginaRol(conn)
        self.resultados = PaginaResultados(conn)
        self.estadisticas = PaginaEstadisticas(conn)
        self.liguilla = PaginaLiguilla(conn)
        self.cobros = PaginaCobros(conn)
        self.config = PaginaConfig(conn)
        self.ligas.datos_cambiados.connect(self.equipos.refrescar)
        self.ligas.datos_cambiados.connect(self.rol.refrescar)
        self.equipos.datos_cambiados.connect(self.rol.refrescar)
        self.config.datos_cambiados.connect(self.ligas.refrescar)
        self.config.datos_cambiados.connect(self.equipos.refrescar)
        self.config.datos_cambiados.connect(self.rol.refrescar)
        self.config.buscar_actualizacion.connect(lambda: self.revisar_actualizacion(manual=True))
        self.config.cerrar_sesion.connect(self.cerrar_sesion)

        contenido = QWidget(objectName="contenido")
        cuerpo = QHBoxLayout(contenido)
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        cuerpo.addWidget(self._crear_barra())
        margen = QVBoxLayout()
        margen.setContentsMargins(12, 10, 12, 10)
        margen.addWidget(self.pila)
        cuerpo.addLayout(margen, 1)
        self.setCentralWidget(contenido)

        self.senales = _Senales()
        self.senales.encontrada.connect(self._al_encontrar)
        self.senales.sin_novedad.connect(self._al_no_haber_novedad)
        self.senales.sin_conexion.connect(self._al_no_haber_conexion)
        self.senales.descargada.connect(self._al_descargar)
        self.senales.descarga_fallida.connect(self._al_fallar_descarga)

        # Sin internet solo se reintenta en silencio más tarde.
        self.temporizador = QTimer(self, interval=MINUTOS_ENTRE_REVISIONES * 60 * 1000)
        self.temporizador.timeout.connect(self.revisar_actualizacion)
        self.temporizador.start()
        QTimer.singleShot(1500, self.revisar_actualizacion)

    def _crear_barra(self) -> QWidget:
        barra = QWidget(objectName="barra")
        barra.setFixedWidth(ANCHO_BARRA)
        columna = QVBoxLayout(barra)
        columna.setContentsMargins(0, 14, 0, 8)
        columna.setSpacing(0)
        grupo = QButtonGroup(self, exclusive=True)

        logo = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(
            QPixmap(str(asset("logo.png"))).scaledToWidth(
                ANCHO_BARRA - 28, Qt.TransformationMode.SmoothTransformation
            )
        )
        columna.addWidget(logo)
        columna.addSpacing(14)

        def agregar(texto: str, pagina: QWidget):
            self.pila.addWidget(pagina)
            nav = QPushButton(texto, objectName="nav", checkable=True)
            nav.clicked.connect(lambda: self.pila.setCurrentWidget(pagina))
            grupo.addButton(nav)
            columna.addWidget(nav)
            return nav

        agregar("Inicio", self.inicio).click()
        agregar("Ligas y categorías", self.ligas)
        agregar("Equipos y jugadores", self.equipos)
        agregar("Rol de juegos", self.rol)
        agregar("Resultados", self.resultados)
        agregar("Estadísticas", self.estadisticas)
        agregar("Liguilla", self.liguilla)
        agregar("Cobros", self.cobros)
        for texto in ETAPAS_PENDIENTES:
            pendiente = QPushButton(texto, objectName="nav", enabled=False)
            pendiente.setToolTip("Disponible en una próxima etapa")
            columna.addWidget(pendiente)
        columna.addStretch(1)
        agregar("Configuración", self.config)
        return barra

    def cerrar_sesion(self):
        """Oculta todo hasta volver a iniciar sesión; si se cancela, cierra el programa."""
        app = QApplication.instance()
        app.setQuitOnLastWindowClosed(False)
        self.temporizador.stop()
        self.hide()
        if pedir_acceso(self.conn):
            self.show()
            self.temporizador.start()
            app.setQuitOnLastWindowClosed(True)
        else:
            app.quit()

    def revisar_actualizacion(self, manual: bool = False):
        def trabajo():
            try:
                encontrada = updater.buscar(__version__)
            except updater.SinConexion:
                self.senales.sin_conexion.emit(manual)
                return
            if encontrada:
                self.senales.encontrada.emit(encontrada, manual)
            else:
                self.senales.sin_novedad.emit(manual)

        threading.Thread(target=trabajo, daemon=True).start()

    def _al_no_haber_conexion(self, manual: bool):
        if manual:
            error(self, "No hay conexión a internet. Inténtalo más tarde.")

    def _al_no_haber_novedad(self, manual: bool):
        if manual:
            info(self, f"Ya tienes la versión más reciente ({__version__}).")

    def _al_encontrar(self, actualizacion: updater.Actualizacion, manual: bool):
        # Con la sesión cerrada no se muestra nada; se avisará en la siguiente revisión.
        if not self.isVisible() or (self._avisada == actualizacion.version and not manual):
            return
        self._avisada = actualizacion.version
        caja = QMessageBox(self)
        caja.setIcon(QMessageBox.Icon.Information)
        caja.setWindowTitle("Actualización disponible")
        caja.setText(
            f"Hay una versión nueva: {actualizacion.version}\nTu versión: {__version__}"
        )
        if actualizacion.notas:
            caja.setInformativeText(actualizacion.notas[:800])
        ahora = caja.addButton("Actualizar ahora", QMessageBox.ButtonRole.AcceptRole)
        caja.addButton("Después", QMessageBox.ButtonRole.RejectRole)
        caja.exec()
        if caja.clickedButton() is not ahora:
            return
        if not updater.puede_instalar():
            info(self, "La instalación automática solo funciona en el programa instalado (.exe).")
            return
        self._descargar(actualizacion)

    def _descargar(self, actualizacion: updater.Actualizacion):
        self._progreso = QProgressDialog("Descargando actualización...", "", 0, 0, self)
        self._progreso.setCancelButton(None)
        self._progreso.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._progreso.show()

        def trabajo():
            try:
                self.senales.descargada.emit(updater.descargar(actualizacion))
            except updater.SinConexion:
                self.senales.descarga_fallida.emit(
                    "Se perdió la conexión. La actualización se intentará más tarde."
                )
            except (ValueError, OSError) as exc:
                self.senales.descarga_fallida.emit(str(exc))

        threading.Thread(target=trabajo, daemon=True).start()

    def _cerrar_progreso(self):
        if self._progreso:
            self._progreso.close()
            self._progreso = None

    def _al_fallar_descarga(self, mensaje: str):
        self._cerrar_progreso()
        self._avisada = None
        error(self, mensaje)

    def _al_descargar(self, ruta):
        self._cerrar_progreso()
        try:
            carpeta = data_dir() / "respaldos"
            carpeta.mkdir(exist_ok=True)
            db.respaldar(
                self.conn, carpeta / f"antes de actualizar {datetime.now():%Y-%m-%d %H%M}.zip", fotos_dir()
            )
        except OSError as exc:
            error(self, f"No se actualizó porque no se pudo crear el respaldo previo: {exc}")
            return
        updater.instalar_y_cerrar(ruta)
        QApplication.quit()
