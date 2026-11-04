"""Punto de entrada del programa."""

import sys

from PySide6.QtWidgets import QApplication

from dep_leon import db
from dep_leon.paths import db_path
from dep_leon.ui.acceso import pedir_acceso
from dep_leon.ui.tema import ESTILO
from dep_leon.ui.ventana import Ventana


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Deportivo León")
    app.setStyle("Fusion")
    app.setStyleSheet(ESTILO)
    conn = db.conectar(db_path())
    try:
        if not pedir_acceso(conn):
            return 0
        ventana = Ventana(conn)
        ventana.show()
        return app.exec()
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
