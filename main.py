"""Punto de entrada del programa."""

import sys

from PySide6.QtWidgets import QApplication

from dep_leon import db
from dep_leon.paths import db_path
from dep_leon.ui.tema import ESTILO
from dep_leon.ui.ventana import Ventana


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Deportivo León")
    app.setStyle("Fusion")
    app.setStyleSheet(ESTILO)
    conn = db.conectar(db_path())
    ventana = Ventana(conn)
    ventana.show()
    resultado = app.exec()
    conn.close()
    return resultado


if __name__ == "__main__":
    sys.exit(main())
