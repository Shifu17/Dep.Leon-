"""Estilo visual: fondo claro y descansado, con el verde y el dorado del escudo como acentos.

Los colores viven en ``dep_leon.colores``. El tamaño de letra sigue el ajuste «Tamaño del texto»
de Windows (Accesibilidad), que Qt no aplica por sí solo a un estilo con tamaños fijos.
"""

from ..colores import (  # noqa: F401  (se reexportan para las pruebas de contraste)
    BARRA,
    BARRA_HOVER,
    BLANCO,
    BORDE,
    BORDE_CONTROL,
    BORDE_PELIGRO,
    CAMPO_DESACTIVADO,
    CUADRICULA,
    DESACTIVADO,
    DORADO,
    ENCABEZADO_TABLA,
    FILA_ALTERNA,
    FONDO,
    ROJO,
    ROJO_SUAVE,
    TEXTO,
    TEXTO_BARRA,
    TEXTO_BARRA_INACTIVO,
    TEXTO_CAMPO_DESACTIVADO,
    TEXTO_DESACTIVADO,
    TEXTO_SUAVE,
    VERDE,
    VERDE_ACTIVO,
    VERDE_SUAVE,
)
from ..paths import asset

FLECHA = asset("flecha.png").as_posix()
FLECHA_ARRIBA = asset("flecha_arriba.png").as_posix()


def escala_texto() -> float:
    """Factor de «Tamaño del texto» de Windows (1.0 a 2.25); 1.0 en otros sistemas o si falla."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Accessibility") as clave:
            valor, _ = winreg.QueryValueEx(clave, "TextScaleFactor")
        return min(max(int(valor) / 100, 1.0), 2.25)
    except (ImportError, OSError, ValueError):
        return 1.0


ESCALA_TEXTO = escala_texto()


def _t(pixeles: int) -> str:
    return f"{round(pixeles * ESCALA_TEXTO)}px"


ESTILO = f"""
QWidget {{ font-size: {_t(14)}; }}
QMainWindow, QWidget#contenido {{ background: {FONDO}; }}
QDialog, QMessageBox {{ background: {FONDO}; }}
QWidget#panelLogo {{ background: {BARRA}; }}
QWidget#panelFormulario {{ background: {BLANCO}; }}
QWidget#barra {{ background: {BARRA}; }}
QLabel {{ color: {TEXTO}; }}
QCheckBox, QRadioButton {{
    color: {TEXTO}; border: 1px solid transparent; border-radius: 3px; padding: 3px 4px; spacing: 8px;
}}
QCheckBox::indicator {{ width: 18px; height: 18px; }}
QCheckBox:focus, QRadioButton:focus {{ border-color: {VERDE_ACTIVO}; }}

QLabel#titulo {{
    background: {BLANCO}; color: {VERDE_ACTIVO}; font-size: {_t(19)}; font-weight: 600;
    padding: 10px 14px; border: 1px solid {BORDE}; border-bottom: 3px solid {DORADO};
    border-radius: 6px;
}}
QLabel#tituloAcceso {{ color: {VERDE_ACTIVO}; font-size: {_t(24)}; font-weight: 600; }}
QFrame#tarjeta {{ background: {BLANCO}; border: 1px solid {BORDE}; border-radius: 8px; }}
QLabel#tarjetaNumero {{ color: {TEXTO}; font-size: {_t(30)}; font-weight: 600; }}
QFrame#franja {{ background: {BLANCO}; border: 1px solid {BORDE}; border-radius: 8px; }}
QFrame#separador {{ background: {BORDE}; margin: 10px 0; }}
QLabel#datoNumero {{ color: {TEXTO}; font-size: {_t(22)}; font-weight: 600; }}
QLabel#datoAlerta {{ color: {ROJO}; font-size: {_t(22)}; font-weight: 600; }}
QLabel#datoTexto {{ color: {TEXTO_SUAVE}; }}
QFrame#pendiente {{ background: {BLANCO}; border: 1px solid {BORDE}; border-radius: 6px; }}
QFrame#pendienteAlerta {{ background: {ROJO_SUAVE}; border: 1px solid {BORDE_PELIGRO}; border-radius: 6px; }}
QLabel#vacio {{ color: {TEXTO_SUAVE}; background: transparent; }}
QLabel#errorCampo {{ color: {ROJO}; }}
QLineEdit[invalido="true"], QComboBox[invalido="true"], QSpinBox[invalido="true"],
QDoubleSpinBox[invalido="true"], QDateEdit[invalido="true"], QTimeEdit[invalido="true"] {{
    border: 2px solid {ROJO}; padding: 5px;
}}
QPushButton#mas {{ padding-right: 26px; }}
QPushButton#mas::menu-indicator {{
    image: url("{FLECHA}"); width: 9px; height: 6px;
    subcontrol-origin: padding; subcontrol-position: right center; right: 9px;
}}
QMenu {{ background: {BLANCO}; color: {TEXTO}; border: 1px solid {BORDE_CONTROL}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {VERDE_SUAVE}; color: {TEXTO}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {TEXTO_SUAVE}; padding: 6px 14px; margin-right: 4px;
    border: none; border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{ color: {VERDE_ACTIVO}; border-bottom: 2px solid {VERDE}; }}
QTabBar::tab:hover {{ color: {TEXTO}; }}
QTabBar:focus {{ border: 1px solid {BARRA}; border-radius: 4px; }}
QLabel#tarjetaAlerta {{ color: {ROJO}; font-size: {_t(30)}; font-weight: 600; }}
QFrame#avisoAtrasados {{ background: {ROJO_SUAVE}; border: 1px solid {BORDE_PELIGRO}; border-radius: 6px; }}
QLabel#tarjetaTexto {{ color: {TEXTO_SUAVE}; }}
QSpinBox#marcador {{ font-size: {_t(24)}; font-weight: 600; }}
QWidget#listaGoles {{ background: {BLANCO}; }}
QLabel#marcoFoto {{ background: {BLANCO}; color: {TEXTO_SUAVE}; border: 1px solid {BORDE}; }}
QWidget#lienzoLlave {{ background: {FONDO}; }}
QPushButton#llave {{
    background: {BLANCO}; color: {TEXTO}; border: 1px solid {BORDE}; border-radius: 6px;
    text-align: left; padding: 8px 10px; font-weight: 400;
}}
QPushButton#llave:hover {{ background: {FILA_ALTERNA}; }}
QPushButton#llave:checked {{ background: {VERDE_SUAVE}; border: 2px solid {VERDE}; }}
QPushButton#llave:disabled {{ background: {FILA_ALTERNA}; color: {TEXTO_SUAVE}; }}
QPushButton#llave:focus {{ border: 2px solid {BARRA}; padding: 7px 9px; }}
QLabel#campeon {{
    background: {BARRA}; color: white; font-size: {_t(18)}; font-weight: 600; padding: 8px 14px;
    border-left: 5px solid {DORADO}; border-radius: 4px;
}}
QLabel#seccion {{ font-size: {_t(14)}; font-weight: 600; color: {TEXTO}; }}
QLabel#ayuda {{ color: {TEXTO_SUAVE}; }}
QLabel#ayudaPagina {{ color: {TEXTO_SUAVE}; padding: 2px 2px 4px 2px; }}
QLabel#aviso {{ color: {ROJO}; font-weight: 600; }}
QLabel#codigo {{
    background: {VERDE_SUAVE}; color: {TEXTO}; font-size: {_t(22)}; font-weight: 600;
    padding: 12px; border-radius: 6px;
}}

QPushButton#nav {{
    background: transparent; color: {TEXTO_BARRA}; border: none; border-left: 4px solid transparent;
    text-align: left; padding: 11px 14px; font-size: {_t(15)}; border-radius: 0;
}}
QPushButton#nav:hover {{ background: {BARRA_HOVER}; }}
QPushButton#nav:checked {{
    background: {VERDE}; color: white; font-weight: 600; border-left: 4px solid {DORADO};
}}
QPushButton#nav:disabled {{ color: {TEXTO_BARRA_INACTIVO}; }}
QPushButton#nav:focus {{
    background: {BARRA_HOVER}; border: 2px solid {DORADO}; padding: 9px 12px 9px 16px;
}}
QPushButton#nav:checked:focus {{ background: {VERDE}; border: 2px solid white; }}

QPushButton {{
    background: {VERDE}; color: white; border: 1px solid {VERDE}; border-radius: 6px;
    padding: 9px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: {VERDE_ACTIVO}; border-color: {VERDE_ACTIVO}; }}
QPushButton:pressed {{ background: {BARRA}; border-color: {BARRA}; }}
QPushButton:focus {{ border: 2px solid {BARRA}; padding: 8px 13px; }}
QPushButton:disabled {{ background: {DESACTIVADO}; border-color: {DESACTIVADO}; color: {TEXTO_DESACTIVADO}; }}
QPushButton#secundario, QPushButton#mas {{ background: {BLANCO}; color: {VERDE_ACTIVO}; border: 1px solid {BORDE_CONTROL}; }}
QPushButton#secundario:hover, QPushButton#mas:hover {{ background: {VERDE_SUAVE}; border-color: {VERDE_ACTIVO}; }}
QPushButton#secundario:pressed, QPushButton#mas:pressed {{ background: {VERDE_SUAVE}; }}
QPushButton#secundario:focus, QPushButton#mas:focus {{ border: 2px solid {BARRA}; padding: 8px 13px; }}
QPushButton#peligro {{ background: {BLANCO}; color: {ROJO}; border: 1px solid {BORDE_PELIGRO}; }}
QPushButton#peligro:hover {{ background: {ROJO_SUAVE}; border-color: {ROJO}; }}
QPushButton#peligro:pressed {{ background: {ROJO_SUAVE}; }}
QPushButton#peligro:focus {{ border: 2px solid {ROJO}; padding: 8px 13px; }}

QTableWidget {{
    background: {BLANCO}; alternate-background-color: {FILA_ALTERNA}; color: {TEXTO};
    gridline-color: {CUADRICULA}; border: 1px solid {BORDE}; border-radius: 6px;
    selection-background-color: {VERDE_SUAVE}; selection-color: {TEXTO};
}}
QTableWidget:focus {{ border: 2px solid {VERDE}; }}
QTableWidget::item {{ padding: 0 4px; }}
QTableWidget::item:selected {{
    background: {VERDE_SUAVE}; color: {TEXTO};
    border-top: 1px solid {VERDE}; border-bottom: 1px solid {VERDE};
}}
QHeaderView::section {{
    background: {ENCABEZADO_TABLA}; color: {TEXTO}; font-weight: 600; padding: 7px 6px;
    border: none; border-right: 1px solid {BORDE}; border-bottom: 1px solid {BORDE};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit {{
    background: {BLANCO}; color: {TEXTO}; border: 1px solid {BORDE_CONTROL};
    border-radius: 5px; padding: 6px;
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus {{
    border: 2px solid {VERDE}; padding: 5px;
}}
QDoubleSpinBox:disabled, QSpinBox:disabled, QTimeEdit:disabled {{ background: {CAMPO_DESACTIVADO}; color: {TEXTO_CAMPO_DESACTIVADO}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{FLECHA}"); width: 12px; height: 8px; }}
QDoubleSpinBox::up-button, QSpinBox::up-button, QTimeEdit::up-button {{
    subcontrol-origin: border; subcontrol-position: top right; width: 20px; border: none;
}}
QDoubleSpinBox::down-button, QSpinBox::down-button, QTimeEdit::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border: none;
}}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover, QTimeEdit::up-button:hover,
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover, QTimeEdit::down-button:hover {{ background: {VERDE_SUAVE}; }}
QDoubleSpinBox::up-arrow, QSpinBox::up-arrow, QTimeEdit::up-arrow {{ image: url("{FLECHA_ARRIBA}"); width: 9px; height: 6px; }}
QDoubleSpinBox::down-arrow, QSpinBox::down-arrow, QTimeEdit::down-arrow {{ image: url("{FLECHA}"); width: 9px; height: 6px; }}
QComboBox QAbstractItemView {{
    background: {BLANCO}; color: {TEXTO};
    selection-background-color: {VERDE_SUAVE}; selection-color: {TEXTO};
}}
QToolTip {{ background: {BLANCO}; color: {TEXTO}; border: 1px solid {BORDE}; }}
"""
