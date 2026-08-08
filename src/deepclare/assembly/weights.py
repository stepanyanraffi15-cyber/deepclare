"""Dossier 03 §4.4 — per-line gross and net weight.

The rule the whole module turns on: **the invoice is authoritative**. A line carrying its
own weights files them, never scaled and never second-guessed. Only the lines the invoice
left blank are inferred, and every inferred figure is a review guess.

The distribution is the broker's own manual reconciliation, and it has one property that
is not negotiable: **the per-line grosses must sum to the consignment note's total
exactly**. Rounding each share to two decimals and hoping is not that; the residual is
placed on the largest allocation so the sum closes on the nose. A declaration whose
weights do not reconcile with the manifest is one a customs officer will notice.

When there is nothing to distribute from — no consignment-note total, or a total that is
not above the weights the invoice already fixed — nothing is distributed. Negative or
fabricated weights are worse than blank ones.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict

from deepclare.assembly.inputs import AssemblyInput, LineDraft
from deepclare.assembly.tables import ReferenceTables
from deepclare.assembly.trace import (
    COARSE,
    DISTRIBUTED,
    Review,
    derived,
    restated,
    transform,
)
from deepclare.domain import ConsignmentNote, InvoiceGoodsLine, Traced

CENT = Decimal("0.01")
NET_OF_GROSS = Decimal("0.9")
"""Dossier 03 §4.4 — filed declarations run 0.85 to 0.95 net over gross. A coarse
stand-in, always at or below gross by construction, pending per-good research."""


class LineWeights(BaseModel):
    """One line's resolved weights, in kilograms."""

    model_config = ConfigDict(frozen=True)

    line_id: str
    gross: Traced[Decimal] | None = None
    net: Traced[Decimal] | None = None
    gross_was_distributed: bool = False


def resolve_weights(
    submission: AssemblyInput, tables: ReferenceTables, review: Review
) -> dict[str, LineWeights]:
    """Every line's gross and net, keyed by line id.

    Two passes, because the second depends on the first: the invoice's own weights are
    read first and become the fixed sum the distribution works against.
    """
    printed = {
        draft.line_id: _printed_weights(draft.line, tables, review)
        for draft in submission.lines
    }
    distributed = _distribute(submission, printed, review)

    resolved: dict[str, LineWeights] = {}
    for draft in submission.lines:
        line_id = draft.line_id
        gross, net = printed[line_id]
        was_distributed = False
        if gross is None and line_id in distributed:
            gross = distributed[line_id]
            was_distributed = True
        if net is None and gross is not None:
            net = _net_from_gross(gross, line_id, review, was_distributed)
        if gross is None:
            review.omitted(
                "line gross weight",
                "The invoice printed no weight for this line and nothing could be "
                "apportioned to it, so no gross weight was filed.",
                line_id=line_id,
                remedy="The line's gross weight, or a consignment-note total above the "
                "weights the invoice already fixes.",
            )
            review.omitted(
                "line net weight",
                "There is no gross weight for this line, so there is nothing to derive a "
                "net weight from either.",
                line_id=line_id,
            )
        elif net is not None and net.value > gross.value:
            review.needs_review(
                "line net weight",
                f"The invoice prints a net weight of {net.value} kg against a gross of "
                f"{gross.value} kg. Both were filed as printed — the invoice is "
                "authoritative — but net above gross is not physically possible and one "
                "of the two was misread or misprinted.",
                line_id=line_id,
                remedy="Which of the two figures the invoice actually states.",
            )
        resolved[line_id] = LineWeights(
            line_id=line_id, gross=gross, net=net, gross_was_distributed=was_distributed
        )
    return resolved


def _printed_weights(
    line: InvoiceGoodsLine, tables: ReferenceTables, review: Review
) -> tuple[Traced[Decimal] | None, Traced[Decimal] | None]:
    """What the invoice states for this line, converted into kilograms."""
    return (
        _in_kilograms(line.gross_weight, line, tables, review, "line gross weight"),
        _in_kilograms(line.net_weight, line, tables, review, "line net weight"),
    )


def _in_kilograms(
    weight: Traced[Decimal] | None,
    line: InvoiceGoodsLine,
    tables: ReferenceTables,
    review: Review,
    concept: str,
) -> Traced[Decimal] | None:
    """A printed weight as kilograms, converting when the column says something else.

    Dossier 05 §6.1 records the cautionary case as a live bug: an extraction carrying
    tonne magnitudes filed the tonne figure under the kilogram element, a 1000x error on
    a legal document. Copying a magnitude across unit labels is the bug class, so the
    conversion happens here, once, with the factor recorded in the transform chain.
    """
    if weight is None:
        return None
    printed_unit = line.weight_unit.value if line.weight_unit is not None else None
    if printed_unit is None or not printed_unit.strip():
        return weight

    okei = tables.resolve_unit(printed_unit)
    factor = tables.kilograms_per(okei) if okei is not None else None
    if factor is None:
        review.needs_review(
            concept,
            f"The weight column is labelled {printed_unit!r}, which is not a mass this "
            f"product recognises. {weight.value} was filed as kilograms unchanged.",
            line_id=line.line_id,
            remedy="What unit the weight column is in.",
        )
        return weight
    if factor == 1:
        return weight
    converted = (weight.value * factor).quantize(CENT, rounding=ROUND_HALF_UP)
    review.guess(
        concept,
        f"The invoice states {weight.value} {printed_unit}, which is {converted} kg. The "
        "declaration files kilograms, so the figure was converted.",
        line_id=line.line_id,
    )
    return restated(
        weight,
        converted,
        transform(
            f"unit-convert-{printed_unit.strip().upper()}-to-kg",
            weight.value,
            converted,
            "the filed weight elements are kilograms and a magnitude copied across unit "
            "labels is a 1000x error",
        ),
    )


def _distribute(
    submission: AssemblyInput,
    printed: dict[str, tuple[Traced[Decimal] | None, Traced[Decimal] | None]],
    review: Review,
) -> dict[str, Traced[Decimal]]:
    """Share the consignment note's total gross across the lines the invoice left blank.

    Returns nothing at all rather than a partial answer: if the budget is not positive or
    no key exists, the lines stay unweighted and say so.
    """
    blank = [draft for draft in submission.lines if printed[draft.line_id][0] is None]
    if not blank:
        return {}

    note = submission.consignment_note
    total = note.gross_weight if note is not None else None
    if total is None:
        return {}

    fixed = sum(
        (gross.value for gross, _ in printed.values() if gross is not None), Decimal(0)
    )
    budget = total.value - fixed
    if budget <= 0:
        review.needs_review(
            "shipment gross weight",
            f"The consignment note states {total.value} kg in total and the invoice "
            f"already fixes {fixed} kg across its own lines, leaving nothing to "
            f"apportion to the {len(blank)} line(s) it left blank. Nothing was "
            "distributed: a negative or invented weight is worse than a blank one.",
            remedy="Per-line weights on the invoice, or a corrected consignment-note "
            "total.",
        )
        return {}

    key = _distribution_key(blank)
    if key is None:
        review.needs_review(
            "shipment gross weight",
            f"{len(blank)} line(s) carry no weight, and they share no quantity and no "
            "invoiced value to apportion by. Nothing was distributed.",
            remedy="A quantity or a line total for each unweighted line.",
        )
        return {}

    shares, basis = key
    allocations = _allocate(budget, shares)
    note_id = note.source_document_id if note is not None else "the consignment note"
    for draft in blank:
        review.guess(
            "line gross weight",
            f"The invoice states no weight for this line. {allocations[draft.line_id]} kg "
            f"is its share of the {budget} kg the consignment note leaves after the "
            f"weights the invoice fixes, apportioned by {basis}. Every line's share is a "
            "guess; together they reconcile to the manifest exactly.",
            line_id=draft.line_id,
            remedy="The line's own weight from the packing list or the supplier.",
        )
    return {
        line_id: derived(
            amount,
            f"gross distributed from consignment-note total by {basis}, residual on the "
            f"largest share, sourced from {note_id}",
            DISTRIBUTED,
        )
        for line_id, amount in allocations.items()
    }


def _distribution_key(blank: list[LineDraft]) -> tuple[dict[str, Decimal], str] | None:
    """The share each unweighted line takes, and the name of the basis.

    Quantity first, then invoiced value, then equal shares — and a basis counts only when
    **every** unweighted line has it. A key present on some lines and not others is not a
    key; it silently gives the lines that lack it nothing.
    """
    quantities = {
        draft.line_id: draft.line.quantity.value
        for draft in blank
        if draft.line.quantity is not None and draft.line.quantity.value > 0
    }
    if len(quantities) == len(blank):
        return quantities, "quantity share"

    values = {
        draft.line_id: draft.line.total_price.value
        for draft in blank
        if draft.line.total_price is not None and draft.line.total_price.value > 0
    }
    if len(values) == len(blank):
        return values, "invoiced-value share"

    return {draft.line_id: Decimal(1) for draft in blank}, "equal shares"


def _allocate(budget: Decimal, shares: dict[str, Decimal]) -> dict[str, Decimal]:
    """Split a budget in proportion to shares, to the cent, summing to the budget exactly.

    Each allocation is rounded to two decimals and the residual — whatever the rounding
    lost or gained — goes onto the largest one, where it is proportionally smallest. The
    sum is then the budget by construction rather than by luck.
    """
    total_share = sum(shares.values())
    allocations = {
        line_id: (budget * share / total_share).quantize(CENT, rounding=ROUND_HALF_UP)
        for line_id, share in shares.items()
    }
    residual = budget - sum(allocations.values())
    if residual != 0:
        largest = max(allocations, key=lambda line_id: (allocations[line_id], line_id))
        allocations[largest] += residual
    return allocations


def _net_from_gross(
    gross: Traced[Decimal], line_id: str, review: Review, gross_was_distributed: bool
) -> Traced[Decimal]:
    """The coarse stand-in for a net weight the invoice does not print."""
    net = (gross.value * NET_OF_GROSS).quantize(CENT, rounding=ROUND_HALF_UP)
    review.guess(
        "line net weight",
        f"The invoice states no net weight for this line, so {net} kg was filed — nine "
        f"tenths of the {gross.value} kg gross. Filed declarations run between 0.85 and "
        "0.95 net over gross; this is a coarse stand-in and not a measurement of these "
        "goods.",
        line_id=line_id,
        remedy="The line's net weight, or the packaging weight to subtract.",
    )
    source_rule = (
        "net at nine tenths of a distributed gross"
        if gross_was_distributed
        else "net at nine tenths of the printed gross"
    )
    return derived(
        net,
        source_rule,
        COARSE,
        transforms=(
            transform(
                "net-from-gross-0.9",
                gross.value,
                net,
                "no net weight was printed and the filed declaration needs one",
            ),
        ),
    )
