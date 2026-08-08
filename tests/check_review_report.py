"""Build a report from a realistic mixed run and print it. No network, no model.

The findings below are the shapes the pipeline is specified to produce — a weight
distributed from the consignment-note total, a classification abstention on diverging
materials, a supplementary unit the code and the invoice disagree about, a kilogram
default — plus, deliberately, two malformed inputs so that the defect section has
something to show: a value whose producer attached no confidence, and an item keyed by an
XML element name instead of a domain concept.

Run it: .venv/bin/python tests/check_review_report.py
"""

from __future__ import annotations

from decimal import Decimal

from deepclare.domain import (
    Confidence,
    DocumentRegion,
    Provenance,
    ReviewItem,
    ReviewKind,
    Traced,
    Transform,
    ValueOrigin,
)
from deepclare.review import ReportedValue, build_report, render_report, reported

INVOICE = "upload-1-invoice.pdf"
CMR = "upload-2-cmr.pdf"


def extracted(document: str, page: int, role: str) -> Provenance:
    return Provenance(
        origin=ValueOrigin.EXTRACTED,
        source_document_id=document,
        source_document_role=role,
        region=DocumentRegion(page_number=page),
        stage="reading",
    )


def derived(rule: str) -> Provenance:
    return Provenance(origin=ValueOrigin.DERIVED, rule=rule, stage="assembly")


def generated(prompt: str) -> Provenance:
    return Provenance(
        origin=ValueOrigin.GENERATED,
        prompt_name=prompt,
        prompt_version="1",
        stage="description",
    )


def items() -> list[ReviewItem]:
    return [
        ReviewItem(
            kind=ReviewKind.PLACEHOLDER,
            concept="foreign consignor name",
            detail="The seller block on page 1 of the invoice could not be read, and a "
            "party name is one of the two elements permitted to carry a stand-in. A "
            "dash was filed in its place.",
            remedy="the seller's registered name, or a legible copy of the invoice "
            "header",
        ),
        ReviewItem(
            kind=ReviewKind.GUESS,
            concept="shipment origin country",
            detail="No line stated an origin, so the invoice header's country was "
            "applied to every line.",
        ),
        ReviewItem(
            kind=ReviewKind.NEEDS_REVIEW,
            concept="transport vehicle plates",
            detail="Box 25 of the consignment note carried two plates for what may be "
            "one vehicle restated in a second format. Both were filed.",
            remedy="confirmation of how many vehicles carried the goods",
        ),
        ReviewItem(
            kind=ReviewKind.GUESS,
            concept="line gross weight",
            line_id="1",
            detail="No weight was printed on this line, so the consignment note's total "
            "of 18400 kg was distributed across the lines by quantity share.",
        ),
        ReviewItem(
            kind=ReviewKind.OMITTED,
            concept="commodity code",
            line_id="2",
            detail="No code was assigned. The retrieved candidates split between "
            "7318159000 and 7318160000 on whether the fasteners are screws or nuts, and "
            "the description does not say which. Filing either would be a guess at a "
            "duty rate.",
            remedy="the fastener type, or a catalogue page for the article number",
        ),
        ReviewItem(
            kind=ReviewKind.NEEDS_REVIEW,
            concept="supplementary quantity unit",
            line_id="2",
            detail="The nomenclature gives this code the supplementary unit 'шт' while "
            "the invoice priced the line in kilograms. The code's unit was filed and the "
            "quantity restated; the restated count needs confirming.",
            remedy="a piece count for the line",
        ),
        ReviewItem(
            kind=ReviewKind.GUESS,
            concept="measure unit",
            line_id="3",
            detail="Neither the code nor the invoice gave a unit and the goods have no "
            "natural one, so the kilogram default was applied.",
        ),
        ReviewItem(
            kind=ReviewKind.PLACEHOLDER,
            concept="line gross weight",
            line_id="4",
            detail="A stand-in weight was filed for this line.",
        ),
        # Deliberately malformed: an item keyed by an element path.
        ReviewItem(
            kind=ReviewKind.NEEDS_REVIEW,
            concept="GoodsItem/GoodsTNVEDCode",
            line_id="4",
            detail="The code was accepted from the vendor catalogue and always needs a "
            "human eye.",
        ),
    ]


def values() -> list[ReportedValue]:
    return [
        reported(
            "foreign consignor name",
            Traced[str](
                value="-",
                provenance=derived("party name unreadable; stand-in permitted"),
                confidence=Confidence(derivation=0.20, validity=0.60),
            ),
        ),
        reported(
            "invoice total",
            Traced[Decimal](
                value=Decimal("41250.00"),
                provenance=extracted(INVOICE, 1, "invoice"),
                confidence=Confidence(extraction=0.97),
            ),
        ),
        reported(
            "transport vehicle plates",
            Traced[str](
                value="34ABC123",
                provenance=extracted(CMR, 1, "consignment_note").model_copy(
                    update={
                        "transforms": (
                            Transform(
                                operation="strip-spaces-uppercase",
                                before="34 abc 123",
                                after="34ABC123",
                                reason="one plate must have one written form",
                            ),
                        )
                    }
                ),
                confidence=Confidence(extraction=0.71),
            ),
        ),
        reported(
            "goods location",
            Traced[str](
                value="AM-YEREVAN-WAREHOUSE-3",
                provenance=Provenance(
                    origin=ValueOrigin.SUPPLIED, supplied_by="declarant profile"
                ),
                confidence=Confidence(validity=0.99),
            ),
        ),
        reported(
            "line gross weight",
            Traced[Decimal](
                value=Decimal("4600.00"),
                provenance=derived(
                    "gross distributed from consignment-note total by quantity share"
                ),
                confidence=Confidence(derivation=0.55, validity=0.80),
            ),
            line_id="1",
        ),
        reported(
            "goods description",
            Traced[str](
                value="ՊՈՂՊԱՏԵ ԱՄՐԱԿՆԵՐ, ՊՏՈՒՏԱԿԱՎՈՐ",
                provenance=generated("write_goods_description"),
                confidence=Confidence(derivation=0.82, validity=0.90),
            ),
            line_id="2",
        ),
        reported(
            "commodity code",
            # Deliberately malformed: an extracted value whose producer assessed nothing.
            Traced[str](
                value="7318159000",
                provenance=extracted(INVOICE, 2, "invoice"),
            ),
            line_id="3",
        ),
        reported(
            "measure unit",
            Traced[str](
                value="166",
                provenance=derived("kilogram default, no unit available"),
                confidence=Confidence(derivation=0.30, validity=0.95),
            ),
            line_id="3",
        ),
    ]


def main() -> None:
    report = build_report(items(), values())
    print(render_report(report))
    print("--- group order ---")
    for group in report.groups:
        print(
            f"{group.line_id or 'shipment'}: "
            f"{group.flags.most_consequential} "
            f"({len(group.entries)} items, {len(group.values)} values)"
        )


if __name__ == "__main__":
    main()
