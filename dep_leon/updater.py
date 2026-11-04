"""Actualizaciones desde GitHub Releases.

Sin internet no ocurre nada. Si hay una versión nueva, se avisa y solo se instala cuando el
usuario acepta; el ejecutable descargado debe coincidir con la huella SHA-256 publicada.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO = "Shifu17/Dep.Leon-"
URL_ULTIMA = f"https://api.github.com/repos/{REPO}/releases/latest"
NOMBRE_EXE = "DeportivoLeon.exe"
AGENTE = "DeportivoLeon-actualizador"
TIEMPO_ESPERA = 10
TIEMPO_DESCARGA = 300


class SinConexion(Exception):
    """No se pudo contactar el servidor de actualizaciones."""


@dataclass(frozen=True)
class Actualizacion:
    version: str
    notas: str
    url_exe: str
    url_huella: str


def _version(texto: str) -> tuple[int, ...] | None:
    coincidencia = re.fullmatch(r"v?(\d+(?:\.\d+)*)", texto.strip())
    return tuple(int(p) for p in coincidencia.group(1).split(".")) if coincidencia else None


def es_mas_nueva(candidata: str, actual: str) -> bool:
    nueva, vigente = _version(candidata), _version(actual)
    if nueva is None or vigente is None:
        return False
    largo = max(len(nueva), len(vigente))
    return nueva + (0,) * (largo - len(nueva)) > vigente + (0,) * (largo - len(vigente))


def _abrir(url: str, tiempo: int):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": AGENTE}), timeout=tiempo
    )


def buscar(actual: str) -> Actualizacion | None:
    """Devuelve la actualización disponible, o None si no hay. Lanza SinConexion sin internet."""
    try:
        with _abrir(URL_ULTIMA, TIEMPO_ESPERA) as respuesta:
            datos = json.load(respuesta)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:  # todavía no hay versiones publicadas
            return None
        raise SinConexion(str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise SinConexion(str(exc)) from exc

    version = str(datos.get("tag_name", ""))
    if not es_mas_nueva(version, actual):
        return None
    archivos = {a.get("name"): a.get("browser_download_url") for a in datos.get("assets", [])}
    url_exe = archivos.get(NOMBRE_EXE)
    url_huella = archivos.get(f"{NOMBRE_EXE}.sha256")
    if not url_exe or not url_huella:
        return None
    return Actualizacion(version.lstrip("v"), str(datos.get("body") or ""), url_exe, url_huella)


def descargar(actualizacion: Actualizacion) -> Path:
    """Descarga y verifica el ejecutable. Lanza SinConexion o ValueError si algo falla."""
    carpeta = Path(tempfile.mkdtemp(prefix="DeportivoLeon-"))
    destino = carpeta / NOMBRE_EXE
    huella = hashlib.sha256()
    try:
        with _abrir(actualizacion.url_huella, TIEMPO_ESPERA) as respuesta:
            esperada = respuesta.read(1024).decode("ascii", "ignore").split()[0].lower()
        with _abrir(actualizacion.url_exe, TIEMPO_DESCARGA) as respuesta, destino.open("wb") as salida:
            while bloque := respuesta.read(1024 * 256):
                huella.update(bloque)
                salida.write(bloque)
    except (OSError, IndexError) as exc:
        raise SinConexion(str(exc)) from exc
    if huella.hexdigest() != esperada:
        destino.unlink(missing_ok=True)
        raise ValueError("La descarga no coincide con la huella publicada; no se instaló.")
    return destino


def script_reemplazo(nuevo: Path, actual: Path, pid: int) -> str:
    """Script que espera a que el programa cierre, reemplaza el .exe y lo vuelve a abrir."""
    return f"""@echo off
chcp 65001 >nul
:esperar
"%SystemRoot%\\System32\\tasklist.exe" /FI "PID eq {pid}" /NH | "%SystemRoot%\\System32\\find.exe" "{pid}" >nul
if not errorlevel 1 (
  ping -n 2 127.0.0.1 >nul
  goto esperar
)
set intentos=0
:mover
move /y "{nuevo}" "{actual}" >nul 2>&1
if not errorlevel 1 goto abrir
set /a intentos+=1
if %intentos% geq 15 goto abrir
ping -n 2 127.0.0.1 >nul
goto mover
:abrir
start "" "{actual}"
del "%~f0"
"""


def instalar_y_cerrar(nuevo: Path) -> None:
    """Lanza el reemplazo en segundo plano; quien llama debe cerrar el programa enseguida."""
    script = nuevo.parent / "actualizar.bat"
    script.write_text(
        script_reemplazo(nuevo, Path(sys.executable), os.getpid()), encoding="utf-8"
    )
    # Hace que el .exe reabierto sea una instancia independiente de esta (PyInstaller).
    entorno = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    subprocess.Popen(
        ["cmd", "/c", str(script)],
        env=entorno,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )


def puede_instalar() -> bool:
    return bool(getattr(sys, "frozen", False))
