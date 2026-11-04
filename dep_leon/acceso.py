"""Cuenta de acceso al programa.

Hay una sola cuenta por computadora. Como no hay correo para recuperarla, al crearla se entrega
un código de recuperación. Solo se guardan huellas (scrypt), nunca la contraseña ni el código.
"""

import hashlib
import hmac
import secrets
import sqlite3

LONGITUD_MINIMA = 6
_N, _R, _P = 2**14, 8, 1
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I, para copiarlo sin errores


def _huella(secreto: str, sal: bytes, n: int = _N, r: int = _R, p: int = _P) -> bytes:
    return hashlib.scrypt(secreto.encode("utf-8"), salt=sal, n=n, r=r, p=p, dklen=32)


def _proteger(secreto: str) -> str:
    sal = secrets.token_bytes(16)
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${_huella(secreto, sal).hex()}"


def _coincide(secreto: str, guardado: str) -> bool:
    _, n, r, p, sal, huella = guardado.split("$")
    calculada = _huella(secreto, bytes.fromhex(sal), int(n), int(r), int(p))
    return hmac.compare_digest(calculada, bytes.fromhex(huella))


def _nuevo_codigo() -> str:
    bloques = ("".join(secrets.choice(_ALFABETO) for _ in range(4)) for _ in range(3))
    return "-".join(bloques)


def _normalizar_codigo(codigo: str) -> str:
    return "".join(c for c in codigo.upper() if c.isalnum())


def _clave_usuario(usuario: str) -> str:
    return " ".join(usuario.split()).casefold()


def problema_con_contrasena(contrasena: str) -> str | None:
    if len(contrasena) < LONGITUD_MINIMA:
        return f"La contraseña debe tener al menos {LONGITUD_MINIMA} caracteres."
    return None


def hay_cuenta(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone() is not None


def nombre_usuario(conn: sqlite3.Connection) -> str:
    fila = conn.execute("SELECT usuario FROM usuarios LIMIT 1").fetchone()
    return fila["usuario"] if fila else ""


def crear_cuenta(conn: sqlite3.Connection, usuario: str, contrasena: str) -> str:
    """Crea la cuenta y devuelve el código de recuperación, que no se puede volver a consultar."""
    usuario = " ".join(usuario.split())
    if not usuario:
        raise ValueError("Escribe un nombre de usuario.")
    problema = problema_con_contrasena(contrasena)
    if problema:
        raise ValueError(problema)
    if hay_cuenta(conn):
        raise ValueError("Ya existe una cuenta en esta computadora.")
    codigo = _nuevo_codigo()
    with conn:
        conn.execute(
            "INSERT INTO usuarios (id, usuario, contrasena, codigo) VALUES (1, ?, ?, ?)",
            (usuario, _proteger(contrasena), _proteger(_normalizar_codigo(codigo))),
        )
    return codigo


def _cuenta(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM usuarios WHERE id = 1").fetchone()


def verificar(conn: sqlite3.Connection, usuario: str, contrasena: str) -> bool:
    cuenta = _cuenta(conn)
    if cuenta is None:
        return False
    # Se calcula siempre la huella para no delatar por tiempo cuál dato falló.
    correcta = _coincide(contrasena, cuenta["contrasena"])
    return correcta and _clave_usuario(usuario) == _clave_usuario(cuenta["usuario"])


def cambiar_contrasena(conn: sqlite3.Connection, actual: str, nueva: str) -> None:
    """Lanza ValueError si la contraseña actual es incorrecta o la nueva no es válida."""
    cuenta = _cuenta(conn)
    if cuenta is None or not _coincide(actual, cuenta["contrasena"]):
        raise ValueError("La contraseña actual no es correcta.")
    problema = problema_con_contrasena(nueva)
    if problema:
        raise ValueError(problema)
    with conn:
        conn.execute("UPDATE usuarios SET contrasena = ? WHERE id = 1", (_proteger(nueva),))


def recuperar(conn: sqlite3.Connection, codigo: str, nueva: str) -> str:
    """Pone una contraseña nueva con el código y entrega otro, porque cada código sirve una vez.

    Lanza ValueError si el código es incorrecto o la contraseña no es válida.
    """
    cuenta = _cuenta(conn)
    if cuenta is None or not _coincide(_normalizar_codigo(codigo), cuenta["codigo"]):
        raise ValueError("El código de recuperación no es correcto.")
    problema = problema_con_contrasena(nueva)
    if problema:
        raise ValueError(problema)
    siguiente = _nuevo_codigo()
    with conn:
        conn.execute(
            "UPDATE usuarios SET contrasena = ?, codigo = ? WHERE id = 1",
            (_proteger(nueva), _proteger(_normalizar_codigo(siguiente))),
        )
    return siguiente
