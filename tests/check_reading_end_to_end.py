"""Manual end-to-end check: synthetic invoice PDF -> intake -> vision model -> record.

Makes a real, billed provider call, so it is NOT collected by pytest (pyproject
restricts collection to test_*.py). Run it by hand:

    .venv/bin/python tests/make_synthetic_invoice.py
    .venv/bin/python tests/check_reading_end_to_end.py

The invoice it reads is entirely fictitious and generated on the spot; no real
trade document is stored in this repository. It deliberately carries a freight
row, which must never come back as a goods line.
"""

import logging
from pathlib import Path
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from deepclare.config import load_settings
from deepclare.intake import (SubmittedFile, check_submission, route_documents,
                              rasterize_documents, group_pages, PageVerdict)
from deepclare.models import GenerativeModel, ModelTier
from deepclare.reading import DocumentReader

s = load_settings()
raw = Path("/tmp/invoice_synthetic.pdf").read_bytes()
files = [SubmittedFile(file_name="invoice.pdf", content=raw, declared_role=None)]

check_submission(files)
routed = route_documents(files)
print(f"routed: invoice={routed.invoice.file_name if routed.invoice else None}")

pages = rasterize_documents(routed.page_bearing_documents())
print(f"rasterized {len(pages)} page(s) (role hint: {pages[0].role_hint})")

# every page reads as the invoice: one document, one role, no classifier call needed
verdicts = [PageVerdict(page=i+1, page_type="invoice") for i in range(len(pages))]
grouped = group_pages(routed, pages, verdicts)
doc = grouped.invoice
print(f"grouped: invoice document with {len(doc.pages)} page(s)")

model = GenerativeModel(s)

reader = DocumentReader(model, s.prompts_dir)
result = reader.read_invoice(doc)
print("\n=== EXTRACTED ===")
inv = result.invoice
print(f"invoice no : {inv.invoice_number.value if inv.invoice_number else None}")
print(f"date       : {inv.invoice_date.value if inv.invoice_date else None}")
print(f"currency   : {inv.currency.value if inv.currency else None}")
print(f"incoterms  : {inv.incoterms_code.value if inv.incoterms_code else None}")
print(f"total      : {inv.total_amount.value if inv.total_amount else None}")
print(f"seller     : {inv.seller.name.value if inv.seller and inv.seller.name else None}")
print(f"buyer      : {inv.buyer.name.value if inv.buyer and inv.buyer.name else None}")
print(f"\nGOODS LINES: {len(inv.goods_lines)}")
for g in inv.goods_lines:
    d=g.description.value
    q=g.quantity.value if g.quantity else None
    u=g.unit.value if g.unit else None
    hs=g.printed_customs_code.value if g.printed_customs_code else None
    tot=g.total_price.value if g.total_price else None
    print(f"  [{g.line_id}] {d!r}  qty={q} {u}  hs={hs}  total={tot}")
print("\nFREIGHT ROW EXCLUDED:",
      not any("freight" in (g.description.value or "").lower() for g in inv.goods_lines))
