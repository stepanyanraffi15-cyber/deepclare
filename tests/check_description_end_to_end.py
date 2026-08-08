"""Manual check: real goods lines -> per-line context -> the real model -> Armenian text.

Makes real, billed provider calls, so it is NOT collected by pytest (pyproject restricts
collection to test_*.py). Run it by hand:

    .venv/bin/python tests/check_description_end_to_end.py

The three goods lines are ones the specification records from the measured corpus: a
Turkish DIN-rail carrier, a steel rail-switch fastener, and a construction chemical. Each
sits in a small invoice of plausible neighbours so that the sibling summary is built by
the real context builder rather than typed in. No customer document is stored here.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from deepclare.config import load_settings
from deepclare.description import DescriptionWriter, build_line_contexts
from deepclare.domain import (
    InvoiceGoodsLine,
    InvoiceRecord,
    LineEnrichment,
    Provenance,
    Traced,
    ValueOrigin,
)
from deepclare.models import GenerativeModel

EXTRACTED = Provenance(origin=ValueOrigin.EXTRACTED, source_document_id="invoice")


def traced(value: str) -> Traced[str]:
    return Traced[str](value=value, provenance=EXTRACTED)


def price(value: str) -> Traced[Decimal]:
    return Traced[Decimal](value=Decimal(value), provenance=EXTRACTED)


def line(line_id: str, description: str, unit: str, unit_price: str) -> InvoiceGoodsLine:
    return InvoiceGoodsLine(
        line_id=line_id,
        description=traced(description),
        unit=traced(unit),
        unit_price=price(unit_price),
    )


def invoice(*lines: InvoiceGoodsLine) -> InvoiceRecord:
    return InvoiceRecord(source_document_id="invoice", goods_lines=lines)


ELECTRICAL = invoice(
    line("1", "RAY TAŞIYICI", "AD", "2.40"),
    line("2", "MKR 2,5 MM", "AD", "0.85"),
    line("3", "KLEMENS 4 MM", "AD", "1.10"),
    line("4", "PVC KABLO KANALI 25X40", "M", "1.75"),
    line("5", "BUTON KIRMIZI", "AD", "3.20"),
)

STEEL = invoice(
    line("1", "FOR FASTENING RAIL SWITCHES FROM BLACK METAL", "KG", "1.90"),
    line("2", "HEXAGON BOLT DIN 933 M8X40", "KG", "2.30"),
    line("3", "FLAT WASHER DIN 125 M8", "KG", "2.10"),
)

CHEMICALS = invoice(
    line("1", "CALCIUM FORMATE", "KG", "0.72"),
    line("2", "CEMENT CEM I 42.5 N EN 197-1", "KG", "0.06"),
    line("3", "REDISPERSIBLE POLYMER POWDER", "KG", "1.85"),
)

# A typed note from the operator, which is what the evidence stage hands over. Written
# here because there is no evidence document in this check.
CHEMICAL_NOTE = LineEnrichment(
    line_id="1",
    grounding_facts=(traced("Used as a hardening accelerator in dry mortar mixes"),),
)


def main() -> None:
    settings = load_settings()
    with GenerativeModel(settings) as model:
        writer = DescriptionWriter(model, settings.prompts_dir)
        for label, record, enrichments in (
            ("Turkish electrical invoice", ELECTRICAL, ()),
            ("steel articles invoice", STEEL, ()),
            ("construction chemicals invoice", CHEMICALS, (CHEMICAL_NOTE,)),
        ):
            context = build_line_contexts(record, enrichments)[0]
            print(f"\n=== {label} — line {context.line_id} ===")
            print(f"invoice name  : {context.goods_name}")
            print(f"language      : {context.source_language.value}")
            print(f"unit / price  : {context.unit} / {context.unit_price}")
            print(f"facts         : {list(context.grounding_facts)}")
            print(f"siblings      : {list(context.sibling_names)}")

            written = writer.write(context)
            print(f"DESCRIPTION   : {written.text.value}")
            print(f"SEARCH TERM   : {written.search_term.value}")
            print(f"PRODUCT KIND  : {written.product_kind.value.value}")
            print(f"COMPLETENESS  : {written.completeness.value}")
            print(
                f"provenance    : {written.text.provenance.origin.value} by "
                f"{written.text.provenance.prompt_name} "
                f"v{written.text.provenance.prompt_version}, "
                f"derivation={written.text.confidence.derivation}"
            )
            print(
                f"call          : {written.call.model_id} "
                f"({written.call.model_version}), "
                f"{written.call.usage.total_tokens} tokens"
            )


if __name__ == "__main__":
    main()
