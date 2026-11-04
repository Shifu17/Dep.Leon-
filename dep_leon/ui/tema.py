"""Estilo visual tomado de la hoja de rol de juegos de la liga."""

AMBAR = "#FDC000"
VERDE = "#02CB00"
VERDE_OSCURO = "#029A00"
NEGRO = "#000000"
LAVANDA = "#E9EDF4"
LAVANDA_FUERTE = "#D0D8E8"
ENCABEZADO_TABLA = "#C5CBE0"
AZUL = "#1F6FB5"
AZUL_MARINO = "#1F3864"

ESTILO = f"""
QMainWindow {{ background: {AMBAR}; }}
QWidget#contenido {{ background: {AMBAR}; }}
QDialog {{ background: {LAVANDA}; }}
QLabel {{ color: {AZUL_MARINO}; }}
QWidget#barra {{ background: {NEGRO}; }}
QFrame#banner {{ background: {NEGRO}; border: 3px solid {AMBAR}; }}

QLabel#titulo {{
    background: {VERDE}; color: white; font-size: 17px; font-weight: bold;
    padding: 8px; border: 1px solid {AZUL_MARINO};
}}
QLabel#seccion {{ font-size: 14px; font-weight: bold; color: {AZUL_MARINO}; }}
QLabel#ayuda {{ color: #2B3550; }}

QPushButton#nav {{
    background: transparent; color: {VERDE}; border: none; text-align: left;
    padding: 12px 14px; font-size: 14px; font-weight: bold;
}}
QPushButton#nav:hover {{ background: #1C1C1C; }}
QPushButton#nav:checked {{ background: {VERDE}; color: {NEGRO}; }}
QPushButton#nav:disabled {{ color: #808080; font-weight: normal; }}

QPushButton {{
    background: {VERDE}; color: {NEGRO}; border: 1px solid {AZUL_MARINO}; border-radius: 3px;
    padding: 6px 12px; font-weight: bold;
}}
QPushButton:hover {{ background: #27E025; }}
QPushButton:pressed {{ background: {VERDE_OSCURO}; }}
QPushButton:disabled {{ background: #B9BFCC; color: #5B6275; }}
QPushButton#secundario {{ background: {LAVANDA_FUERTE}; }}
QPushButton#secundario:hover {{ background: {ENCABEZADO_TABLA}; }}
QPushButton#peligro {{ background: #F4C7C3; color: #7A1410; }}
QPushButton#peligro:hover {{ background: #EDA8A2; }}
QPushButton#secundario:disabled, QPushButton#peligro:disabled {{
    background: #DDE1EA; color: #7B8294;
}}

QTableWidget {{
    background: {LAVANDA}; alternate-background-color: {LAVANDA_FUERTE}; color: {AZUL};
    gridline-color: {AZUL_MARINO}; border: 1px solid {AZUL_MARINO};
    selection-background-color: {VERDE}; selection-color: {NEGRO};
    font-weight: bold;
}}
QHeaderView::section {{
    background: {ENCABEZADO_TABLA}; color: {NEGRO}; font-weight: bold; padding: 5px;
    border: 1px solid {AZUL_MARINO};
}}
QLineEdit, QComboBox, QSpinBox, QDateEdit {{
    background: white; color: {AZUL_MARINO}; border: 1px solid {AZUL_MARINO};
    border-radius: 2px; padding: 4px;
}}
QComboBox QAbstractItemView {{
    background: white; color: {AZUL_MARINO};
    selection-background-color: {VERDE}; selection-color: {NEGRO};
}}
QCheckBox {{ color: {AZUL_MARINO}; }}
QToolTip {{ background: white; color: {NEGRO}; border: 1px solid {NEGRO}; }}
"""
