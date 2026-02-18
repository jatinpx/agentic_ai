from fpdf import FPDF
from datetime import datetime
import re
from pathlib import Path


def _latin_safe(text: str) -> str:
    if text is None:
        return ""

    normalized = (
        str(text)
        .replace("•", "-")
        .replace("●", "-")
        .replace("○", "-")
        .replace("—", "-")
        .replace("–", "-")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
    )
    return normalized.encode("latin-1", "replace").decode("latin-1")

def generate_pdf_report(content, title_input):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(18, 20, 18)
    pdf.add_page()

    width = pdf.w - pdf.l_margin - pdf.r_margin

    # ---- HEADER ----
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(width, 10, _latin_safe(title_input.title()))
    
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(120, 120, 120)
    now = datetime.now().strftime("%B %d, %Y | %H:%M")
    pdf.cell(width, 6, _latin_safe("Technical Intelligence Report"), ln=True)
    pdf.cell(width, 6, _latin_safe(f"Generated: {now}"), ln=True)

    pdf.ln(6)
    pdf.set_draw_color(200,200,200)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(8)

    # ---- CLEAN CONTENT ----
    safe = _latin_safe(content)

    lines = safe.split("\n")

    for line in lines:
        line = line.rstrip()

        if not line.strip():
            pdf.ln(4)
            continue

        # ---- HEADERS ----
        if line.startswith("###"):
            pdf.ln(4)
            pdf.set_font("Helvetica","B",13)
            pdf.multi_cell(width,8,_latin_safe(line.replace("###","").strip()))
            pdf.ln(1)

        elif line.startswith("##"):
            pdf.ln(6)
            pdf.set_font("Helvetica","B",15)
            pdf.multi_cell(width,10,_latin_safe(line.replace("##","").strip()))
            pdf.ln(2)

        # ---- NUMBERED LIST ----
        elif re.match(r'^\d+\.', line.strip()):
            pdf.set_font("Helvetica","",11)
            pdf.multi_cell(width,7,_latin_safe(line.strip()))

        # ---- BULLETS ----
        elif line.startswith("- ") or line.startswith("* "):
            pdf.set_font("Helvetica","",11)
            bullet = "- " + line[2:]
            pdf.multi_cell(width,7,_latin_safe(bullet))

        else:
            pdf.set_font("Helvetica","",11)
            line = line.replace("**","")
            pdf.multi_cell(width,7,_latin_safe(line))

    # ---- SAVE ----
    try:
        backend_root = Path(__file__).resolve().parent.parent
        reports_dir = backend_root / "reports"
        reports_dir.mkdir(exist_ok=True)

        file = f"Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        path = reports_dir / file
        pdf.output(str(path))
        return str(path)

    except Exception as e:
        print("PDF ERROR:", e)
        return None
