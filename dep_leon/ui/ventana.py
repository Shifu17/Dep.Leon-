"""Ventana principal, con encabezado, navegación y aviso de actualizaciones."""

import sqlite3
import threading
from datetime import datetime

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
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
from . import diseno
from .comun import error, info, logo
from .pagina_cobros import PaginaCobros
from .pagina_config import PaginaConfig
from .pagina_equipos import PaginaEquipos
from .pagina_estadisticas import PaginaEstadisticas
from .pagina_inicio import PaginaInicio
from .pagina_ligas import PaginaLigas
from .pagina_liguilla import PaginaLiguilla
from .pagina_reportes import PaginaReportes
from .pagina_resultados import VER_POR_CAPTURAR, PaginaResultados
from .pagina_rol import PaginaRol
from .tema import ESCALA_TEXTO

ANCHO_BARRA = round(220 * min(ESCALA_TEXTO, 1.5))  # crece con el texto para no cortar el menú
ALTO_LOGO = 200  # el escudo es vertical: se limita su alto para que la navegación quepa
ALTO_LOGO_COMPACTO = 160  # en pantallas bajas, como las laptops de 768 px
TAMANO_PREFERIDO = (1200, 760)
MINUTOS_ENTRE_REVISIONES = 30


class _Senales(QObject):
    encontrada = Signal(object, bool)
    sin_novedad = Signal(bool)
    sin_conexion = Signal(bool)
    avance = Signal(int, int)
    descargada = Signal(object)
    descarga_fallida = Signal(str)
    descarga_cancelada = Signal()


class Ventana(QMainWindow):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setWindowTitle(f"Deportivo León - v{__version__}")
        self.setWindowIcon(QIcon(str(asset("icono.ico"))))
        self._ajustar_a_pantalla()
        self.conn = conn
        self._avisada: str | None = None
        self._progreso: QProgressDialog | None = None
        self._seleccion: tuple | None = None  # liga, torneo y categoría elegidas por la persona
        self._navegacion: dict[QWidget, QPushButton] = {}

        self.pila = QStackedWidget()
        self.inicio = PaginaInicio(conn)
        self.ligas = PaginaLigas(conn)
        self.equipos = PaginaEquipos(conn)
        self.rol = PaginaRol(conn)
        self.resultados = PaginaResultados(conn)
        self.estadisticas = PaginaEstadisticas(conn)
        self.liguilla = PaginaLiguilla(conn)
        self.cobros = PaginaCobros(conn)
        self.reportes = PaginaReportes(conn)
        self.config = PaginaConfig(conn)
        self.ligas.datos_cambiados.connect(self.equipos.refrescar)
        self.ligas.datos_cambiados.connect(self.rol.refrescar)
        self.equipos.datos_cambiados.connect(self.rol.refrescar)
        self.config.datos_cambiados.connect(self.ligas.refrescar)
        self.config.datos_cambiados.connect(self.equipos.refrescar)
        self.config.datos_cambiados.connect(self.rol.refrescar)
        self.config.buscar_actualizacion.connect(lambda: self.revisar_actualizacion(manual=True))
        self.config.cerrar_sesion.connect(self.cerrar_sesion)
        self.inicio.ir_a.connect(self._ir_a)
        for pagina in (self.equipos, self.rol, self.resultados, self.estadisticas, self.liguilla, self.cobros, self.reportes):
            pagina.filtros.elegido.connect(lambda p=pagina: self._recordar_seleccion(p))

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
        contenido.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        contenido.setFocus()

        self.senales = _Senales()
        self.senales.encontrada.connect(self._al_encontrar)
        self.senales.sin_novedad.connect(self._al_no_haber_novedad)
        self.senales.sin_conexion.connect(self._al_no_haber_conexion)
        self.senales.avance.connect(self._al_avanzar)
        self.senales.descargada.connect(self._al_descargar)
        self.senales.descarga_cancelada.connect(self._al_cancelar_descarga)
        self.senales.descarga_fallida.connect(self._al_fallar_descarga)

        # Sin internet solo se reintenta en silencio más tarde.
        self.temporizador = QTimer(self, interval=MINUTOS_ENTRE_REVISIONES * 60 * 1000)
        self.temporizador.timeout.connect(self.revisar_actualizacion)
        self.temporizador.start()
        QTimer.singleShot(1500, self.revisar_actualizacion)
        if updater.puede_instalar():
            threading.Thread(target=updater.limpiar_restos, daemon=True).start()

    def _ajustar_a_pantalla(self):
        """Abre en el tamaño preferido sin pasar del área libre de la pantalla (sin barra de tareas)."""
        pantalla = QGuiApplication.primaryScreen()
        if pantalla is None:
            self.resize(*TAMANO_PREFERIDO)
            return
        libre = pantalla.availableGeometry()
        # El marco de la ventana (título y bordes) también ocupa lugar.
        ancho = min(TAMANO_PREFERIDO[0], libre.width() - 16)
        alto = min(TAMANO_PREFERIDO[1], libre.height() - 48)
        self.resize(ancho, alto)
        self.move(libre.x() + (libre.width() - ancho) // 2, libre.y() + max(0, (libre.height() - alto - 32) // 2))

    def _crear_barra(self) -> QWidget:
        barra = QWidget(objectName="barra")
        barra.setFixedWidth(ANCHO_BARRA)
        columna = QVBoxLayout(barra)
        columna.setContentsMargins(0, 14, 0, 8)
        columna.setSpacing(0)
        grupo = QButtonGroup(self, exclusive=True)

        pantalla = QGuiApplication.primaryScreen()
        baja = pantalla is not None and pantalla.availableGeometry().height() < 820
        columna.addWidget(logo(ANCHO_BARRA - 28, ALTO_LOGO_COMPACTO if baja else ALTO_LOGO))
        columna.addSpacing(14)

        def agregar(texto: str, pagina: QWidget, icono: str):
            self.pila.addWidget(pagina)
            nav = QPushButton(texto, objectName="nav", checkable=True)
            nav.setIcon(diseno.icono_navegacion(icono))
            nav.setIconSize(QSize(26, 18))
            nav.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            nav.clicked.connect(lambda: self._mostrar(pagina))
            atajo = str((len(self._navegacion) + 1) % 10)
            nav.setToolTip(f"Ctrl+{atajo}")
            QShortcut(QKeySequence(f"Ctrl+{atajo}"), self).activated.connect(nav.click)
            self._navegacion[pagina] = nav
            grupo.addButton(nav)
            columna.addWidget(nav)
            return nav

        agregar("Inicio", self.inicio, "inicio").click()
        agregar("Ligas y categorías", self.ligas, "ligas")
        agregar("Equipos y jugadores", self.equipos, "equipos")
        agregar("Rol de juegos", self.rol, "rol")
        agregar("Resultados", self.resultados, "resultados")
        agregar("Estadísticas", self.estadisticas, "estadisticas")
        agregar("Liguilla", self.liguilla, "liguilla")
        agregar("Cobros", self.cobros, "cobros")
        agregar("Reportes", self.reportes, "reportes")
        columna.addStretch(1)
        agregar("Configuración", self.config, "configuracion")
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._enfocar_busqueda)
        QShortcut(QKeySequence("F5"), self).activated.connect(self._refrescar_pagina)
        return barra

    def _recordar_seleccion(self, pagina: QWidget):
        self._seleccion = pagina.filtros.seleccion()

    def _mostrar(self, pagina: QWidget):
        # Inicio y Ligas tienen su propia vista; las demás conservan lo elegido por la persona.
        if self._seleccion and hasattr(pagina, "filtros"):
            pagina.filtros.aplicar(*self._seleccion)
        self.pila.setCurrentWidget(pagina)

    def _ir_a(self, destino: str, liga_id, torneo_id):
        pagina = {
            "ligas": self.ligas, "equipos": self.equipos, "rol": self.rol,
            "resultados": self.resultados, "cobros": self.cobros,
        }[destino]
        if liga_id is not None:
            self._seleccion = (liga_id, torneo_id, None)
        if destino == "resultados":
            self.resultados.ver.setCurrentText(VER_POR_CAPTURAR)
        self._navegacion[pagina].click()
        if destino == "rol":
            self.rol.fecha.setCurrentIndex(0)  # los partidos sin fecha solo aparecen en «Todas»

    def _enfocar_busqueda(self):
        campo = getattr(self.pila.currentWidget(), "busqueda", None)
        if campo:
            campo.setFocus()
            campo.selectAll()

    def _refrescar_pagina(self):
        pagina = self.pila.currentWidget()
        if hasattr(pagina, "filtros"):
            pagina.filtros.refrescar()
        elif hasattr(pagina, "refrescar"):
            pagina.refrescar()

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
        self._cancelar_descarga = threading.Event()
        self._progreso = QProgressDialog("Conectando...", "Cancelar", 0, 100, self)
        self._progreso.setWindowTitle("Actualización")
        self._progreso.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._progreso.setMinimumDuration(0)
        self._progreso.setAutoClose(False)
        self._progreso.setAutoReset(False)
        self._progreso.setValue(0)
        self._progreso.canceled.connect(self._cancelar_descarga.set)
        self._progreso.show()
        cancelar = self._cancelar_descarga

        def trabajo():
            try:
                ruta = updater.descargar(actualizacion, self.senales.avance.emit, cancelar)
                self.senales.descargada.emit(ruta)
            except updater.Cancelada:
                self.senales.descarga_cancelada.emit()
            except updater.SinConexion:
                self.senales.descarga_fallida.emit(
                    "Se perdió la conexión durante la descarga. Inténtalo de nuevo más tarde."
                )
            except (ValueError, OSError) as exc:
                self.senales.descarga_fallida.emit(str(exc))

        threading.Thread(target=trabajo, daemon=True).start()

    def _al_avanzar(self, recibido: int, total: int):
        if not self._progreso:
            return
        mb = 1024 * 1024
        if total:
            self._progreso.setValue(min(99, recibido * 100 // total))
            self._progreso.setLabelText(f"Descargando: {recibido // mb} de {total // mb} MB")
        else:
            self._progreso.setRange(0, 0)
            self._progreso.setLabelText(f"Descargando: {recibido // mb} MB")

    def _cerrar_progreso(self):
        if self._progreso:
            self._progreso.close()
            self._progreso = None

    def _al_cancelar_descarga(self):
        self._cerrar_progreso()
        self._avisada = None

    def _al_fallar_descarga(self, mensaje: str):
        self._cerrar_progreso()
        self._avisada = None
        error(self, mensaje)

    def _al_descargar(self, ruta):
        if self._progreso:
            self._progreso.setCancelButton(None)
            self._progreso.setRange(0, 0)
            self._progreso.setLabelText("Instalando...")
            QApplication.processEvents()
        try:
            carpeta = data_dir() / "respaldos"
            carpeta.mkdir(exist_ok=True)
            db.respaldar(
                self.conn, carpeta / f"antes de actualizar {datetime.now():%Y-%m-%d %H%M}.zip", fotos_dir()
            )
            updater.instalar_y_abrir(ruta)
        except OSError as exc:
            self._al_fallar_descarga(
                "No se pudo instalar la actualización y sigues con la versión actual.\n\n"
                f"Motivo: {exc}\n\nPuedes descargarla desde la página del programa en GitHub."
            )
            return
        QApplication.quit()
