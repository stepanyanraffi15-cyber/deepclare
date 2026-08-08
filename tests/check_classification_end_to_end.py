"""Manual check: real goods lines -> the real models -> a real commodity code.

Makes real, billed provider calls and reads the real reference collection, so it is NOT
collected by pytest (pyproject restricts collection to test_*.py). Run it by hand:

    .venv/bin/python tests/check_classification_end_to_end.py

Five cases, each chosen for the path it exercises rather than for the answer it gives:

1. an unambiguous bulk material — the ordinary route, chapter to heading to leaf;
2. a line whose invoice prints its own commodity code — the fast path, which skips both
   narrowing calls;
3. a device the specification records as *genuinely* straddling two headings, where the
   deciding attribute is not on the document;
4. a line whose candidates split by raw material — wood against plastic — with the line
   silent about it: the abstention that names each branch with its code;
5. a line whose supplier catalogue prints a code — the vendor-catalogue short circuit,
   which makes no model call at all.

Every line goes through description composition first, because that is where its input
comes from: this is the two modules end to end, not the classifier alone. Each sits in a
small invoice of plausible neighbours so the sibling summary is built rather than typed
in. No customer document is stored here; every line below is fictitious.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

import qdrant_client

from deepclare.classification import Classifier, build_classification_lines
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
from deepclare.embedding import GeminiEmbedder
from deepclare.models import GenerativeModel
from deepclare.reference.store import NomenclatureStore

EXTRACTED = Provenance(origin=ValueOrigin.EXTRACTED, source_document_id="invoice")


def traced(value: str) -> Traced[str]:
    return Traced[str](value=value, provenance=EXTRACTED)


def price(value: str) -> Traced[Decimal]:
    return Traced[Decimal](value=Decimal(value), provenance=EXTRACTED)


def line(
    line_id: str,
    description: str,
    unit: str,
    unit_price: str,
    printed_code: str | None = None,
) -> InvoiceGoodsLine:
    return InvoiceGoodsLine(
        line_id=line_id,
        description=traced(description),
        unit=traced(unit),
        unit_price=price(unit_price),
        printed_customs_code=traced(printed_code) if printed_code else None,
    )


def invoice(*lines: InvoiceGoodsLine) -> InvoiceRecord:
    return InvoiceRecord(source_document_id="invoice", goods_lines=lines)


# --- the five cases ---------------------------------------------------------

BUILDING = invoice(
    line("1", "PORTLAND CEMENT CEM I 42.5 N", "KG", "0.06"),
    line("2", "GYPS", "KG", "0.08"),
    line("3", "SAND, WASHED, 0-4 MM", "KG", "0.02"),
)

ELECTRICAL = invoice(
    line("1", "TERMINAL BLOCK 4 MM", "PCS", "1.10", printed_code="8536.90.10.00.00"),
    line("2", "MKR 2,5 MM", "PCS", "0.85"),
    line("3", "DIN RAIL 35X7.5 MM", "M", "2.40"),
)

SENSORS = invoice(
    line("1", "INDUCTIVE PROXIMITY SENSOR M18, 8MM SENSING DISTANCE", "PCS", "18.00"),
    line("2", "MOUNTING BRACKET FOR SENSOR M18", "PCS", "3.20"),
    line("3", "CONNECTOR CABLE M12 5M", "PCS", "9.50"),
)

HOUSEWARES = invoice(
    line("1", "CLOTHES HANGERS, 42 CM", "PCS", "0.35"),
    line("2", "LAUNDRY BASKET 40 L", "PCS", "3.10"),
    line("3", "SHOE RACK 3 TIER", "PCS", "6.80"),
)

CATALOGUE = invoice(
    line("1", "PE BAG 50X80 CM, 40 MICRON", "PCS", "0.07"),
    line("2", "STRETCH FILM 500MM X 300M", "PCS", "4.20"),
)

CATALOGUE_ENRICHMENT = (
    LineEnrichment(
        line_id="1",
        printed_customs_code=traced("3923210000"),
        grounding_facts=(traced("low density polyethylene, 40 micron"),),
    ),
)

CASES = [
    ("obvious bulk material", BUILDING, "1", ()),
    ("printed code on the invoice", ELECTRICAL, "1", ()),
    ("genuinely straddling headings", SENSORS, "1", ()),
    ("material split, line silent", HOUSEWARES, "1", ()),
    ("vendor catalogue code", CATALOGUE, "1", CATALOGUE_ENRICHMENT),
]


def main() -> None:
    settings = load_settings()
    embedder = GeminiEmbedder(settings)
    client = qdrant_client.QdrantClient(path=str(settings.qdrant_path))
    store = NomenclatureStore(
        artifact_dir=settings.reference_dir,
        qdrant_client=client,
        collection=settings.qdrant_collection,
        embedder=embedder,
    )

    with GenerativeModel(settings) as model:
        writer = DescriptionWriter(model, settings.prompts_dir)
        classifier = Classifier(store=store, model=model, prompts_dir=settings.prompts_dir)

        print("=" * 100)
        print(classifier.graph.describe())
        print("=" * 100)
        print(f"features        : {classifier.features.model_dump()}")
        print(f"nomenclature    : vintage {store.vintage}")
        print(f"embedding       : {store.embedding_pairing[0]} at "
              f"{store.embedding_pairing[1]} dimensions")

        for label, source, line_id, enrichments in CASES:
            descriptions = [
                writer.write(context)
                for context in build_line_contexts(source, enrichments)
            ]
            lines = build_classification_lines(source, descriptions, enrichments)
            subject = next(one for one in lines if one.line_id == line_id)
            report(label, subject, classifier.classify(subject))


def report(label: str, subject, result) -> None:
    print()
    print("=" * 100)
    print(f"CASE  {label}")
    print(f"      invoice name   : {subject.source_name}")
    print(f"      armenian text  : {subject.description_hy}")
    print(f"      search term    : {subject.search_term_hy}")
    if subject.printed_code:
        print(f"      printed code   : {subject.printed_code.value}")
    if subject.catalogue_code:
        print(f"      catalogue code : {subject.catalogue_code.value}")
    print("-" * 100)
    print(f"  decided by        : {result.decided_by}")
    print(f"  code              : {result.code.value if result.code else '(abstained)'}")
    print(f"  confidence        : {result.confidence}")
    print(f"  needs review      : {result.needs_review}")
    print(f"  supplementary unit: {result.supplementary_unit or '(none)'}")
    print(f"  legal basis       : {result.legal_basis or '(none)'}")
    print(f"  material decisive : {result.material_decisive}"
          f"   assumed: {result.material_assumed or '(none)'}")
    print(f"  rationale         : {result.rationale}")
    if result.resolving_evidence:
        print(f"  would be resolved by: {result.resolving_evidence}")
    print(f"  candidates        : {len(result.candidates)}")
    for candidate in result.candidates:
        mark = "->" if result.code and candidate.code == result.code.value else "  "
        print(f"   {mark} {candidate.similarity:.4f}  {candidate.render()[:150]}")
    print("  trace")
    for step in result.steps:
        cost = ""
        if step.call is not None:
            cost = f"  [{step.call.tier.value} {step.call.model_id}]"
        print(f"    {step.node}{cost}")
        print(f"        {step.detail}")


if __name__ == "__main__":
    main()
