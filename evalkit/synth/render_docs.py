"""Render a case to the input documents: invoice PDF, CMR PDF, invoice XLSX.

All projections of the same IR as the ground-truth XML, so they never disagree. PDFs are
**paginated onto A4 pages** — a vision model downscales an oversized image until the text
is unreadable, so every page stays A4 (legible) and the table flows across pages: page 1
carries the full header, later pages a compact "continued" header, the column header
repeats on every page, and the last page carries the TOTAL. Each page is scan-degraded
independently, like separate scans. The XLSX is a genuine workbook for the Excel flows.
"""

from __future__ import annotations

import io
import random

from openpyxl import Workbook

from .ir import Case
from .paper import A4, INK, Canvas, degrade, signature, stamp

_M = 60  # page margin
END = 1180  # page right edge
# invoice columns: text-left for text cols, right-edge for numeric cols
_NO, _PRODUCT, _MODEL, _ORIGIN = 66, 108, 330, 520
_QTY_R, _UNIT, _NET_R, _PRICE_R, _AMOUNT_R = 632, 644, 812, 946, 1174
_ROW_BOTTOM = 1600  # rows fill down to here; the rest of the A4 page holds footer/total/stamps
_FOOTER_Y = 1708


def _money(x: float) -> str:
    return f"{x:,.2f}"


def _multipage_pdf(pages: list) -> bytes:
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    return buf.getvalue()


def _pack(heights: list[float], top_first: int, top_cont: int, reserve: int) -> list[tuple[list[int], bool]]:
    """Assign row indices to A4 pages without splitting a row. `reserve` keeps room on every
    page for the last page's total/stamps. Returns [(indices, is_first_page), ...]."""
    pages: list[tuple[list[int], bool]] = []
    i, first = 0, True
    while i < len(heights):
        y = top_first if first else top_cont
        page: list[int] = []
        while i < len(heights) and (y + heights[i] <= _ROW_BOTTOM - reserve or not page):
            page.append(i)
            y += heights[i]
            i += 1
        pages.append((page, first))
        first = False
    return pages


def _page_footer(c: Canvas, page: int, n: int) -> None:
    c.right(END, _FOOTER_Y, f"Page {page} of {n}", 13, fill=(120, 124, 134))


# --- invoice -------------------------------------------------------------------------------

def _inv_layout(c: Canvas, g) -> tuple[list[str], list[str], float]:
    model = _model_cell(g)
    prod = c.wrap(g.source_name, (_ORIGIN if model in ("", "-") else _MODEL) - _PRODUCT - 12)
    mod = c.wrap(model, _ORIGIN - _MODEL - 12) if model not in ("", "-") else [model]
    return prod, mod, max(len(prod), len(mod), 1) * 24 + 16


def _inv_full_header(c: Canvas, case: Case) -> int:
    c.text((_M, 46), case.seller.name, 30, True)
    c.text((_M, 88), case.seller.address, 18, fill=(80, 84, 94))
    c.right(END, 46, "COMMERCIAL INVOICE", 30, True)
    c.right(END, 92, f"No. {case.invoice_no}", 19)
    c.right(END, 118, f"Date: {case.date}", 19)
    c.line((_M, 150, END, 150))
    c.text((_M, 166), "Bill to:", 17, fill=(110, 114, 124))
    c.text((_M, 190), case.buyer.name, 20, True)
    c.text((_M, 218), case.buyer.address, 17, fill=(80, 84, 94))
    if case.buyer.tax_id:
        c.text((_M, 244), f"ՀՎՀՀ: {case.buyer.tax_id}", 17, fill=(80, 84, 94))
    c.right(END, 190, f"Incoterms: {case.incoterms}", 18)
    c.right(END, 216, f"Currency: {case.currency}", 18)
    c.right(END, 242, f"From: {case.dispatch_country}", 18)
    return 288


def _inv_cont_header(c: Canvas, case: Case, page: int, n: int) -> int:
    c.text((_M, 42), case.seller.name, 22, True)
    c.right(END, 42, "COMMERCIAL INVOICE (continued)", 20, True)
    c.right(END, 74, f"No. {case.invoice_no}   ·   Page {page} of {n}", 16, fill=(90, 94, 104))
    c.line((_M, 104, END, 104))
    return 118


def _inv_cols(c: Canvas, top: int) -> int:
    c.box((_M, top, END, top + 34))
    c.text((_NO, top + 7), "#", 17, True)
    c.text((_PRODUCT, top + 7), "Product", 17, True)
    c.text((_MODEL, top + 7), "Model / Art.", 17, True)
    c.text((_ORIGIN, top + 7), "Origin", 17, True)
    c.right(_QTY_R, top + 7, "Qty", 17, True)
    c.text((_UNIT, top + 7), "Unit", 17, True)
    c.right(_NET_R, top + 7, "Net kg", 17, True)
    c.right(_PRICE_R, top + 7, "Unit Price", 17, True)
    c.right(_AMOUNT_R, top + 7, "Amount", 17, True)
    return top + 34


def _inv_row(c: Canvas, num: int, g, y: float, prod: list[str], mod: list[str]) -> None:
    c.text((_NO, y + 9), str(num), 18)
    for li, ln in enumerate(prod):
        c.text((_PRODUCT, y + 9 + li * 24), ln, 18)
    for li, ln in enumerate(mod):
        c.text((_MODEL, y + 9 + li * 24), ln, 18)
    c.text((_ORIGIN, y + 9), g.origin, 18)
    c.right(_QTY_R, y + 9, f"{g.quantity:g}", 18)
    c.text((_UNIT, y + 9), "PCS" if g.unit == "796" else "KG", 16)
    c.right(_NET_R, y + 9, f"{g.net_weight:g}", 18)
    c.right(_PRICE_R, y + 9, _money(g.unit_price), 18)
    c.right(_AMOUNT_R, y + 9, _money(g.invoiced_cost), 18)


def invoice_pages(case: Case, rng: random.Random) -> list:
    layouts = [_inv_layout(Canvas((16, 16)), g) for g in case.goods]
    heights = [h for *_, h in layouts]
    plan = _pack(heights, 288 + 34, 118 + 34, reserve=80)
    n = len(plan)
    pages = []
    for pi, (idxs, first) in enumerate(plan, 1):
        c = Canvas(A4)
        top = _inv_full_header(c, case) if first else _inv_cont_header(c, case, pi, n)
        y = _inv_cols(c, top)
        for i in idxs:
            prod, mod, rh = layouts[i]
            _inv_row(c, i + 1, case.goods[i], y, prod, mod)
            c.line((_M, y + rh, END, y + rh), 1, fill=(200, 202, 210))
            y += rh
        c.box((_M, top, END, y))
        if pi == n:
            c.right(_QTY_R, y + 16, "TOTAL:", 20, True)
            c.right(_AMOUNT_R, y + 16, f"{_money(case.total_cost)} {case.currency}", 20, True)
            c.text((_M, y + 18), f"Packages: {case.total_packages}   Net basis: KG", 17, fill=(90, 94, 104))
        _page_footer(c, pi, n)
        pages.append(degrade(c.img, rng))
    return pages


def render_invoice_pdf(case: Case, rng: random.Random) -> bytes:
    return _multipage_pdf(invoice_pages(case, rng))


def invoice_image(case: Case, rng: random.Random):  # page 1, for previews
    return invoice_pages(case, rng)[0]


# --- CMR (single-page consignment note: references the invoice, carries only totals) -------
# Real CMRs never itemise goods — the goods box says "contents of the attached invoice" and
# gives shipment totals (packages + gross/net weight). It's a transport doc, not a goods list.

_COUNTRIES = {
    "CN": "China", "TR": "Turkey", "DE": "Germany", "GE": "Georgia", "RU": "Russia",
    "IT": "Italy", "ES": "Spain", "GB": "United Kingdom", "IR": "Iran", "AM": "Armenia",
    "FR": "France", "NL": "Netherlands", "PL": "Poland", "UA": "Ukraine", "AE": "UAE",
    "IN": "India", "US": "USA", "KR": "Korea", "CZ": "Czechia", "LT": "Lithuania",
}
_LM, _RM, _COL = 40, 1200, 622  # CMR margins + column split


def _ctry(code: str) -> str:
    return _COUNTRIES.get((code or "").upper(), (code or "").upper())


def _plate(rng: random.Random) -> str:
    ll = "ABCDEFGHKMNPRSTVXYZ"
    return f"{rng.choice(ll)}{rng.choice(ll)} {rng.randint(100, 999)} {rng.choice(ll)}{rng.choice(ll)}"


def _cbox(c: Canvas, x, y, w, h, num: str, label: str) -> None:
    c.box((x, y, x + w, y + h), width=1)
    c.text((x + 7, y + 4), f"{num}  {label}", 11, fill=(120, 124, 134))


def cmr_image(case: Case, rng: random.Random):
    """A single-page facsimile of the standard CMR form: the goods box references the invoice
    and shows only the shipment TOTALS (packages + gross/net) — never the itemised goods."""
    c = Canvas(A4)
    lm, rm, col = _LM, _RM, _COL
    gross = sum(g.gross_weight for g in case.goods)
    net = sum(g.net_weight for g in case.goods)

    c.text((lm, 32), "INTERNATIONAL CONSIGNMENT NOTE", 22, True)
    c.text((lm, 66), "Международная товарно-транспортная накладная · Internationaler Frachtbrief",
           12, fill=(110, 114, 124))
    c.d.ellipse((rm - 128, 24, rm, 78), outline=INK, width=3)
    c.text((rm - 100, 36), "CMR", 24, True)

    _cbox(c, lm, 96, col - lm, 92, "1", "Sender (Name, Address, Country)")
    c.text((lm + 8, 122), case.seller.name, 17)
    c.text((lm + 8, 148), case.seller.address, 15, fill=(70, 74, 84))
    c.text((lm + 8, 170), _ctry(case.dispatch_country), 15, fill=(70, 74, 84))
    _cbox(c, col + 6, 96, rm - col - 6, 92, "16", "Carrier (Name, Address, Country)")
    c.text((col + 14, 122), case.carrier.name, 17)
    c.text((col + 14, 148), case.carrier.address, 15, fill=(70, 74, 84))

    _cbox(c, lm, 192, col - lm, 104, "2", "Consignee (Name, Address, Country)")
    c.text((lm + 8, 218), case.buyer.name, 17)
    c.text((lm + 8, 244), case.buyer.address, 15, fill=(70, 74, 84))
    if case.buyer.tax_id:
        c.text((lm + 8, 268), f"Tax code (ՀՎՀՀ): {case.buyer.tax_id}", 15, fill=(70, 74, 84))
    _cbox(c, col + 6, 192, rm - col - 6, 50, "17", "Successive carrier")
    _cbox(c, col + 6, 244, rm - col - 6, 52, "18", "Carrier's reservations and observations")

    _cbox(c, lm, 300, col - lm, 56, "3", "Place of delivery of the goods")
    c.text((lm + 8, 326), "YEREVAN / ARMENIA", 17)
    _cbox(c, lm, 358, col - lm, 56, "4", "Place & date of taking over the goods")
    c.text((lm + 8, 384), f"BATUMI / GEORGIA   ·   {case.date}", 16)
    _cbox(c, lm, 416, col - lm, 52, "5", "Documents attached")
    c.text((lm + 8, 442), f"INVOICE No {case.invoice_no}   ·   {case.date}", 16)
    _cbox(c, col + 6, 300, rm - col - 6, 44, "19", "Special agreements")
    _cbox(c, col + 6, 344, rm - col - 6, 124, "20", "To be paid by")
    for k, lab in enumerate(("Carriage charges", "Discount", "Balance", "TOTAL")):
        c.text((col + 14, 372 + k * 24), lab, 13, fill=(120, 124, 134))

    gy = 476
    gcols = [(lm, "6  Marks & Nos"), (lm + 150, "7  Packages"), (lm + 300, "8  Packing"),
             (lm + 420, "9  Nature of the goods"), (rm - 300, "11  Gross kg"), (rm - 150, "12  Net kg")]
    c.box((lm, gy, rm, gy + 32), width=1)
    for x, lab in gcols:
        c.text((x + 6, gy + 8), lab, 12, True)
    c.box((lm, gy + 32, rm, gy + 148), width=1)
    for x, _lab in gcols[1:]:
        c.line((x, gy, x, gy + 148), 1, fill=(150, 154, 164))
    c.text((lm + 6, gy + 60), "—", 16)
    c.text((lm + 156, gy + 60), str(case.total_packages), 16)
    c.text((lm + 306, gy + 60), "PALLETS", 16)
    c.text((lm + 426, gy + 60), "CONTENTS OF THE ATTACHED INVOICE GOODS", 17, True)
    c.right(rm - 156, gy + 60, f"{gross:g}", 16)
    c.right(rm - 8, gy + 60, f"{net:g}", 16)

    my = gy + 154
    _cbox(c, lm, my, col - lm, 90, "13", "Sender's instructions")
    c.text((lm + 8, my + 34), "TERMINAL YEREVAN", 17, True)
    _cbox(c, lm, my + 96, col - lm, 52, "14", "Instructions as to payment for carriage")
    _cbox(c, col + 6, my, rm - col - 6, 56, "21", "Established in")
    c.text((col + 14, my + 26), f"BATUMI   ·   {case.date}", 16)

    sy = my + 158
    third = (rm - lm) / 3
    for i, (num, label, who) in enumerate([
        ("22", "Signature & stamp of the sender", case.seller.name),
        ("23", "Signature & stamp of the carrier", case.carrier.name),
        ("24", "Goods received", case.buyer.name)]):
        bx = lm + i * third
        _cbox(c, bx, sy, third - 6, 176, num, label)
        c.paste(signature(rng), (int(bx + 22), int(sy + 66)))
        c.paste(stamp(who, rng), (int(bx + third - 184), int(sy + 26)))

    vy = sy + 182
    _cbox(c, lm, vy, rm - lm, 72, "27", "Vehicle (Truck / Trailer plate)")
    c.text((lm + 200, vy + 32), f"Truck:  {_plate(rng)}        Trailer:  {_plate(rng)}", 18)

    # 25-29 charges grid (blank in practice — fills the lower form like a real CMR)
    cy = vy + 78
    _cbox(c, lm, cy, rm - lm, 300, "25–29", "Charges to be paid")
    split = lm + 620
    c.line((split, cy, split, cy + 300), 1, fill=(180, 184, 194))
    c.right(split - 12, cy + 8, "Currency", 12, fill=(120, 124, 134))
    c.text((split + 12, cy + 8), "Amount", 12, fill=(120, 124, 134))
    ry = cy + 44
    for label in ("Carriage charges", "Supplementary charges", "Customs duties",
                  "Reductions", "Balance", "TOTAL to be paid"):
        c.text((lm + 12, ry), label, 15, fill=(90, 94, 104))
        c.line((lm, ry + 30, rm, ry + 30), 1, fill=(222, 224, 230))
        ry += 42
    return degrade(c.img, rng)


def render_cmr_pdf(case: Case, rng: random.Random) -> bytes:
    return _multipage_pdf([cmr_image(case, rng)])


# --- XLSX ----------------------------------------------------------------------------------

def render_invoice_xlsx(case: Case) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Invoice"
    ws.append([case.seller.name])
    ws.append(["Invoice", case.invoice_no, "Date", case.date, "Currency", case.currency])
    ws.append(["Bill to", case.buyer.name, case.buyer.address, f"ՀՎՀՀ {case.buyer.tax_id or ''}"])
    ws.append([])
    ws.append(["#", "Product", "Model / Art.", "Origin", "Qty", "Unit", "Net kg", "Unit Price", "Amount"])
    for i, g in enumerate(case.goods, 1):
        ws.append([i, g.source_name, g.trade_name or "", g.origin, g.quantity,
                   "PCS" if g.unit == "796" else "KG", g.net_weight, g.unit_price, g.invoiced_cost])
    ws.append([])
    ws.append(["", "", "", "", "", "", "", "TOTAL", case.total_cost])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _model_cell(g) -> str:
    # When the trade name IS the printed product (detergents, electrical), the seed sets
    # source_name == trade_name — don't repeat it in the Model column.
    if g.trade_name and g.trade_name != g.source_name:
        return g.trade_name
    return "" if g.trade_name else "-"
