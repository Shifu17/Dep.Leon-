"""Credenciales de juego en PDF, con el mismo acomodo que la hoja «Cédula» de los clubes.

Cada credencial es una cuadrícula de 4 columnas por 13 renglones, como en el Excel:
escudos y título arriba; la foto a la izquierda con la fecha de nacimiento abajo; el nombre en grande,
la CURP, el club, la categoría y el número de playera; «JUGADOR» en amarillo con la rama; entrenador y
director general; y una franja negra al pie. Caben 10 por hoja carta, con una línea gris para recortar.
"""

import sqlite3
from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .paths import asset

ANCHO = 95 * mm
ALTO = 51 * mm
COLUMNAS = 2
FILAS = 5
SEPARACION = 3 * mm

# Proporciones de la cédula original: anchos de columna A-D y altos de los 13 renglones.
_ANCHOS = [81, 96, 96, 96]
_ALTOS = [12, 12, 12, 11.4, 12, 11.25, 11.25, 12, 12, 12, 10.5, 12, 10.5]
AMARILLO = HexColor("#FFFF00")
GRIS_CORTE = HexColor("#B8B8B8")
CIUDAD = "SALTILLO, COAHUILA"


def rama(texto: str) -> str:
    """FEMENIL si la liga o la categoría lo dicen; si no, VARONIL."""
    return "FEMENIL" if "femenil" in texto.casefold() else "VARONIL"


def generar(conn: sqlite3.Connection, equipo_id: int, destino: Path | str, fotos_dir: Path) -> int:
    """Genera las credenciales del equipo y devuelve cuántas se crearon."""
    equipo = conn.execute(
        """SELECT e.*, c.nombre AS categoria, t.nombre AS torneo, l.nombre AS liga
           FROM equipos e JOIN categorias c ON c.id = e.categoria_id
           JOIN torneos t ON t.id = e.torneo_id JOIN ligas l ON l.id = t.liga_id WHERE e.id = ?""",
        (equipo_id,),
    ).fetchone()
    jugadores = conn.execute(
        "SELECT * FROM jugadores WHERE equipo_id = ? ORDER BY numero IS NULL, numero, nombre COLLATE ES",
        (equipo_id,),
    ).fetchall()

    pdf = canvas.Canvas(str(destino), pagesize=letter)
    pdf.setTitle(f"Credenciales {equipo['nombre']}")
    ancho_hoja, alto_hoja = letter
    margen_x = (ancho_hoja - COLUMNAS * ANCHO - (COLUMNAS - 1) * SEPARACION) / 2
    margen_y = (alto_hoja - FILAS * ALTO - (FILAS - 1) * SEPARACION) / 2
    por_hoja = COLUMNAS * FILAS
    escudo = ImageReader(str(asset("escudo.png")))

    for i, jugador in enumerate(jugadores):
        if i and i % por_hoja == 0:
            pdf.showPage()
        posicion = i % por_hoja
        x = margen_x + (posicion % COLUMNAS) * (ANCHO + SEPARACION)
        y = alto_hoja - margen_y - ALTO - (posicion // COLUMNAS) * (ALTO + SEPARACION)
        _dibujar(pdf, x, y, jugador, equipo, fotos_dir, escudo)

    pdf.save()
    return len(jugadores)


class _Rejilla:
    """Convierte celdas de la cédula (columna 0-3, renglón 0-12) en rectángulos de la tarjeta."""

    def __init__(self, x: float, y: float):
        total_ancho, total_alto = sum(_ANCHOS), sum(_ALTOS)
        self.xs = [x]
        for a in _ANCHOS:
            self.xs.append(self.xs[-1] + a * ANCHO / total_ancho)
        self.ys = [y + ALTO]  # de arriba hacia abajo
        for a in _ALTOS:
            self.ys.append(self.ys[-1] - a * ALTO / total_alto)

    def caja(self, col1: int, ren1: int, col2: int | None = None, ren2: int | None = None):
        """(x, y, ancho, alto) de las celdas combinadas col1..col2 x ren1..ren2."""
        col2 = col1 if col2 is None else col2
        ren2 = ren1 if ren2 is None else ren2
        x, x2 = self.xs[col1], self.xs[col2 + 1]
        arriba, abajo = self.ys[ren1], self.ys[ren2 + 1]
        return x, abajo, x2 - x, arriba - abajo


def _texto(pdf, caja, texto: str, fuente: str, tamano: float, color=black) -> None:
    """Texto centrado en la caja; si no cabe, se achica y al final se recorta."""
    x, y, ancho, alto = caja
    texto = texto or ""
    while tamano > 5 and pdf.stringWidth(texto, fuente, tamano) > ancho - 1.5 * mm:
        tamano -= 0.5
    texto = _ajustar(pdf, texto, fuente, tamano, ancho - 1.5 * mm)
    pdf.setFillColor(color)
    pdf.setFont(fuente, tamano)
    pdf.drawCentredString(x + ancho / 2, y + (alto - tamano * 0.72) / 2, texto)


def _nombre(pdf, caja, nombre: str) -> None:
    """El nombre ocupa cuatro renglones de la cédula: va en una o dos líneas, grande."""
    x, y, ancho, alto = caja
    fuente, tamano = "Helvetica-Bold", 12
    palabras = nombre.split()
    if pdf.stringWidth(nombre, fuente, tamano) <= ancho - 2 * mm or len(palabras) < 2:
        _texto(pdf, caja, nombre, fuente, tamano)
        return
    # Dos líneas tan parejas como se pueda.
    mejor = min(
        range(1, len(palabras)),
        key=lambda i: abs(len(" ".join(palabras[:i])) - len(" ".join(palabras[i:]))),
    )
    lineas = [" ".join(palabras[:mejor]), " ".join(palabras[mejor:])]
    while tamano > 7 and max(pdf.stringWidth(l, fuente, tamano) for l in lineas) > ancho - 2 * mm:
        tamano -= 0.5
    pdf.setFillColor(black)
    pdf.setFont(fuente, tamano)
    centro = y + alto / 2
    for i, linea in enumerate(lineas):
        base = centro + (0.15 if i == 0 else -1.0) * tamano
        pdf.drawCentredString(x + ancho / 2, base, _ajustar(pdf, linea, fuente, tamano, ancho - 2 * mm))


def _dibujar(pdf: canvas.Canvas, x: float, y: float, jugador, equipo, fotos_dir: Path, escudo) -> None:
    r = _Rejilla(x, y)
    pdf.setStrokeColor(GRIS_CORTE)
    pdf.setLineWidth(0.4)
    pdf.rect(x, y, ANCHO, ALTO, fill=0)

    # Renglones 1 y 2: escudos a los lados y el título al centro.
    for col in (0, 3):
        ex, ey, ea, eh = r.caja(col, 0, col, 1)
        pdf.drawImage(escudo, ex + 1 * mm, ey + 0.5 * mm, ea - 2 * mm, eh - 1 * mm,
                      preserveAspectRatio=True, anchor="c", mask="auto")
    _texto(pdf, r.caja(0, 0, 3, 0), "Deportivo León Saltillo A.C.", "Times-Bold", 10)
    _texto(pdf, r.caja(0, 1, 3, 1), "Credenciales de Juego", "Times-Bold", 10)

    # Foto: columna A, renglones 3 a 8.
    fx, fy, fa, fh = r.caja(0, 2, 0, 7)
    fx, fy, fa, fh = fx + 1 * mm, fy + 0.5 * mm, fa - 2 * mm, fh - 1 * mm
    ruta_foto = fotos_dir / jugador["foto"] if jugador["foto"] else None
    if ruta_foto and ruta_foto.is_file():
        pdf.drawImage(ImageReader(str(ruta_foto)), fx, fy, fa, fh, preserveAspectRatio=True, anchor="c")
    else:
        pdf.setStrokeColor(GRIS_CORTE)
        pdf.rect(fx, fy, fa, fh, fill=0)
        _texto(pdf, (fx, fy, fa, fh), "FOTO", "Helvetica", 9)

    _nombre(pdf, r.caja(1, 2, 3, 5), jugador["nombre"])
    _texto(pdf, r.caja(1, 6, 3, 6), jugador["curp"], "Helvetica-Bold", 9)
    _texto(pdf, r.caja(1, 7, 3, 7), equipo["nombre"], "Helvetica-Bold", 9)

    nacimiento = date.fromisoformat(jugador["fecha_nacimiento"]).strftime("%d/%m/%Y")
    _texto(pdf, r.caja(0, 8), nacimiento, "Helvetica-Bold", 8)
    _texto(pdf, r.caja(1, 8, 2, 8), equipo["categoria"].upper(), "Helvetica-Bold", 9)
    _texto(pdf, r.caja(3, 8), "# Playera", "Helvetica", 9)

    ax, ay, aa, ah = r.caja(0, 9)
    pdf.setFillColor(AMARILLO)
    pdf.rect(ax, ay, aa, ah, fill=1, stroke=0)
    _texto(pdf, (ax, ay, aa, ah), "JUGADOR", "Helvetica-Bold", 9)
    _texto(pdf, r.caja(1, 9, 2, 9), rama(f"{equipo['liga']} {equipo['categoria']}"), "Helvetica-Bold", 9)
    numero = "" if jugador["numero"] is None else str(jugador["numero"])
    _texto(pdf, r.caja(3, 9), numero, "Helvetica-Bold", 10)

    _texto(pdf, r.caja(0, 10, 1, 10), "Entrenador", "Helvetica", 8)
    _texto(pdf, r.caja(2, 10, 3, 10), "Dir. Gral.", "Helvetica", 8)
    _texto(pdf, r.caja(0, 11, 1, 11), equipo["responsable"], "Helvetica-Bold", 8)
    _texto(pdf, r.caja(2, 11, 3, 11), equipo["director"], "Helvetica-Bold", 8)

    px, py, pa, ph = r.caja(0, 12, 3, 12)
    pdf.setFillColor(black)
    pdf.rect(px, py, pa, ph, fill=1, stroke=0)
    _texto(pdf, (px, py, pa, ph), pie(equipo["torneo"]), "Helvetica-Bold", 8, white)


def pie(torneo: str) -> str:
    """Franja inferior: la ciudad y el torneo, en lugar de una temporada fija."""
    return f"{CIUDAD} · {torneo.upper()}"


def _ajustar(pdf: canvas.Canvas, texto: str, fuente: str, tamano: float, ancho: float) -> str:
    """Recorta con puntos suspensivos el texto que no cabe."""
    if pdf.stringWidth(texto, fuente, tamano) <= ancho:
        return texto
    while texto and pdf.stringWidth(texto + "...", fuente, tamano) > ancho:
        texto = texto[:-1]
    return texto + "..."
