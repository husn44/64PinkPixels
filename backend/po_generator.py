import os
import random
from datetime import date
from backend.models import ExtractedItem
from backend.config import settings

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)


def _generate_po_number() -> str:
    today = date.today().strftime("%Y%m%d")
    rand = random.randint(1000, 9999)
    return f"PO-{today}-{rand}"


def generate_po_pdf(
    vendor_name: str,
    extracted_items: list[ExtractedItem],
    po_number: str | None = None,
    output_dir: str | None = None,
) -> str:
    if po_number is None:
        po_number = _generate_po_number()
    if output_dir is None:
        output_dir = str(settings.DATA_DIR)

    os.makedirs(output_dir, exist_ok=True)
    safe_vendor = "".join(c if c.isalnum() else "_" for c in vendor_name)
    filename = f"{po_number}_{safe_vendor}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "POTitle",
        parent=styles["Title"],
        fontSize=20,
        leading=24,
        spaceAfter=6,
        textColor=colors.HexColor("#1a1a2e"),
    )
    subtitle_style = ParagraphStyle(
        "POSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#555555"),
    )
    section_style = ParagraphStyle(
        "POSection",
        parent=styles["Heading2"],
        fontSize=12,
        leading=16,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor("#16213e"),
    )
    body_style = ParagraphStyle(
        "POBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
    )

    elements = []

    # Header
    elements.append(Paragraph("PINKPIXELS PROCUREMENT", title_style))
    elements.append(Paragraph("Purchase Order", subtitle_style))
    elements.append(Spacer(1, 0.3 * inch))

    # PO info table — use first item's contact info
    first_item = extracted_items[0]
    po_info = [
        ["PO Number:", po_number, "Date:", date.today().strftime("%B %d, %Y")],
        ["From:", "PinkPixels Inc.", "To:", vendor_name],
        ["", "", "Contact:", first_item.contact_info or "N/A"],
    ]
    po_table = Table(po_info, colWidths=[1.2 * inch, 2.3 * inch, 1.2 * inch, 2.3 * inch])
    po_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#555555")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(po_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Line items
    elements.append(Paragraph("Line Items", section_style))

    line_data = [
        ["#", "Item", "Description", "Qty", "Unit", "Unit Price", "Total"],
    ]
    subtotal = 0.0
    for idx, item in enumerate(extracted_items, 1):
        unit_price = item.item_price / max(item.normalized_quantity, 1)
        line_total = item.item_price
        subtotal += line_total
        line_data.append([
            str(idx),
            item.item_name,
            Paragraph(item.item_description or "-", body_style),
            str(item.normalized_quantity),
            item.normalized_unit,
            f"RM {unit_price:,.2f}",
            f"RM {line_total:,.2f}",
        ])

    line_table = Table(
        line_data,
        colWidths=[0.4 * inch, 1.3 * inch, 1.8 * inch, 0.6 * inch, 0.7 * inch, 1.0 * inch, 1.0 * inch],
    )
    line_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (2, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Totals
    tax = round(subtotal * 0.08, 2)
    grand_total = subtotal + tax

    totals_data = [
        ["", "Subtotal:", f"RM {subtotal:,.2f}"],
        ["", "Tax (8%):", f"RM {tax:,.2f}"],
        ["", "Grand Total:", f"RM {grand_total:,.2f}"],
    ]
    totals_table = Table(totals_data, colWidths=[3.5 * inch, 1.5 * inch, 1.5 * inch])
    totals_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (1, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (1, -1), (-1, -1), 11),
        ("LINEABOVE", (1, -1), (-1, -1), 1, colors.HexColor("#1a1a2e")),
    ]))
    elements.append(totals_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Terms
    elements.append(Paragraph("Terms & Conditions", section_style))
    payment = first_item.payment_terms or "Net 30"
    delivery = f"{first_item.delivery_days} business days" if first_item.delivery_days else "As agreed"
    warranty = first_item.warranty or "Per manufacturer's standard warranty"
    terms_text = (
        f"1. Payment: {payment}.<br/>"
        f"2. Delivery: {delivery}.<br/>"
        f"3. Warranty: {warranty}.<br/>"
        "4. This PO is subject to PinkPixels standard terms and conditions.<br/>"
        "5. Vendor must acknowledge receipt of this PO within 2 business days.<br/>"
        "6. All goods must meet specified quality standards."
    )
    elements.append(Paragraph(terms_text, body_style))
    elements.append(Spacer(1, 0.5 * inch))

    # Signature block
    sig_data = [
        ["Authorized Signature:", "Date:"],
        ["", date.today().strftime("%B %d, %Y")],
        ["________________________", "________________________"],
    ]
    sig_table = Table(sig_data, colWidths=[3.5 * inch, 3.0 * inch])
    sig_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(sig_table)

    doc.build(elements)
    return filepath
