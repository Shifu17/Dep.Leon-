import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from dep_leon import acceso, db
from dep_leon.ui import acceso as ui_acceso


@pytest.fixture
def cuenta(conn):
    return acceso.crear_cuenta(conn, "  Admin  Liga ", "secreto1")


def test_primera_vez_no_hay_cuenta(conn):
    assert not acceso.hay_cuenta(conn)
    assert not acceso.verificar(conn, "x", "y")


def test_verifica_usuario_y_contrasena(conn, cuenta):
    assert acceso.verificar(conn, "admin liga", "secreto1")
    assert not acceso.verificar(conn, "admin liga", "Secreto1")
    assert not acceso.verificar(conn, "otro", "secreto1")


def test_no_guarda_secretos_en_claro(conn, cuenta):
    fila = conn.execute("SELECT * FROM usuarios").fetchone()
    assert "secreto1" not in fila["contrasena"]
    assert cuenta.replace("-", "") not in fila["codigo"]
    assert fila["contrasena"].startswith("scrypt$")


def test_dos_cuentas_iguales_tienen_huella_distinta(tmp_path):
    otra = db.conectar(tmp_path / "otra.db")
    uno = db.conectar(tmp_path / "uno.db")
    acceso.crear_cuenta(otra, "a", "secreto1")
    acceso.crear_cuenta(uno, "a", "secreto1")
    consulta = "SELECT contrasena FROM usuarios"
    assert otra.execute(consulta).fetchone()[0] != uno.execute(consulta).fetchone()[0]
    otra.close()
    uno.close()


@pytest.mark.parametrize("usuario, contrasena", [("", "secreto1"), ("   ", "secreto1"), ("a", "corta")])
def test_rechaza_datos_invalidos(conn, usuario, contrasena):
    with pytest.raises(ValueError):
        acceso.crear_cuenta(conn, usuario, contrasena)
    assert not acceso.hay_cuenta(conn)


def test_solo_una_cuenta(conn, cuenta):
    with pytest.raises(ValueError):
        acceso.crear_cuenta(conn, "otro", "secreto2")


def test_cambiar_contrasena(conn, cuenta):
    with pytest.raises(ValueError):
        acceso.cambiar_contrasena(conn, "mala", "nueva123")
    with pytest.raises(ValueError):
        acceso.cambiar_contrasena(conn, "secreto1", "x")
    acceso.cambiar_contrasena(conn, "secreto1", "nueva123")
    assert acceso.verificar(conn, "admin liga", "nueva123")
    assert not acceso.verificar(conn, "admin liga", "secreto1")


def test_recuperar_con_codigo_y_el_codigo_se_gasta(conn, cuenta):
    with pytest.raises(ValueError):
        acceso.recuperar(conn, "AAAA-BBBB-CCCC", "nueva123")
    nuevo = acceso.recuperar(conn, cuenta.lower().replace("-", " "), "nueva123")
    assert acceso.verificar(conn, "admin liga", "nueva123")
    with pytest.raises(ValueError):
        acceso.recuperar(conn, cuenta, "otra1234")
    acceso.recuperar(conn, nuevo, "otra1234")
    assert acceso.verificar(conn, "admin liga", "otra1234")


def test_restaurar_conserva_la_cuenta_actual(conn, tmp_path):
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    # Respaldo hecho antes de que existiera la cuenta (o de una versión anterior).
    with conn:
        conn.execute("DROP TABLE usuarios")
    respaldo = tmp_path / "viejo.zip"
    db.respaldar(conn, respaldo, fotos)
    conn.executescript(db.ESQUEMA)
    acceso.crear_cuenta(conn, "admin", "secreto1")

    db.restaurar(conn, respaldo, fotos)
    assert acceso.verificar(conn, "admin", "secreto1")


def test_respaldo_con_otra_cuenta_no_cambia_quien_entra(conn, tmp_path):
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    acceso.crear_cuenta(conn, "antigua", "secreto1")
    respaldo = tmp_path / "r.zip"
    db.respaldar(conn, respaldo, fotos)
    with conn:
        conn.execute("DELETE FROM usuarios")
    acceso.crear_cuenta(conn, "actual", "secreto2")

    db.restaurar(conn, respaldo, fotos)
    assert acceso.verificar(conn, "actual", "secreto2")
    assert not acceso.verificar(conn, "antigua", "secreto1")


# --- Pantallas ---


def test_primera_vez_muestra_crear_y_entrega_codigo(app, conn, monkeypatch):
    mostrados = []
    monkeypatch.setattr(ui_acceso.DialogoCodigo, "exec", lambda self: mostrados.append(self.codigo))
    dialogo = ui_acceso.DialogoAcceso(conn)
    assert dialogo.pila.currentIndex() == 0

    dialogo.nuevo_usuario.setText("admin")
    dialogo.nueva_contrasena.setText("secreto1")
    dialogo.confirmacion.setText("distinta")
    errores = []
    monkeypatch.setattr(ui_acceso, "error", lambda _, m: errores.append(m))
    dialogo.crear()
    assert dialogo.aviso_crear.text() == "Las contraseñas no coinciden." and not acceso.hay_cuenta(conn)

    dialogo.confirmacion.setText("secreto1")
    dialogo.crear()
    assert dialogo.result() == 1 and len(mostrados) == 1
    assert acceso.verificar(conn, "admin", "secreto1")


def test_entrar_y_bloqueo_por_intentos(app, conn, cuenta):
    dialogo = ui_acceso.DialogoAcceso(conn)
    assert dialogo.pila.currentIndex() == 1
    assert dialogo.usuario.text() == "Admin Liga"

    for _ in range(ui_acceso.MAX_INTENTOS - 1):
        dialogo.contrasena.setText("mala")
        dialogo.entrar()
    assert dialogo.aviso.text() == "Usuario o contraseña incorrectos."
    assert dialogo.contrasena.text() == "" and dialogo.result() == 0

    dialogo.contrasena.setText("mala")
    dialogo.entrar()
    assert "Espera" in dialogo.aviso.text() and not dialogo.boton_entrar.isEnabled()

    # Durante la espera, ni la contraseña correcta deja pasar.
    dialogo.contrasena.setText("secreto1")
    dialogo.entrar()
    assert dialogo.result() == 0

    dialogo._terminar_espera()
    dialogo.entrar()
    assert dialogo.result() == 1


def test_recuperar_desde_la_pantalla(app, conn, cuenta, monkeypatch):
    monkeypatch.setattr(ui_acceso.DialogoCodigo, "exec", lambda self: None)
    dialogo = ui_acceso.DialogoAcceso(conn)
    dialogo._ir_a_recuperar()
    dialogo.codigo.setText(cuenta)
    dialogo.contrasena_recuperada.setText("nueva123")
    dialogo.confirmacion_recuperada.setText("nueva123")
    dialogo.recuperar()
    assert dialogo.result() == 1
    assert acceso.verificar(conn, "admin liga", "nueva123")


def test_codigo_no_se_cierra_sin_confirmar(app):
    dialogo = ui_acceso.DialogoCodigo(None, "AAAA-BBBB-CCCC")
    assert not dialogo.continuar.isEnabled()
    dialogo.show()
    dialogo.reject()
    assert dialogo.isVisible()
    dialogo.guardado.setChecked(True)
    assert dialogo.continuar.isEnabled()
    dialogo.reject()
    assert not dialogo.isVisible()


def test_cerrar_sesion_oculta_y_vuelve_o_sale(app, conn, cuenta, monkeypatch, tmp_path):
    from dep_leon import updater
    from dep_leon.ui import ventana as ui_ventana

    monkeypatch.setenv("DEP_LEON_DATA", str(tmp_path))
    monkeypatch.setattr(updater, "buscar", lambda actual: None)
    salidas = []
    monkeypatch.setattr(app, "quit", lambda: salidas.append(True))
    ventana = ui_ventana.Ventana(conn)
    ventana.show()

    visible_al_pedir = []

    def pedir(_):
        visible_al_pedir.append(ventana.isVisible())
        return True

    monkeypatch.setattr(ui_ventana, "pedir_acceso", pedir)
    ventana.config.cerrar_sesion.emit()
    assert visible_al_pedir == [False] and ventana.isVisible() and ventana.temporizador.isActive()

    monkeypatch.setattr(ui_ventana, "pedir_acceso", lambda _: False)
    ventana.config.cerrar_sesion.emit()
    assert salidas == [True] and not ventana.isVisible() and not ventana.temporizador.isActive()
    app.setQuitOnLastWindowClosed(True)
    ventana.close()
