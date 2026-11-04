"""Credenciales de jugadores en PDF, tamaño tarjeta, para imprimir en hoja carta."""

import sqlite3
from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .paths import asset

ANCHO = 85.6 * mm
ALTO = 54 * mm
COLUMNAS = 2
FILAS = 4
SEPARACION = 4 * mm

AMBAR = HexColor("#FFC000")
VERDE = HexColor("#00C800")
LAVANDA = HexColor("#E9EDF4")
AZUL = HexColor("#1F5FA8")


def generar(conn: sqlite3.Connection, equipo_id: int, destino: Path | str, fotos_dir: Path) -> int:
    """Genera las credenciales del equipo y devuelve cuántas se crearon."""
    equipo = conn.execute(
        """SELECT e.nombre, c.nombre AS categoria, t.nombre AS torneo
           FROM equipos e JOIN categorias c ON c.id = e.categoria_id
           JOIN torneos t ON t.id = e.torneo_id WHERE e.id = ?""",
        (equipo_id,),
    ).fetchone()
    jugadores = conn.execute(
        "SELECT * FROM jugadores WHERE equipo_id = ? ORDER BY numero", (equipo_id,)
    ).fetchall()

    pdf = canvas.Canvas(str(destino), pagesize=letter)
    pdf.setTitle(f"Credenciales {equipo['nombre']}")
    ancho_hoja, alto_hoja = letter
    margen_x = (ancho_hoja - COLUMNAS * ANCHO - (COLUMNAS - 1) * SEPARACION) / 2
    margen_y = (alto_hoja - FILAS * ALTO - (FILAS - 1) * SEPARACION) / 2
    por_hoja = COLUMNAS * FILAS

    for i, jugador in enumerate(jugadores):
        if i and i % por_hoja == 0:
            pdf.showPage()
        posicion = i % por_hoja
        x = margen_x + (posicion % COLUMNAS) * (ANCHO + SEPARACION)
        y = alto_hoja - margen_y - ALTO - (posicion // COLUMNAS) * (ALTO + SEPARACION)
        _dibujar(pdf, x, y, jugador, equipo, fotos_dir)

    pdf.save()
    return len(jugadores)


def _dibujar(pdf: canvas.Canvas, x: float, y: float, jugador, equipo, fotos_dir: Path) -> None:
    pdf.setFillColor(AMBAR)
    pdf.setStrokeColor(black)
    pdf.rect(x, y, ANCHO, ALTO, fill=1)
    margen = 1.5 * mm
    pdf.setFillColor(LAVANDA)
    pdf.rect(x + margen, y + margen, ANCHO - 2 * margen, ALTO - 2 * margen, fill=1, stroke=0)

    alto_encabezado = 13 * mm
    tope = y + ALTO - margen
    pdf.setFillColor(black)
    pdf.rect(x + margen, tope - alto_encabezado, ANCHO - 2 * margen, alto_encabezado, fill=1, stroke=0)
    pdf.drawImage(
        ImageReader(str(asset("logo_futbol7.png"))),
        x + margen + 0.5 * mm, tope - alto_encabezado + 0.5 * mm,
        12 * mm, alto_encabezado - 1 * mm, preserveAspectRatio=True,
    )
    pdf.drawImage(
        ImageReader(str(asset("banner_deportivo_leon.png"))),
        x + margen + 13 * mm, tope - alto_encabezado + 0.5 * mm,
        ANCHO - 2 * margen - 14 * mm, alto_encabezado - 1 * mm, preserveAspectRatio=True,
    )

    alto_franja = 5 * mm
    pdf.setFillColor(VERDE)
    pdf.rect(x + margen, tope - alto_encabezado - alto_franja, ANCHO - 2 * margen, alto_franja, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(
        x + ANCHO / 2, tope - alto_encabezado - alto_franja + 1.5 * mm,
        _ajustar(pdf, equipo["torneo"], "Helvetica-Bold", 8, ANCHO - 4 * mm),
    )

    foto_ancho, foto_alto = 22 * mm, 27 * mm
    foto_x = x + margen + 1.5 * mm
    foto_y = y + margen + 1.5 * mm
    ruta_foto = fotos_dir / jugador["foto"] if jugador["foto"] else None
    pdf.setFillColor(white)
    pdf.rect(foto_x, foto_y, foto_ancho, foto_alto, fill=1)
    if ruta_foto and ruta_foto.is_file():
        pdf.drawImage(
            ImageReader(str(ruta_foto)), foto_x, foto_y, foto_ancho, foto_alto,
            preserveAspectRatio=True, anchor="c",
        )
    else:
        pdf.setFillColor(black)
        pdf.setFont("Helvetica", 7)
        pdf.drawCentredString(foto_x + foto_ancho / 2, foto_y + foto_alto / 2, "Sin foto")

    texto_x = foto_x + foto_ancho + 2 * mm
    texto_ancho = x + ANCHO - margen - 1.5 * mm - texto_x
    linea = foto_y + foto_alto - 4 * mm
    pdf.setFillColor(AZUL)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(texto_x, linea, _ajustar(pdf, jugador["nombre"], "Helvetica-Bold", 10, texto_ancho))
    linea -= 5.5 * mm
    pdf.setFillColor(black)
    nacimiento = date.fromisoformat(jugador["fecha_nacimiento"]).strftime("%d/%m/%Y")
    for titulo, valor in (
        ("Equipo", equipo["nombre"]),
        ("Categoría", equipo["categoria"]),
        ("Nacimiento", nacimiento),
        ("Número", str(jugador["numero"])),
    ):
        pdf.setFont("Helvetica", 8)
        contenido = _ajustar(pdf, f"{titulo}: {valor}", "Helvetica", 8, texto_ancho)
        pdf.drawString(texto_x, linea, contenido)
        linea -= 4.5 * mm


def _ajustar(pdf: canvas.Canvas, texto: str, fuente: str, tamano: float, ancho: float) -> str:
    """Recorta con puntos suspensivos el texto que no cabe."""
    if pdf.stringWidth(texto, fuente, tamano) <= ancho:
        return texto
    while texto and pdf.stringWidth(texto + "...", fuente, tamano) > ancho:
        texto = texto[:-1]
    return texto + "..."
