"""Geração de PDF da escala (UTF-8) com fonte DejaVu."""
from __future__ import annotations

import datetime as dt
import urllib.request
from pathlib import Path
from typing import Any

import fpdf

from logic import AREAS, WEEKDAY_PT

_DEJAVU_URL = (
    "https://raw.githubusercontent.com/py-pdf/fpdf2/master/test/fonts/DejaVuSans.ttf"
)


def _dejavu_path() -> Path:
    """fpdf2 recente não inclui TTF no pacote; usa cópia local ou baixa uma vez."""
    local = Path(__file__).resolve().parent / "fonts" / "DejaVuSans.ttf"
    if local.is_file():
        return local
    bundled = Path(fpdf.__file__).resolve().parent / "font" / "DejaVuSans.ttf"
    if bundled.is_file():
        return bundled
    local.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(_DEJAVU_URL, local)
    except OSError as e:
        raise RuntimeError(
            "Não foi possível baixar a fonte DejaVuSans.ttf (necessária para o PDF com acentos). "
            "Verifique a conexão ou coloque o arquivo manualmente em fonts/DejaVuSans.ttf."
        ) from e
    return local


def _short(text: str, max_len: int) -> str:
    t = (text or "-").replace("\n", " ").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


TRAINING_PDF_BANNER = "Oficina de comunicação · Todos os Domingos · 7h30 às 9h30."

EMPTY_CELL_PLACEHOLDER = "Responsável do dia"


def build_schedule_pdf(
    title: str,
    events: list[dict[str, Any]],
    names_by_cell: dict[tuple[str, str], str],
    *,
    include_training: bool = False,
) -> bytes:
    """
    events: lista de {date, label, time_range?}
    names_by_cell: (data_iso, area) -> nome; '-' ou '—' vira texto cinza «Responsável do dia»
    """
    font_path = _dejavu_path()
    if not font_path.is_file():
        raise FileNotFoundError(f"Fonte DejaVu não encontrada em {font_path}")

    pdf = fpdf.FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    pdf.add_font("DejaVu", "", str(font_path))
    pdf.add_font("DejaVu", "B", str(font_path))
    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(0, 9, title, ln=1)
    if include_training:
        pdf.set_font("DejaVu", "", 7.5)
        pdf.set_text_color(80, 40, 40)
        pdf.multi_cell(0, 3.8, TRAINING_PDF_BANNER, ln=1)
        pdf.set_text_color(0, 0, 0)
    pdf.ln(1)

    col_date = 44
    col_lbl = 50
    margin_x = 10
    table_w = 297 - 2 * margin_x
    area_w = (table_w - col_date - col_lbl) / len(AREAS)
    row_h = 10

    pdf.set_font("DejaVu", "B", 7)
    pdf.cell(col_date, row_h, "Data", border=1, align="C")
    pdf.cell(col_lbl, row_h, "Evento", border=1, align="C")
    for a in AREAS:
        pdf.cell(area_w, row_h, _short(a, 14), border=1, align="C")
    pdf.ln()

    pdf.set_font("DejaVu", "", 6)
    for ev in events:
        date_iso = ev["date"]
        label = ev.get("label") or ""
        tr = ev.get("time_range")
        d = dt.date.fromisoformat(date_iso)
        wd = WEEKDAY_PT[d.weekday()]
        if tr:
            date_txt = _short(f"{d.day:02d}/{d.month:02d} — {wd} ({tr})", 42)
        else:
            date_txt = _short(f"{d.day:02d}/{d.month:02d} — {wd}", 32)
        ev_lbl = f"{label}" + (f" · {tr}" if tr else "")
        if include_training and d.weekday() == 6:
            ev_lbl = f"{ev_lbl} · {TRAINING_PDF_BANNER}"
        ev_lbl = _short(ev_lbl, 72)
        pdf.cell(col_date, row_h, date_txt, border=1, align="L")
        pdf.cell(col_lbl, row_h, ev_lbl, border=1, align="L")
        for area in AREAS:
            name = (names_by_cell.get((date_iso, area), "-") or "-").strip()
            if name in ("-", "—"):
                pdf.set_text_color(190, 190, 190)
                pdf.cell(
                    area_w,
                    row_h,
                    _short(EMPTY_CELL_PLACEHOLDER, 20),
                    border=1,
                    align="C",
                )
                pdf.set_text_color(0, 0, 0)
            else:
                pdf.cell(area_w, row_h, _short(name, 18), border=1, align="C")
        pdf.ln()

    return bytes(pdf.output())
