"""Pantallas de inicio de sesión, creación de cuenta y recuperación."""

import sqlite3

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import acceso
from ..paths import asset
from .comun import AvisoCampo, botones_dialogo, error, info

MAX_INTENTOS = 5
ESPERA_SEGUNDOS = 30
ANCHO_LOGO = 270


def _boton(texto: str, al_pulsar, estilo: str | None = None) -> QPushButton:
    """Botón que no se activa solo con Enter: cada campo decide qué hace esa tecla."""
    resultado = QPushButton(texto)
    resultado.setAutoDefault(False)
    resultado.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    if estilo:
        resultado.setObjectName(estilo)
    resultado.clicked.connect(al_pulsar)
    return resultado


def _campo_contrasena() -> QLineEdit:
    campo = QLineEdit()
    campo.setEchoMode(QLineEdit.EchoMode.Password)
    return campo


def _mostrar_al_marcar(casilla: QCheckBox, campos: list[QLineEdit]) -> None:
    def cambiar(marcada: bool):
        modo = QLineEdit.EchoMode.Normal if marcada else QLineEdit.EchoMode.Password
        for campo in campos:
            campo.setEchoMode(modo)

    casilla.toggled.connect(cambiar)


class DialogoCodigo(QDialog):
    """Muestra el código de recuperación y no se cierra hasta confirmar que se guardó."""

    def __init__(self, padre, codigo: str):
        super().__init__(padre)
        self.setWindowTitle("Código de recuperación")
        self.codigo = codigo
        etiqueta = QLabel(codigo, objectName="codigo", alignment=Qt.AlignmentFlag.AlignCenter)
        etiqueta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.guardado = QCheckBox("Ya lo guardé en un lugar seguro")
        self.continuar = _boton("Continuar", self.accept)
        self.continuar.setEnabled(False)
        self.guardado.toggled.connect(self.continuar.setEnabled)

        raiz = QVBoxLayout(self)
        raiz.addWidget(QLabel("Guarda este código", objectName="seccion"))
        raiz.addWidget(
            QLabel(
                "Si olvidas tu contraseña, es la única forma de volver a entrar. Anótalo y guárdalo "
                "fuera de esta computadora: no se volverá a mostrar.",
                objectName="ayuda", wordWrap=True,
            )
        )
        raiz.addWidget(etiqueta)
        raiz.addWidget(_boton("Copiar código", self._copiar, "secundario"))
        raiz.addWidget(self.guardado)
        raiz.addWidget(self.continuar)
        self.setFixedWidth(420)

    def _copiar(self):
        QGuiApplication.clipboard().setText(self.codigo)

    def reject(self):
        if self.guardado.isChecked():
            super().reject()


class DialogoAcceso(QDialog):
    """Crea la cuenta la primera vez; después pide usuario y contraseña."""

    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        self.setWindowTitle("Deportivo León")
        self.setWindowIcon(QIcon(str(asset("icono.ico"))))
        self.fallos = 0

        panel = QWidget(objectName="panelLogo")
        panel.setFixedWidth(ANCHO_LOGO + 60)
        columna = QVBoxLayout(panel)
        logo = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(QPixmap(str(asset("logo.png"))))
        columna.addStretch(1)
        columna.addWidget(logo)
        columna.addStretch(1)

        self.pila = QStackedWidget()
        self.pila.addWidget(self._pagina_crear())
        self.pila.addWidget(self._pagina_entrar())
        self.pila.addWidget(self._pagina_recuperar())
        cuerpo = QWidget(objectName="panelFormulario")
        margen = QVBoxLayout(cuerpo)
        margen.setContentsMargins(28, 24, 28, 24)
        margen.addWidget(self.pila)

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(panel)
        raiz.addWidget(cuerpo, 1)
        self.resize(760, 430)
        self._mostrar_inicio()

    def _mostrar_inicio(self):
        if acceso.hay_cuenta(self.conn):
            self.pila.setCurrentIndex(1)
            self.usuario.setText(acceso.nombre_usuario(self.conn))
            self.contrasena.clear()
            self.contrasena.setFocus()
        else:
            self.pila.setCurrentIndex(0)
            self.nuevo_usuario.setFocus()

    def _pagina_crear(self) -> QWidget:
        pagina = QWidget()
        self.nuevo_usuario = QLineEdit()
        self.nueva_contrasena = _campo_contrasena()
        self.confirmacion = _campo_contrasena()
        mostrar = QCheckBox("Mostrar contraseña")
        _mostrar_al_marcar(mostrar, [self.nueva_contrasena, self.confirmacion])
        self.nuevo_usuario.returnPressed.connect(self.nueva_contrasena.setFocus)
        self.nueva_contrasena.returnPressed.connect(self.confirmacion.setFocus)
        self.confirmacion.returnPressed.connect(self.crear)

        forma = QFormLayout()
        forma.addRow("Usuario:", self.nuevo_usuario)
        forma.addRow("Contraseña:", self.nueva_contrasena)
        forma.addRow("Repite la contraseña:", self.confirmacion)
        forma.addRow("", mostrar)

        raiz = QVBoxLayout(pagina)
        raiz.addStretch(1)
        raiz.addWidget(QLabel("Te damos la bienvenida", objectName="tituloAcceso"))
        raiz.addWidget(
            QLabel(
                "Crea la cuenta para entrar al programa. Tus datos actuales se conservan.",
                objectName="ayuda", wordWrap=True,
            )
        )
        raiz.addLayout(forma)
        self.aviso_crear = AvisoCampo()
        raiz.addWidget(self.aviso_crear)
        raiz.addWidget(_boton("Crear cuenta", self.crear))
        raiz.addStretch(1)
        return pagina

    def _pagina_entrar(self) -> QWidget:
        pagina = QWidget()
        self.usuario = QLineEdit()
        self.contrasena = _campo_contrasena()
        mostrar = QCheckBox("Mostrar contraseña")
        _mostrar_al_marcar(mostrar, [self.contrasena])
        self.usuario.returnPressed.connect(self.contrasena.setFocus)
        self.contrasena.returnPressed.connect(self.entrar)
        self.aviso = QLabel(objectName="aviso", wordWrap=True)
        self.boton_entrar = _boton("Iniciar sesión", self.entrar)

        forma = QFormLayout()
        forma.addRow("Usuario:", self.usuario)
        forma.addRow("Contraseña:", self.contrasena)
        forma.addRow("", mostrar)

        raiz = QVBoxLayout(pagina)
        raiz.addStretch(1)
        raiz.addWidget(QLabel("Iniciar sesión", objectName="tituloAcceso"))
        raiz.addLayout(forma)
        raiz.addWidget(self.aviso)
        raiz.addWidget(self.boton_entrar)
        raiz.addWidget(_boton("Olvidé mi contraseña", self._ir_a_recuperar, "secundario"))
        raiz.addStretch(1)
        return pagina

    def _pagina_recuperar(self) -> QWidget:
        pagina = QWidget()
        self.codigo = QLineEdit()
        self.codigo.setPlaceholderText("XXXX-XXXX-XXXX")
        self.contrasena_recuperada = _campo_contrasena()
        self.confirmacion_recuperada = _campo_contrasena()
        self.contrasena_recuperada.returnPressed.connect(self.confirmacion_recuperada.setFocus)
        self.confirmacion_recuperada.returnPressed.connect(self.recuperar)
        self.codigo.returnPressed.connect(self.contrasena_recuperada.setFocus)
        self.aviso_recuperar = QLabel(objectName="aviso", wordWrap=True)
        self.boton_recuperar = _boton("Cambiar contraseña", self.recuperar)

        forma = QFormLayout()
        forma.addRow("Código:", self.codigo)
        forma.addRow("Contraseña nueva:", self.contrasena_recuperada)
        forma.addRow("Repítela:", self.confirmacion_recuperada)

        raiz = QVBoxLayout(pagina)
        raiz.addStretch(1)
        raiz.addWidget(QLabel("Recuperar acceso", objectName="tituloAcceso"))
        raiz.addWidget(
            QLabel(
                "Escribe el código que guardaste al crear la cuenta.", objectName="ayuda", wordWrap=True
            )
        )
        raiz.addLayout(forma)
        raiz.addWidget(self.aviso_recuperar)
        raiz.addWidget(self.boton_recuperar)
        raiz.addWidget(_boton("Volver", self._mostrar_inicio, "secundario"))
        raiz.addStretch(1)
        return pagina

    def _ir_a_recuperar(self):
        self.pila.setCurrentIndex(2)
        self.codigo.setFocus()

    def crear(self):
        if self.nueva_contrasena.text() != self.confirmacion.text():
            self.aviso_crear.mostrar("Las contraseñas no coinciden.")
            self.confirmacion.setFocus()
            return
        try:
            codigo = acceso.crear_cuenta(
                self.conn, self.nuevo_usuario.text(), self.nueva_contrasena.text()
            )
        except ValueError as exc:
            self.aviso_crear.mostrar(str(exc))
            return
        DialogoCodigo(self, codigo).exec()
        self.accept()

    def _registrar_fallo(self, etiqueta: QLabel, mensaje: str):
        self.fallos += 1
        if self.fallos < MAX_INTENTOS:
            etiqueta.setText(mensaje)
            return
        self.fallos = 0
        etiqueta.setText(f"Demasiados intentos. Espera {ESPERA_SEGUNDOS} segundos.")
        for boton in (self.boton_entrar, self.boton_recuperar):
            boton.setEnabled(False)
        QTimer.singleShot(ESPERA_SEGUNDOS * 1000, self._terminar_espera)

    def _terminar_espera(self):
        for boton in (self.boton_entrar, self.boton_recuperar):
            boton.setEnabled(True)
        self.aviso.clear()
        self.aviso_recuperar.clear()

    def entrar(self):
        if not self.boton_entrar.isEnabled():
            return
        if acceso.verificar(self.conn, self.usuario.text(), self.contrasena.text()):
            self.accept()
            return
        self.contrasena.clear()
        self._registrar_fallo(self.aviso, "Usuario o contraseña incorrectos.")

    def recuperar(self):
        if not self.boton_recuperar.isEnabled():
            return
        if self.contrasena_recuperada.text() != self.confirmacion_recuperada.text():
            self.aviso_recuperar.setText("Las contraseñas no coinciden.")
            return
        problema = acceso.problema_con_contrasena(self.contrasena_recuperada.text())
        if problema:
            self.aviso_recuperar.setText(problema)
            return
        try:
            nuevo = acceso.recuperar(
                self.conn, self.codigo.text(), self.contrasena_recuperada.text()
            )
        except ValueError as exc:
            self._registrar_fallo(self.aviso_recuperar, str(exc))
            return
        DialogoCodigo(self, nuevo).exec()
        self.accept()


class DialogoCambiarContrasena(QDialog):
    def __init__(self, padre, conn: sqlite3.Connection):
        super().__init__(padre)
        self.setWindowTitle("Cambiar contraseña")
        self.conn = conn
        self.actual = _campo_contrasena()
        self.nueva = _campo_contrasena()
        self.confirmacion = _campo_contrasena()
        forma = QFormLayout(self)
        forma.addRow("Contraseña actual:", self.actual)
        forma.addRow("Contraseña nueva:", self.nueva)
        forma.addRow("Repítela:", self.confirmacion)
        self.aviso = AvisoCampo()
        forma.addRow(self.aviso)
        forma.addRow(botones_dialogo(self, self._aceptar))

    def _aceptar(self):
        if self.nueva.text() != self.confirmacion.text():
            self.aviso.mostrar("Las contraseñas nuevas no coinciden.")
            return
        try:
            acceso.cambiar_contrasena(self.conn, self.actual.text(), self.nueva.text())
        except ValueError as exc:
            self.aviso.mostrar(str(exc))
            return
        info(self, "Contraseña cambiada.")
        self.accept()


def pedir_acceso(conn: sqlite3.Connection) -> bool:
    return bool(DialogoAcceso(conn).exec())
