import hashlib
import io
import json
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


def test_descarga_verifica_la_huella(monkeypatch):
    huella = hashlib.sha256(b"programa").hexdigest()
    simular(monkeypatch, {"http://x/exe": b"programa", "http://x/sha": f"{huella}  x.exe\n".encode()})
    assert updater.descargar(ACTUALIZACION).read_bytes() == b"programa"


def test_descarga_alterada_se_rechaza_y_borra(monkeypatch, tmp_path):
    monkeypatch.setattr(updater.tempfile, "mkdtemp", lambda prefix: str(tmp_path))
    simular(monkeypatch, {"http://x/exe": b"alterado", "http://x/sha": b"0" * 64})
    with pytest.raises(ValueError):
        updater.descargar(ACTUALIZACION)
    assert not (tmp_path / updater.NOMBRE_EXE).exists()
