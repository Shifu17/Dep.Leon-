"""Actualizaciones desde GitHub Releases.

Sin internet no ocurre nada. Si hay una versión nueva, se avisa y solo se instala cuando el
usuario acepta; el ejecutable descargado debe coincidir con la huella SHA-256 publicada.

Windows no deja sobrescribir un .exe en uso, pero sí renombrarlo. Por eso la instalación se hace
desde el propio programa, sin procesos auxiliares que esperen a que cierre: renombra el .exe actual,
pone el nuevo en su lugar y lo abre. Si algo falla, deja todo como estaba.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO = "Shifu17/Dep.Leon-"
URL_ULTIMA = f"https://api.github.com/repos/{REPO}/releases/latest"
NOMBRE_EXE = "DeportivoLeon.exe"
AGENTE = "DeportivoLeon-actualizador"
TIEMPO_ESPERA = 10
TIEMPO_DESCARGA = 30  # segundos sin recibir datos antes de dar la conexión por perdida
BLOQUE = 1024 * 256
SUFIJO_NUEVO = ".nuevo"
SUFIJO_ANTERIOR = ".anterior"
PREFIJO_TEMPORAL = "DeportivoLeon-"
ARCHIVOS_DE_DESCARGA = {NOMBRE_EXE, "actualizar.bat"}
HORAS_PARA_LIMPIAR = 1


class SinConexion(Exception):
    """No se pudo contactar el servidor de actualizaciones."""


class Cancelada(Exception):
    """Quien usa el programa canceló la descarga."""


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


def descargar(
    actualizacion: Actualizacion,
    progreso: Callable[[int, int], None] | None = None,
    cancelar: threading.Event | None = None,
) -> Path:
    """Descarga y verifica el ejecutable, y devuelve su ruta en una carpeta temporal.

    progreso recibe (bytes recibidos, bytes totales; 0 si el total no se conoce). Lanza
    SinConexion, Cancelada o ValueError, y en esos casos no deja archivos.
    """
    carpeta = Path(tempfile.mkdtemp(prefix=PREFIJO_TEMPORAL))
    destino = carpeta / NOMBRE_EXE
    huella = hashlib.sha256()
    try:
        try:
            with _abrir(actualizacion.url_huella, TIEMPO_ESPERA) as respuesta:
                esperada = respuesta.read(1024).decode("ascii", "ignore").split()[0].lower()
            with _abrir(actualizacion.url_exe, TIEMPO_DESCARGA) as respuesta, destino.open("wb") as salida:
                encabezados = getattr(respuesta, "headers", None)
                total = int(encabezados.get("Content-Length") or 0) if encabezados else 0
                recibido = 0
                while bloque := respuesta.read(BLOQUE):
                    if cancelar is not None and cancelar.is_set():
                        raise Cancelada
                    huella.update(bloque)
                    salida.write(bloque)
                    recibido += len(bloque)
                    if progreso:
                        progreso(recibido, total)
        except (OSError, IndexError) as exc:
            raise SinConexion(str(exc)) from exc
        if huella.hexdigest() != esperada:
            raise ValueError("La descarga no coincide con la huella publicada; no se instaló.")
    except Exception:
        shutil.rmtree(carpeta, ignore_errors=True)
        raise
    return destino


def reemplazar(nuevo: Path, exe: Path) -> Path:
    """Pone el .exe nuevo en lugar del actual, que sigue en uso, y devuelve la ruta del anterior.

    Lanza OSError si la carpeta no lo permite; en ese caso el .exe actual queda intacto.
    """
    provisional = exe.with_name(exe.name + SUFIJO_NUEVO)
    anterior = exe.with_name(f"{exe.name}{SUFIJO_ANTERIOR}.{os.getpid()}")
    shutil.copyfile(nuevo, provisional)
    try:
        if provisional.stat().st_size != nuevo.stat().st_size:
            raise OSError("La copia de la actualización quedó incompleta.")
        os.replace(exe, anterior)
        try:
            os.replace(provisional, exe)
        except OSError:
            os.replace(anterior, exe)
            raise
    except OSError:
        provisional.unlink(missing_ok=True)
        raise
    return anterior


def deshacer(exe: Path, anterior: Path) -> None:
    """Regresa el .exe anterior a su lugar."""
    exe.unlink(missing_ok=True)
    os.replace(anterior, exe)


def abrir_programa(exe: Path) -> None:
    # Hace que el .exe reabierto sea una instancia independiente de esta (PyInstaller).
    entorno = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    subprocess.Popen(
        [str(exe)],
        cwd=str(exe.parent),
        env=entorno,
        creationflags=subprocess.DETACHED_PROCESS,
        close_fds=True,
    )


def instalar_y_abrir(nuevo: Path, exe: Path | None = None) -> None:
    """Instala la versión descargada y la abre; quien llama debe cerrar el programa enseguida.

    Lanza OSError si no se pudo; en ese caso sigue instalada la versión actual.
    """
    exe = exe or Path(sys.executable)
    anterior = reemplazar(nuevo, exe)
    try:
        abrir_programa(exe)
    except OSError:
        deshacer(exe, anterior)
        raise
    shutil.rmtree(nuevo.parent, ignore_errors=True)


def limpiar_restos(
    exe: Path | None = None, temporal: Path | None = None, intentos: int = 15, espera: float = 1.0
) -> None:
    """Borra lo que dejó una actualización: el .exe anterior y descargas abandonadas.

    El .exe anterior se libera cuando termina de cerrarse la versión vieja, por eso se reintenta.
    """
    exe = exe or Path(sys.executable)
    temporal = temporal or Path(tempfile.gettempdir())
    limite = time.time() - HORAS_PARA_LIMPIAR * 3600
    for carpeta in temporal.glob(f"{PREFIJO_TEMPORAL}*"):
        try:
            if (
                carpeta.is_dir()
                and carpeta.stat().st_mtime < limite
                and {a.name for a in carpeta.iterdir()} <= ARCHIVOS_DE_DESCARGA
            ):
                shutil.rmtree(carpeta, ignore_errors=True)
        except OSError:
            continue
    for intento in range(intentos):
        restantes = []
        for archivo in [*exe.parent.glob(f"{exe.name}{SUFIJO_ANTERIOR}*"), exe.with_name(exe.name + SUFIJO_NUEVO)]:
            try:
                archivo.unlink(missing_ok=True)
            except OSError:
                restantes.append(archivo)
        if not restantes:
            return
        if intento < intentos - 1:
            time.sleep(espera)


def puede_instalar() -> bool:
    return bool(getattr(sys, "frozen", False))
