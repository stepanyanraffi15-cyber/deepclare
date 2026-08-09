"""Manual check: five drafted lines with a deliberate inconsistency -> the real models.

Makes real, billed provider calls and opens the real reference collection, so it is NOT
collected by pytest (pyproject restricts collection to test_*.py). Run it by hand:

    .venv/bin/python tests/check_consistency_pass.py

The shipment is one family of rigid PVC pipe in four diameters plus one elbow fitting.
Three things are planted in it:

1. **The inconsistency.** Line 3 is the same product as lines 1, 2 and 5 and is described
   in different words — a bare "plastic pipe" against the family's "rigid polyvinyl
   chloride pipe, intended for water supply" — and it carries a different commodity code
   for no reason any document states.
2. **The trap.** Line 4 is a fitting, not a pipe. It is worded differently and coded
   differently because it *is* different, and a pass that conforms it to the pipes has
   made the declaration worse.
3. **The guardrails' subjects.** Every line's text ends in a size segment and a
   shipment-quantity segment that were computed downstream from the invoice's own figures.
   They are declared as deterministic segments, and a rewrite that does not reproduce one
   of them character for character is refused.

No customer document is stored here; every line below is fictitious.
"""

from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

import qdrant_client

from deepclare.classification import ExistenceGate
from deepclare.config import load_settings
from deepclare.consistency import DraftedLine, Reconciler
from deepclare.embedding import GeminiEmbedder
from deepclare.models import GenerativeModel
from deepclare.reference.store import NomenclatureStore

PIPE = "ՊՈԼԻՎԻՆԻԼՔԼՈՐԻԴԻ ԽՈՂՈՎԱԿ, ԿՈՇՏ, ՆԱԽԱՏԵՍՎԱԾ Է ՋՐԱՄԱՏԱԿԱՐԱՐՄԱՆ ՀԱՄԱՐ"
PIPE_CODE = "3917231009"


def pipe(line_id: str, diameter: str, metres: str) -> DraftedLine:
    size = f"{diameter} ՄՄ ՏՐԱՄԱԳԾՈՎ"
    quantity = f"{metres} ՄԵՏՐ"
    return DraftedLine(
        line_id=line_id,
        source_name=f"PVC PIPE {diameter}MM",
        description=f"{PIPE}, {size}, {quantity}",
        deterministic_segments=(size, quantity),
        code=PIPE_CODE,
    )


DRAFT = [
    pipe("1", "32", "500"),
    pipe("2", "40", "300"),
    # The planted inconsistency: same goods as 1, 2 and 5, worded unlike them and coded
    # unlike them.
    DraftedLine(
        line_id="3",
        source_name="PVC PIPE 50MM",
        description="ԽՈՂՈՎԱԿ ՊԼԱՍՏՄԱՍՍԵ, 50 ՄՄ ՏՐԱՄԱԳԾՈՎ, 200 ՄԵՏՐ",
        deterministic_segments=("50 ՄՄ ՏՐԱՄԱԳԾՈՎ", "200 ՄԵՏՐ"),
        code="3917320009",
    ),
    # The trap: a fitting, not a pipe. It is supposed to read and code differently.
    DraftedLine(
        line_id="4",
        source_name="PVC ELBOW 32MM 90 DEG",
        description=(
            "ՊՈԼԻՎԻՆԻԼՔԼՈՐԻԴԻ ԱՆԿՅՈՒՆԱԿ ԿՑՈՐԴԻՉ, ՆԱԽԱՏԵՍՎԱԾ Է ԽՈՂՈՎԱԿՆԵՐԻ "
            "ՄԻԱՑՄԱՆ ՀԱՄԱՐ, 32 ՄՄ, 200 ՀԱՏ"
        ),
        deterministic_segments=("32 ՄՄ", "200 ՀԱՏ"),
        code="3917400009",
    ),
    pipe("5", "63", "150"),
]


def main() -> None:
    settings = load_settings()
    client = qdrant_client.QdrantClient(path=str(settings.qdrant_path))
    store = NomenclatureStore(
        artifact_dir=settings.reference_dir,
        qdrant_client=client,
        collection=settings.qdrant_collection,
        embedder=GeminiEmbedder(settings),
    )

    show("BEFORE", [(line.line_id, line.description, line.code) for line in DRAFT])

    with GenerativeModel(settings) as model:
        outcome = Reconciler(
            existence_gate=ExistenceGate(store),
            model=model,
            prompts_dir=settings.prompts_dir,
        ).reconcile(DRAFT)

    show("AFTER", [(line.line_id, line.description, line.code) for line in outcome.lines])

    print()
    print("=" * 100)
    print(f"outcome        : {outcome.outcome.value}")
    print(f"detail         : {outcome.detail}")
    print(f"changed lines  : {', '.join(outcome.changed_line_ids) or '(none)'}")
    print(f"model calls    : {len(outcome.calls)}")
    for call in outcome.calls:
        print(f"    {call.prompt_name} v{call.prompt_version}  [{call.tier.value} "
              f"{call.model_id}]  {call.usage.total_tokens} tokens")

    print()
    print("CHANGES")
    for change in outcome.changes or ():
        print(f"  line {change.line_id} · {change.field.value} "
              f"[{change.transform.operation}]")
        print(f"      before : {change.transform.before or '(none)'}")
        print(f"      after  : {change.transform.after or '(none)'}")
        print(f"      because: {change.transform.reason}")
    if not outcome.changes:
        print("  (none)")

    print()
    print("REFUSED BY A GUARDRAIL")
    for refusal in outcome.rejected or ():
        print(f"  line {refusal.line_id} · {refusal.field.value}")
        print(f"      proposed: {refusal.proposed}")
        print(f"      refused : {refusal.reason}")
    if not outcome.rejected:
        print("  (none)")

    print()
    print("SHIPMENT NOTES")
    for note in outcome.shipment_notes or ("(none)",):
        print(f"  {note}")

    print()
    print("REVIEW ITEMS")
    for item in outcome.review_items or ():
        where = f"line {item.line_id}" if item.line_id else "shipment"
        print(f"  [{item.kind.value}] {where} · {item.concept}")
        print(f"      {item.detail}")
        if item.remedy:
            print(f"      remedy: {item.remedy}")
    if not outcome.review_items:
        print("  (none)")


def show(label: str, rows: list[tuple[str, str, str | None]]) -> None:
    print()
    print("=" * 100)
    print(label)
    print("=" * 100)
    for line_id, text, code in rows:
        print(f"  line {line_id}  [{code or 'abstained'}]  {text}")


if __name__ == "__main__":
    main()
