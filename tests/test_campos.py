import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit

from dep_leon.ui import campos
from dep_leon.ui import pagina_arbitros as ui_arbitros
from dep_leon.ui import pagina_equipos as ui_equipos
from dep_leon.ui import pagina_ligas as ui_ligas


def teclear(campo: QLineEdit, texto: str) -> None:
    """Como si se escribiera en el teclado, letra por letra (QTest.keyClicks falla con acentos)."""
    for letra in texto:
        QApplication.sendEvent(campo, QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, letra))


def escribir(campo: QLineEdit, texto: str) -> str:
    campo.clear()
    teclear(campo, texto)
    return campo.text()


@pytest.mark.parametrize(
    "restringir, tecleado, queda",
    [
        (campos.solo_nombre, "José Pérez 2 Ñúñez!", "José Pérez  Ñúñez"),
        (campos.solo_nombre, "O'Brien-Lugo Jr.", "O'Brien-Lugo Jr."),
        (campos.solo_telefono, "844-123 4567 99", "8441234567"),
        (campos.solo_curp, "abcd010203hclxxx0!1", "ABCD010203HCLXXX01"),
        (campos.solo_nombre_de_equipo, "Atlético F.C. 2000 #1", "Atlético F.C. 2000 1"),
        (campos.solo_categoria, "2015-2016 *Libre", "2015-2016 Libre"),
        (campos.solo_dias, "Viernes y sábado, 9am", "Viernes y sábado, am"),
        (campos.solo_temporada, "2026-2027 abc", "2026-2027 "),
    ],
)
def test_solo_se_escribe_lo_que_va(app, restringir, tecleado, queda):
    campo = restringir(QLineEdit())
    assert escribir(campo, tecleado) == queda


def test_datos_viejos_se_limpian_para_poder_editarlos(app):
    assert campos.solo_telefono(QLineEdit("+52 (844) 123-4567")).text() == "8441234567"
    assert campos.solo_curp(QLineEdit("abcd010203hclxxx01")).text() == "ABCD010203HCLXXX01"
    nombre = campos.solo_nombre(QLineEdit("Juan Pérez 3"))
    assert nombre.text() == "Juan Pérez "
    teclear(nombre, "López")
    assert nombre.text() == "Juan Pérez López"


@pytest.mark.parametrize("texto, motivo", [("", None), ("8441234567", None), ("844123", "escribiste 6")])
def test_telefono_completo(texto, motivo):
    resultado = campos.error_telefono(texto)
    assert (resultado is None) if motivo is None else (motivo in resultado)


def test_dialogo_equipo_pide_telefono_completo(app):
    dialogo = ui_equipos.DialogoEquipo(None, [{"nombre": "Libre", "id": 1}])
    escribir(dialogo.nombre, "Toros")
    escribir(dialogo.responsable, "Entrenador 7")
    assert dialogo.responsable.text() == "Entrenador "
    escribir(dialogo.telefono, "84412")
    dialogo._aceptar()
    assert dialogo.result() == 0 and "10 números" in dialogo.error_telefono.text()
    escribir(dialogo.telefono, "8441234567")
    dialogo._aceptar()
    assert dialogo.result() == 1


def test_dialogo_arbitro_y_jugador(app):
    arbitro = ui_arbitros.DialogoArbitro(None)
    assert escribir(arbitro.nombre, "Árbitro 1 Uno") == "Árbitro  Uno"
    escribir(arbitro.telefono, "123")
    arbitro._aceptar()
    assert arbitro.result() == 0 and arbitro.error_telefono.text()

    jugador = ui_equipos.DialogoJugador(None, {"anio_min": None, "anio_max": None})
    assert escribir(jugador.nombre, "Ana2 Ruiz") == "Ana Ruiz"
    assert escribir(jugador.curp, "abcd") == "ABCD"


def test_dialogos_de_ligas(app):
    liga = ui_ligas.DialogoLiga(None)
    assert escribir(liga.dias, "Lunes 1") == "Lunes "
    torneo = ui_ligas.DialogoTorneo(None)
    assert escribir(torneo.nombre, "Copa 2026-2027") == " 2026-2027"
