"""Recibo de pago en PDF, en media hoja carta."""

import sqlite3
from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from . import cobros
from .paths import asset

OSCURO = HexColor("#10291D")
DORADO = HexColor("#C9A24B")
VERDE = HexColor("#1E7F4C")
TEXTO = HexColor("#1E2B25")
SUAVE = HexColor("#52635A")
LINEAS_MAXIMAS = 12


def generar(conn: sqlite3.Connection, folio: int, destino: Path | str) -> None:
    """Lanza ValueError si el pago está anulado: un recibo no debe avalarlo."""
    pago = conn.execute(
        """SELECT p.*, e.nombre AS equipo, e.torneo_id, c.nombre AS categoria, t.nombre AS torneo
           FROM pagos p JOIN equipos e ON e.id = p.equipo_id
           JOIN categorias c ON c.id = e.categoria_id JOIN torneos t ON t.id = e.torneo_id
           WHERE p.id = ?""",
        (folio,),
    ).fetchone()
    if pago is None or pago["anulado"]:
        raise ValueError("Este pago está anulado; no se puede generar su recibo.")
    detalle = cobros.detalle_de_pago(conn, folio)
    saldo = next(
        a.saldo for a in cobros.adeudos(conn, pago["torneo_id"]) if a.equipo_id == pago["equipo_id"]
    )

    pdf = canvas.Canvas(str(destino), pagesize=letter)
    pdf.setTitle(f"Recibo {folio:05d}")
    ancho, alto = letter
    margen = 18 * mm
    derecha = ancho - margen
    y = alto - 14 * mm

    alto_encabezado = 26 * mm
    pdf.setFillColor(OSCURO)
    pdf.rect(margen, y - alto_encabezado, derecha - margen, alto_encabezado, fill=1, stroke=0)
    pdf.setFillColor(DORADO)
    pdf.rect(margen, y - alto_encabezado - 1 * mm, derecha - margen, 1 * mm, fill=1, stroke=0)
    pdf.drawImage(
        ImageReader(str(asset("logo.png"))), margen + 2 * mm, y - alto_encabezado + 1.5 * mm,
        28 * mm, alto_encabezado - 3 * mm, preserveAspectRatio=True, mask="auto",
    )
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(margen + 34 * mm, y - 11 * mm, "RECIBO DE PAGO")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margen + 34 * mm, y - 18 * mm, "Deportivo León - Saltillo A.C.")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawRightString(derecha - 4 * mm, y - 11 * mm, f"Folio {folio:05d}")
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(
        derecha - 4 * mm, y - 18 * mm, date.fromisoformat(pago["fecha"]).strftime("%d/%m/%Y")
    )
    y -= alto_encabezado + 10 * mm

    for titulo, valor in (
        ("Equipo", pago["equipo"]), ("Categoría", pago["categoria"]), ("Torneo", pago["torneo"]),
    ):
        pdf.setFillColor(SUAVE)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(margen, y, f"{titulo}:")
        pdf.setFillColor(TEXTO)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margen + 22 * mm, y, valor)
        y -= 5.5 * mm
    y -= 3 * mm

    pdf.setFillColor(TEXTO)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margen, y, "Concepto")
    pdf.drawRightString(derecha, y, "Importe")
    y -= 2 * mm
    pdf.setStrokeColor(SUAVE)
    pdf.line(margen, y, derecha, y)
    y -= 5 * mm

    pdf.setFont("Helvetica", 10)
    if len(detalle) > LINEAS_MAXIMAS:
        resto = sum(m for _, m in detalle[LINEAS_MAXIMAS - 1:])
        detalle = detalle[: LINEAS_MAXIMAS - 1] + [
            (f"Otros {len(detalle) - LINEAS_MAXIMAS + 1} conceptos", resto)
        ]
    for texto, monto in detalle:
        pdf.drawString(margen, y, texto)
        pdf.drawRightString(derecha, y, cobros.dinero(monto))
        y -= 5.5 * mm
    pdf.line(margen, y + 2 * mm, derecha, y + 2 * mm)
    y -= 4 * mm

    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(VERDE)
    pdf.drawString(margen, y, "Total pagado")
    pdf.drawRightString(derecha, y, cobros.dinero(pago["monto"]))
    y -= 7 * mm
    pdf.setFillColor(TEXTO)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margen, y, f"Saldo pendiente del equipo al {date.today():%d/%m/%Y}")
    pdf.drawRightString(derecha, y, cobros.dinero(saldo))
    y -= 6 * mm
    if pago["nota"]:
        pdf.setFillColor(SUAVE)
        pdf.drawString(margen, y, f"Nota: {pago['nota'][:90]}")
        y -= 6 * mm

    y -= 16 * mm
    pdf.setStrokeColor(TEXTO)
    pdf.line(margen + 45 * mm, y, derecha - 45 * mm, y)
    pdf.setFillColor(SUAVE)
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString((margen + derecha) / 2, y - 4.5 * mm, "Recibió")
    pdf.save()
