"""Manual end-to-end check: one two-page upload -> intake -> page classifier -> grouping.

Makes a real, billed provider call, so it is NOT collected by pytest (pyproject restricts
collection to test_*.py). Run it by hand:

    .venv/bin/python tests/make_synthetic_bundle.py
    .venv/bin/python tests/check_page_classification.py

The bundle is one file holding two documents, and it is uploaded with no declared role —
so both pages carry the hint `invoice` and the classifier has to move page 2 off it on
the content alone. That is the whole point of the stage: without it the consignee of the
consignment note is read as a party of the invoice.

The declaration it reads is entirely fictitious and generated on the spot; no real trade
document is stored in this repository.
"""

from pathlib import Path

from deepclare.config import load_settings
from deepclare.intake import (
    SubmittedFile,
    check_submission,
    group_pages,
    rasterize_documents,
    route_documents,
)
from deepclare.models import GenerativeModel
from deepclare.reading import VisionPageTypeClassifier

settings = load_settings()
raw = Path("/tmp/bundle_synthetic.pdf").read_bytes()
files = [SubmittedFile(file_name="bundle.pdf", content=raw, declared_role=None)]

check_submission(files)
routed = route_documents(files)
print(f"routed   : invoice={routed.invoice.file_name} ({routed.invoice.file_format})")
print(f"           page-less documents: {len(routed.page_less_documents())}")

pages = rasterize_documents(routed.page_bearing_documents())
print(f"rendered : {len(pages)} page(s), hints {[p.role_hint.value for p in pages]}")

with GenerativeModel(settings) as model:
    classifier = VisionPageTypeClassifier(model, settings.prompts_dir)
    verdicts = classifier.classify(pages)

print("\n=== VERDICTS ===")
for verdict in verdicts:
    print(f"  page {verdict.page}: {verdict.page_type.value}")

grouped = group_pages(routed, pages, verdicts)
print("\n=== GROUPED ===")
print(f"  invoice          : {len(grouped.invoice.pages)} page(s)")
note = grouped.consignment_note
print(f"  consignment note : {len(note.pages) if note else 0} page(s)")
print(f"  evidence         : {len(grouped.supporting_evidence)} document(s)")
print(f"  page-less        : {[d.file_name for d in grouped.page_less]}")
for document in (grouped.invoice, *( (note,) if note else () )):
    for placed in document.pages:
        classification = placed.classification
        print(
            f"    {document.role.value:<17} <- source page "
            f"{classification.source_page_number}, verdict "
            f"{classification.verdict.value if classification.verdict else 'none'}, "
            f"hint {classification.role_hint.value}"
        )
