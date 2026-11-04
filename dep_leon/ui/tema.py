"""Estilo visual: fondo claro y descansado, con el verde y el dorado del escudo como acentos."""

from ..paths import asset

FLECHA = asset("flecha.png").as_posix()
FLECHA_ARRIBA = asset("flecha_arriba.png").as_posix()
FONDO = "#F4F7F5"
BLANCO = "#FFFFFF"
TEXTO = "#1E2B25"
TEXTO_SUAVE = "#52635A"
BORDE = "#CBD8D0"
BARRA = "#10291D"
BARRA_HOVER = "#1B3D2C"
VERDE = "#1E7F4C"
VERDE_HOVER = "#23925A"
VERDE_ACTIVO = "#176A3E"
VERDE_SUAVE = "#D3EADC"
FILA_ALTERNA = "#F1F6F3"
ENCABEZADO_TABLA = "#E4EDE8"
DORADO = "#C9A24B"
ROJO = "#A8261C"
ROJO_SUAVE = "#FBEDEB"

ESTILO = f"""
QWidget {{ font-size: 13px; }}
QMainWindow, QWidget#contenido {{ background: {FONDO}; }}
QDialog, QMessageBox {{ background: {FONDO}; }}
QWidget#panelLogo {{ background: {BARRA}; }}
QWidget#panelFormulario {{ background: {BLANCO}; }}
QWidget#barra {{ background: {BARRA}; }}
QLabel {{ color: {TEXTO}; }}
QCheckBox {{ color: {TEXTO}; }}

QLabel#titulo {{
    background: {BLANCO}; color: {VERDE_ACTIVO}; font-size: 19px; font-weight: 600;
    padding: 10px 14px; border: 1px solid {BORDE}; border-bottom: 3px solid {DORADO};
    border-radius: 6px;
}}
QLabel#tituloAcceso {{ color: {VERDE_ACTIVO}; font-size: 24px; font-weight: 600; }}
QLabel#seccion {{ font-size: 14px; font-weight: 600; color: {TEXTO}; }}
QLabel#ayuda {{ color: {TEXTO_SUAVE}; }}
QLabel#aviso {{ color: {ROJO}; font-weight: 600; }}
QLabel#codigo {{
    background: {VERDE_SUAVE}; color: {TEXTO}; font-size: 22px; font-weight: 600;
    padding: 12px; border-radius: 6px;
}}

QPushButton#nav {{
    background: transparent; color: #E6EFEA; border: none; border-left: 4px solid transparent;
    text-align: left; padding: 11px 14px; font-size: 14px; border-radius: 0;
}}
QPushButton#nav:hover {{ background: {BARRA_HOVER}; }}
QPushButton#nav:checked {{
    background: {VERDE}; color: white; font-weight: 600; border-left: 4px solid {DORADO};
}}
QPushButton#nav:disabled {{ color: #8FA59A; }}

QPushButton {{
    background: {VERDE}; color: white; border: 1px solid {VERDE}; border-radius: 6px;
    padding: 7px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: {VERDE_HOVER}; }}
QPushButton:pressed {{ background: {VERDE_ACTIVO}; }}
QPushButton:disabled {{ background: #BCCBC2; border-color: #BCCBC2; color: #46564D; }}
QPushButton#secundario {{ background: {BLANCO}; color: {VERDE_ACTIVO}; border: 1px solid {BORDE}; }}
QPushButton#secundario:hover {{ background: {VERDE_SUAVE}; }}
QPushButton#peligro {{ background: {BLANCO}; color: {ROJO}; border: 1px solid #E3BDB8; }}
QPushButton#peligro:hover {{ background: {ROJO_SUAVE}; }}

QTableWidget {{
    background: {BLANCO}; alternate-background-color: {FILA_ALTERNA}; color: {TEXTO};
    gridline-color: #E3EAE6; border: 1px solid {BORDE}; border-radius: 6px;
    selection-background-color: {VERDE_SUAVE}; selection-color: {TEXTO};
}}
QHeaderView::section {{
    background: {ENCABEZADO_TABLA}; color: {TEXTO}; font-weight: 600; padding: 6px;
    border: none; border-right: 1px solid {BORDE}; border-bottom: 1px solid {BORDE};
}}
QLineEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit {{
    background: {BLANCO}; color: {TEXTO}; border: 1px solid {BORDE};
    border-radius: 5px; padding: 5px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus {{
    border: 1px solid {VERDE};
}}
QSpinBox:disabled, QTimeEdit:disabled {{ background: #EDF1EE; color: #66756D; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{FLECHA}"); width: 12px; height: 8px; }}
QSpinBox::up-button, QTimeEdit::up-button {{
    subcontrol-origin: border; subcontrol-position: top right; width: 20px; border: none;
}}
QSpinBox::down-button, QTimeEdit::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border: none;
}}
QSpinBox::up-button:hover, QTimeEdit::up-button:hover,
QSpinBox::down-button:hover, QTimeEdit::down-button:hover {{ background: {VERDE_SUAVE}; }}
QSpinBox::up-arrow, QTimeEdit::up-arrow {{ image: url("{FLECHA_ARRIBA}"); width: 9px; height: 6px; }}
QSpinBox::down-arrow, QTimeEdit::down-arrow {{ image: url("{FLECHA}"); width: 9px; height: 6px; }}
QComboBox QAbstractItemView {{
    background: {BLANCO}; color: {TEXTO};
    selection-background-color: {VERDE_SUAVE}; selection-color: {TEXTO};
}}
QToolTip {{ background: {BLANCO}; color: {TEXTO}; border: 1px solid {BORDE}; }}
"""
