"""Genera dep_leon/assets/hoja_registro.xlsx a partir de una hoja de registro llena.

Conserva el formato, las fórmulas y los escudos de la hoja «Cédula», y borra todo dato personal:
jugadores, CURP, fotos, personal del equipo y los metadatos del archivo (autor y rutas de imágenes).

Uso: python scripts/plantilla_registro.py <hoja_de_registro_llena.xlsx>
"""

import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dep_leon import registro  # noqa: E402

DESTINO = RAIZ / "dep_leon" / "assets" / registro.PLANTILLA


def main(origen: str) -> None:
    libro = load_workbook(origen)
    hoja = libro.worksheets[0]
    forma = registro.forma_de_plantilla(libro)

    for celda in ("C3", "C4", "C5"):
        hoja[celda].value = None
    for fila in range(forma.primer_renglon, forma.ultimo_renglon + 1):
        for columna in range(1, hoja.max_column + 1):
            if columna != 1:
                hoja.cell(row=fila, column=columna).value = None
    for fila in forma.personal.values():
        hoja.cell(row=fila, column=3).value = None

    cedula = libro[forma.hoja_cedula]
    fotos = set(forma.fotos.values())
    cedula._images = [
        im for im in cedula._images if (im.anchor._from.col, im.anchor._from.row) not in fotos
    ]

    libro.properties.creator = "Deportivo León"
    libro.properties.lastModifiedBy = "Deportivo León"
    libro.properties.created = libro.properties.modified = datetime(2026, 1, 1)
    libro.properties.lastPrinted = None
    libro.save(DESTINO)
    limpiar_dibujos(DESTINO)
    revisar(DESTINO)
    print(f"Plantilla guardada en {DESTINO}")


def limpiar_dibujos(ruta: Path) -> None:
    """Quita la descripción de cada imagen: Excel guarda ahí la ruta del archivo en la computadora del autor."""
    with zipfile.ZipFile(ruta) as archivo:
        partes = {n: archivo.read(n) for n in archivo.namelist()}
    for nombre, datos in partes.items():
        if nombre.startswith("xl/drawings/") and nombre.endswith(".xml"):
            partes[nombre] = re.sub(rb' descr="[^"]*"', b"", datos)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as archivo:
        for nombre, datos in partes.items():
            archivo.writestr(nombre, datos)


def revisar(ruta: Path) -> None:
    """Falla si queda algún rastro de datos personales en el archivo."""
    with zipfile.ZipFile(ruta) as archivo:
        for nombre in archivo.namelist():
            if nombre.endswith(".xml"):
                texto = archivo.read(nombre).decode("utf-8", "replace")
                assert "descr=" not in texto or "\\Users\\" not in texto, f"ruta de imagen en {nombre}"
                assert "Users" not in texto, f"posible ruta personal en {nombre}"


if __name__ == "__main__":
    main(sys.argv[1])
