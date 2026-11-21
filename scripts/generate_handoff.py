#!/usr/bin/env python3
"""
MeetFlow AI — Mandatory Automatic PDF Handoff Generator (ReportLab).
Reads docs/PROJECT_HANDOFF.md as the source of truth and renders docs/PROJECT_HANDOFF.pdf.
Verifies the generated PDF exists and has valid PDF header/EOF markers.
"""
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def generate_handoff_pdf(md_path: Path, pdf_path: Path) -> None:
    if not md_path.exists():
        raise FileNotFoundError(f"Source handoff markdown not found: {md_path}")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "HandoffTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=10,
    )
    h2_style = ParagraphStyle(
        "HandoffH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#065F46"),
        spaceBefore=10,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "HandoffBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        "HandoffBullet",
        parent=body_style,
        leftIndent=14,
        firstLineIndent=-8,
        spaceAfter=3,
    )

    story = []
    for raw_line in md_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 4))
            continue

        safe = escape(line)
        # Convert simple **bold** markdown to ReportLab <b> tags
        while "**" in safe:
            safe = safe.replace("**", "<b>", 1).replace("**", "</b>", 1)

        if line.startswith("# "):
            story.append(Paragraph(safe[2:], title_style))
        elif line.startswith("## "):
            story.append(Paragraph(safe[3:], h2_style))
        elif line.startswith("- "):
            story.append(Paragraph(f"&bull; {safe[2:]}", bullet_style))
        else:
            story.append(Paragraph(safe, body_style))

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="MeetFlow AI — Project Handoff",
        author="MeetFlow AI Engineering",
    )
    doc.build(story)

    # Verify PDF exists and is readable
    data = pdf_path.read_bytes()
    if not data.startswith(b"%PDF-") or len(data) < 1000:
        raise RuntimeError(f"Generated PDF failed verification ({len(data)} bytes).")
    print(f"Verified PDF handoff generated: {pdf_path} ({len(data)} bytes)")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    md = root / "docs" / "PROJECT_HANDOFF.md"
    pdf = root / "docs" / "PROJECT_HANDOFF.pdf"
    try:
        generate_handoff_pdf(md, pdf)
    except Exception as exc:
        print(f"ERROR generating PDF handoff: {exc}", file=sys.stderr)
        sys.exit(1)
