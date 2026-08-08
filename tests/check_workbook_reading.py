"""Manual end-to-end check: a synthetic spreadsheet invoice through A7 → A11.

Makes two real, billed provider calls, so it is NOT collected by pytest (pyproject
restricts collection to test_*.py). Run it by hand:

    .venv/bin/python tests/make_synthetic_workbook.py
    .venv/bin/python tests/check_workbook_reading.py

The workbook it reads is entirely fictitious and generated on the spot; no real trade
document is stored in this repository. Everything the path has to survive is in it: a
preamble above the table, Armenian headers, gross weight beside net weight, a seller's
article-number column beside a real customs-code column, a totals row below the data, a
row with no description, a quantity cell holding words, a freight row, and a second sheet
with no table in it.
"""

from __future__ import annotations

import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from deepclare.config import load_settings
from deepclare.intake import SubmittedFile, check_submission, route_documents
from deepclare.models import GenerativeModel
from deepclare.reading import read_workbook_invoice
from deepclare.reading.workbook import buffer_workbook

WORKBOOK = Path("/tmp/invoice_synthetic.xlsx")


def show(label: str, value: object) -> None:
    print(f"{label:<22}: {value}")


def main() -> None:
    settings = load_settings()
    files = [
        SubmittedFile(
            file_name="invoice.xlsx", content=WORKBOOK.read_bytes(), declared_role=None
        )
    ]
    check_submission(files)
    routed = route_documents(files)
    show("routed invoice", f"{routed.invoice.file_name} ({routed.invoice.file_format})")
    show("page-bearing", [d.file_name for d in routed.page_bearing_documents()])
    show("page-less", [d.file_name for d in routed.page_less_documents()])

    buffered = buffer_workbook(routed.invoice)
    print("\n=== A7 BUFFER ===")
    for sheet in buffered.sheets:
        show(f"sheet {sheet.name!r}", f"{len(sheet.rows)} non-blank rows")

    with GenerativeModel(settings) as model:
        reading = read_workbook_invoice(routed.invoice, model, settings.prompts_dir)

    print("\n=== A9 / A10 PER SHEET ===")
    for sheet in reading.sheets:
        if sheet.table is None:
            show(sheet.sheet_name, "no goods table; contributes nothing")
            continue
        show(
            sheet.sheet_name,
            f"located by {sheet.table.located_by}, "
            f"{sheet.table.data_row_count} data row(s), "
            f"{sheet.table.column_count} columns, {sheet.goods_rows} goods line(s)",
        )
        if sheet.rows_without_description:
            show("  no description", sheet.rows_without_description)
        if sheet.service_rows:
            show("  service rows", sheet.service_rows)
        for binding in sheet.labelling.bindings:
            print(f"    column {binding.column:>2} -> {binding.field}")
        ignored = sorted(
            set(range(sheet.table.column_count))
            - {b.column for b in sheet.labelling.bindings}
        )
        show("  not bound", ignored)

    print("\n=== A8 HEADER ===")
    invoice = reading.reading.invoice
    for name in (
        "invoice_number",
        "invoice_date",
        "currency",
        "incoterms_code",
        "incoterms_place",
        "origin_country",
        "total_amount",
    ):
        traced = getattr(invoice, name)
        show(name, None if traced is None else traced.value)
    for role in ("seller", "buyer"):
        party = getattr(invoice, role)
        show(role, None if party is None or party.name is None else party.name.value)
    show(
        "service charges",
        [
            (charge.description.value, charge.amount.value if charge.amount else None)
            for charge in reading.reading.service_charges
        ],
    )

    print(f"\n=== GOODS LINES ({reading.goods_source}) ===")
    for line in invoice.goods_lines:
        print(f"  line {line.line_id}: {line.description.value}")
        for name in (
            "printed_line_number",
            "quantity",
            "unit",
            "gross_weight",
            "net_weight",
            "unit_price",
            "total_price",
            "origin_country",
            "printed_customs_code",
        ):
            traced = getattr(line, name)
            if traced is not None:
                print(f"      {name:<22} {traced.value}")

    print("\n=== WHAT COULD NOT BE READ ===")
    if not reading.unread_numbers:
        print("  (none)")
    for unread in reading.unread_numbers:
        print(
            f"  sheet {unread.sheet_name!r} column {unread.column} bound to "
            f"{unread.field_name}: {len(unread.rows)} cell(s) at row(s) "
            f"{', '.join(str(row) for row in unread.rows)} — e.g. "
            f"{', '.join(repr(example) for example in unread.examples)}"
        )
    for sheet in reading.sheets:
        for duplicate in sheet.labelling.duplicates if sheet.labelling else ():
            print(
                f"  sheet {duplicate.sheet_name!r}: {duplicate.field} claimed by columns "
                f"{duplicate.kept_column} and {duplicate.dropped_columns}; lowest wins"
            )

    print("\n=== CALLS ===")
    for call in reading.model_calls:
        show(
            call.prompt_name,
            f"{call.model_id} v{call.prompt_version}, "
            f"{call.usage.prompt_tokens} in / {call.usage.output_tokens} out",
        )


if __name__ == "__main__":
    main()
