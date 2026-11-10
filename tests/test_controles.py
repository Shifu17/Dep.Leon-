import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QComboBox

from dep_leon.ui import pagina_resultados as ui_resultados
from dep_leon.ui.controles import Segmentado, SelectorFecha
from dep_leon.ui.filtros import FiltrosLiga


def test_segmentado_se_usa_como_una_lista(app):
    control = Segmentado(["Uno", "Dos", "Tres"], "Ver")
    cambios = []
    control.currentIndexChanged.connect(cambios.append)
    assert control.currentText() == "Uno"
    control.botones()[2].click()
    assert (control.currentIndex(), control.currentText()) == (2, "Tres")
    control.setCurrentText("Dos")
    assert control.currentIndex() == 1 and cambios == [2, 1]
    assert [b.accessibleName() for b in control.botones()] == ["Ver: Uno", "Ver: Dos", "Ver: Tres"]
    assert [b.property("posicion") for b in control.botones()] == ["inicio", "medio", "fin"]


def test_flechas_de_fecha(app):
    combo = QComboBox()
    combo.addItems(["Todas", "17/10/2026", "24/10/2026"])
    selector = SelectorFecha(combo)
    assert not selector.anterior.isEnabled() and selector.siguiente.isEnabled()
    selector.siguiente.click()
    selector.siguiente.click()
    assert combo.currentText() == "24/10/2026" and not selector.siguiente.isEnabled()
    selector.anterior.click()
    assert combo.currentText() == "17/10/2026" and selector.anterior.isEnabled()
    combo.clear()
    assert not selector.anterior.isEnabled() and not selector.siguiente.isEnabled()


def test_filtros_con_etiqueta_arriba(app, conn):
    from PySide6.QtWidgets import QLabel

    filtros = FiltrosLiga(conn, con_todas=True)
    otro = QComboBox()
    columna = filtros.agregar("Reporte", otro, primero=True)
    titulos = [l.text() for l in filtros.findChildren(QLabel) if l.objectName() == "filtroTitulo"]
    assert titulos == ["Liga", "Torneo", "Categoría", "Reporte"]
    assert filtros.layout().itemAt(0).widget() is columna  # «primero» va antes de la liga
    assert filtros.liga.accessibleName() == "Liga"
    filtros.deleteLater()


def test_resultados_cambia_de_vista_con_un_clic(app, ventana_resultados):
    pagina = ventana_resultados.resultados
    pagina.ver.botones()[2].click()
    assert pagina.ver.currentText() == ui_resultados.VER_TODOS


import pytest  # noqa: E402

from dep_leon import updater  # noqa: E402
from dep_leon.ui.ventana import Ventana  # noqa: E402


@pytest.fixture
def ventana_resultados(app, conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    resultado = Ventana(conn)
    yield resultado
    resultado.temporizador.stop()
    resultado.close()
