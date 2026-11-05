import hashlib
import io
import json
import os
import threading
import urllib.error

import pytest

from dep_leon import updater


@pytest.mark.parametrize(
    "candidata, actual, esperado",
    [
        ("v0.2.0", "0.1.0", True),
        ("0.10.0", "0.9.0", True),
        ("v0.1.0", "0.1.0", False),
        ("0.1", "0.1.0", False),
        ("0.0.9", "0.1.0", False),
        ("v1.0-beta", "0.1.0", False),
        ("", "0.1.0", False),
    ],
)
def test_compara_versiones(candidata, actual, esperado):
    assert updater.es_mas_nueva(candidata, actual) is esperado


class Respuesta(io.BytesIO):
    pass


def simular(monkeypatch, respuestas):
    def abrir(url, tiempo):
        valor = respuestas[url]
        if isinstance(valor, Exception):
            raise valor
        return Respuesta(valor)

    monkeypatch.setattr(updater, "_abrir", abrir)


def version_publicada(**extra):
    return json.dumps({
        "tag_name": "v0.2.0",
        "body": "Notas",
        "assets": [
            {"name": updater.NOMBRE_EXE, "browser_download_url": "http://x/exe"},
            {"name": f"{updater.NOMBRE_EXE}.sha256", "browser_download_url": "http://x/sha"},
        ],
        **extra,
    }).encode()


def test_sin_internet_lanza_sin_conexion(monkeypatch):
    simular(monkeypatch, {updater.URL_ULTIMA: urllib.error.URLError("sin red")})
    with pytest.raises(updater.SinConexion):
        updater.buscar("0.1.0")


def test_sin_versiones_publicadas_no_hay_actualizacion(monkeypatch):
    error = urllib.error.HTTPError(updater.URL_ULTIMA, 404, "", None, None)
    simular(monkeypatch, {updater.URL_ULTIMA: error})
    assert updater.buscar("0.1.0") is None


def test_encuentra_version_nueva(monkeypatch):
    simular(monkeypatch, {updater.URL_ULTIMA: version_publicada()})
    encontrada = updater.buscar("0.1.0")
    assert (encontrada.version, encontrada.notas) == ("0.2.0", "Notas")


def test_ignora_version_igual_y_publicacion_sin_archivos(monkeypatch):
    simular(monkeypatch, {updater.URL_ULTIMA: version_publicada()})
    assert updater.buscar("0.2.0") is None
    simular(monkeypatch, {updater.URL_ULTIMA: version_publicada(assets=[])})
    assert updater.buscar("0.1.0") is None


ACTUALIZACION = updater.Actualizacion("0.2.0", "", "http://x/exe", "http://x/sha")


@pytest.fixture
def temporal(monkeypatch, tmp_path):
    carpeta = tmp_path / "descarga"
    carpeta.mkdir()
    monkeypatch.setattr(updater.tempfile, "mkdtemp", lambda prefix: str(carpeta))
    return carpeta


def con_huella(contenido: bytes) -> dict:
    huella = hashlib.sha256(contenido).hexdigest()
    return {"http://x/exe": contenido, "http://x/sha": f"{huella}  x.exe\n".encode()}


def test_descarga_verifica_la_huella(monkeypatch, temporal):
    simular(monkeypatch, con_huella(b"programa"))
    assert updater.descargar(ACTUALIZACION).read_bytes() == b"programa"


def test_descarga_alterada_se_rechaza_y_borra(monkeypatch, temporal):
    simular(monkeypatch, {"http://x/exe": b"alterado", "http://x/sha": b"0" * 64})
    with pytest.raises(ValueError):
        updater.descargar(ACTUALIZACION)
    assert not temporal.exists()


def test_descarga_informa_el_avance_con_total(monkeypatch, temporal):
    contenido = b"x" * (updater.BLOQUE * 2 + 10)

    class ConTotal(Respuesta):
        headers = {"Content-Length": str(len(contenido))}

    def abrir(url, tiempo):
        return ConTotal(con_huella(contenido)[url])

    monkeypatch.setattr(updater, "_abrir", abrir)
    avances = []
    updater.descargar(ACTUALIZACION, lambda r, t: avances.append((r, t)))
    assert avances[-1] == (len(contenido), len(contenido))
    assert len(avances) == 3


def test_descarga_sin_total_tambien_avanza(monkeypatch, temporal):
    simular(monkeypatch, con_huella(b"programa"))
    avances = []
    updater.descargar(ACTUALIZACION, lambda r, t: avances.append((r, t)))
    assert avances == [(8, 0)]


def test_cancelar_detiene_y_no_deja_archivos(monkeypatch, temporal):
    simular(monkeypatch, con_huella(b"programa"))
    cancelar = threading.Event()
    cancelar.set()
    with pytest.raises(updater.Cancelada):
        updater.descargar(ACTUALIZACION, cancelar=cancelar)
    assert not temporal.exists()


def test_conexion_perdida_a_media_descarga(monkeypatch, temporal):
    class Cortada(Respuesta):
        def read(self, *a):
            raise TimeoutError("sin datos")

    respuestas = con_huella(b"programa")

    def abrir(url, tiempo):
        if url == "http://x/exe":
            assert tiempo == updater.TIEMPO_DESCARGA
            return Cortada()
        return Respuesta(respuestas[url])

    monkeypatch.setattr(updater, "_abrir", abrir)
    with pytest.raises(updater.SinConexion):
        updater.descargar(ACTUALIZACION)
    assert not temporal.exists()


@pytest.fixture
def instalacion(tmp_path):
    carpeta = tmp_path / "Mis programás"
    carpeta.mkdir()
    exe = carpeta / "DeportivoLeon-0.9.0.exe"
    exe.write_bytes(b"viejo")
    descarga = tmp_path / "descarga"
    descarga.mkdir()
    nuevo = descarga / updater.NOMBRE_EXE
    nuevo.write_bytes(b"nuevo")
    return exe, nuevo


def test_reemplazar_conserva_el_nombre_y_guarda_el_anterior(instalacion):
    exe, nuevo = instalacion
    anterior = updater.reemplazar(nuevo, exe)
    assert exe.read_bytes() == b"nuevo"
    assert anterior.read_bytes() == b"viejo"
    assert not exe.with_name(exe.name + updater.SUFIJO_NUEVO).exists()


def test_reemplazar_falla_al_copiar_y_no_toca_nada(instalacion, monkeypatch):
    exe, nuevo = instalacion

    def falla(*a):
        raise PermissionError("sin permiso")

    monkeypatch.setattr(updater.shutil, "copyfile", falla)
    with pytest.raises(OSError):
        updater.reemplazar(nuevo, exe)
    assert exe.read_bytes() == b"viejo"


def test_reemplazar_falla_al_final_y_regresa_el_anterior(instalacion, monkeypatch):
    exe, nuevo = instalacion
    original = os.replace
    llamadas = []

    def falla_la_segunda(a, b):
        llamadas.append(a)
        if len(llamadas) == 2:
            raise PermissionError("bloqueado")
        original(a, b)

    monkeypatch.setattr(updater.os, "replace", falla_la_segunda)
    with pytest.raises(OSError):
        updater.reemplazar(nuevo, exe)
    assert exe.read_bytes() == b"viejo"
    assert [a.name for a in exe.parent.iterdir()] == [exe.name]


def test_instalar_abre_el_nuevo_y_limpia_la_descarga(instalacion, monkeypatch):
    exe, nuevo = instalacion
    abiertos = []
    monkeypatch.setattr(updater, "abrir_programa", abiertos.append)
    updater.instalar_y_abrir(nuevo, exe)
    assert abiertos == [exe] and exe.read_bytes() == b"nuevo"
    assert not nuevo.parent.exists()


def test_si_no_abre_regresa_a_la_version_anterior(instalacion, monkeypatch):
    exe, nuevo = instalacion

    def falla(_):
        raise OSError("bloqueado por el antivirus")

    monkeypatch.setattr(updater, "abrir_programa", falla)
    with pytest.raises(OSError):
        updater.instalar_y_abrir(nuevo, exe)
    assert exe.read_bytes() == b"viejo"
    assert [a.name for a in exe.parent.iterdir()] == [exe.name]


def test_no_quedan_procesos_auxiliares():
    """La versión con script .bat se atoraba para siempre esperando a tasklist."""
    assert not hasattr(updater, "script_reemplazo")
    assert not hasattr(updater, "instalar_y_cerrar")


def test_limpiar_restos_borra_solo_lo_de_la_actualizacion(tmp_path):
    programa = tmp_path / "programa"
    programa.mkdir()
    exe = programa / "Deportivo.exe"
    exe.write_bytes(b"actual")
    (programa / "Deportivo.exe.anterior.123").write_bytes(b"viejo")
    (programa / "Deportivo.exe.nuevo").write_bytes(b"incompleto")
    (programa / "Otro.exe.anterior.5").write_bytes(b"ajeno")

    temp = tmp_path / "temp"
    temp.mkdir()
    vieja = temp / "DeportivoLeon-abc"
    vieja.mkdir()
    (vieja / "actualizar.bat").write_text("x")
    (vieja / updater.NOMBRE_EXE).write_bytes(b"x")
    os.utime(vieja, (1, 1))
    reciente = temp / "DeportivoLeon-reciente"
    reciente.mkdir()
    (reciente / updater.NOMBRE_EXE).write_bytes(b"x")
    ajena = temp / "DeportivoLeon-ajena"
    ajena.mkdir()
    (ajena / "liga.db").write_bytes(b"x")
    os.utime(ajena, (1, 1))

    updater.limpiar_restos(exe, temp, intentos=1)

    assert sorted(a.name for a in programa.iterdir()) == ["Deportivo.exe", "Otro.exe.anterior.5"]
    assert sorted(a.name for a in temp.iterdir()) == ["DeportivoLeon-ajena", "DeportivoLeon-reciente"]
