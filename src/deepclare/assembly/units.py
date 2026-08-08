"""Dossier 03 §4.1 — the four-tier unit ladder. Always resolved, never blank.

A goods line must be filed in some unit, so the ladder ends in a default rather than in an
absence. What it must never do is resolve *quietly*: each tier is a different claim about
where the unit came from, the tier is recorded on every line, and the last one is always
flagged.

  1. the nomenclature's own supplementary unit for the assigned code — authoritative
  2. the invoice's own unit column
  3. what the goods physically are, from the description stage
  4. kilograms, because something has to be filed

A code-versus-invoice disagreement is settled in the code's favour and reported: the
nomenclature prescribes what box 41 counts, the invoice states what the seller sold by,
and the two disagreeing is exactly the shape that files a magnitude under a count label.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from deepclare.assembly.errors import AssemblyError
from deepclare.assembly.inputs import LineDraft, UnitResolution, UnitTier
from deepclare.assembly.tables import ReferenceTables, UnitEntry
from deepclare.assembly.trace import COMPUTED, DEFAULTED, Review, VERBATIM, derived
from deepclare.domain import Traced

_CONFIDENCE_BY_TIER = {
    UnitTier.CODE_SUPPLEMENTARY: VERBATIM,
    UnitTier.INVOICE: VERBATIM,
    UnitTier.PRODUCT_KIND: COMPUTED,
    UnitTier.KILOGRAM_DEFAULT: DEFAULTED,
}


class ResolvedUnit(BaseModel):
    """The unit one line is filed in, with the account of how it was chosen."""

    model_config = ConfigDict(frozen=True)

    resolution: UnitResolution
    code: Traced[str]
    name: Traced[str]

    @property
    def okei(self) -> str:
        return self.resolution.okei


def resolve_unit(draft: LineDraft, tables: ReferenceTables, review: Review) -> ResolvedUnit:
    """Walk the ladder for one line, and say which rung answered."""
    line_id = draft.line_id
    invoice_text = draft.line.unit.value if draft.line.unit is not None else None
    invoice_unit = tables.resolve_unit(invoice_text)

    tier, okei, source_text = _walk(draft, tables, invoice_unit, invoice_text)
    conflicted = (
        tier is UnitTier.CODE_SUPPLEMENTARY
        and invoice_unit is not None
        and invoice_unit != okei
    )

    _report(tier, okei, invoice_unit, source_text, conflicted, line_id, tables, review)

    entry = _emittable(okei, tables)
    resolution = UnitResolution(
        line_id=line_id,
        tier=tier,
        okei=entry.okei,
        name_hy=entry.name_hy,
        source_text=source_text,
        conflicted_with_invoice=conflicted,
    )
    rule = f"unit resolved at tier {tier.value}"
    confidence = _CONFIDENCE_BY_TIER[tier]
    return ResolvedUnit(
        resolution=resolution,
        code=derived(entry.okei, rule, confidence),
        name=derived(entry.name_hy, rule, confidence),
    )


def _walk(
    draft: LineDraft,
    tables: ReferenceTables,
    invoice_unit: str | None,
    invoice_text: str | None,
) -> tuple[UnitTier, str, str | None]:
    """The ladder itself, with nothing else in it."""
    supplementary = draft.classification.supplementary_unit
    from_code = tables.resolve_unit(supplementary)
    if from_code is not None:
        return UnitTier.CODE_SUPPLEMENTARY, from_code, supplementary

    if invoice_unit is not None:
        return UnitTier.INVOICE, invoice_unit, invoice_text

    kind = draft.description.product_kind.value
    from_kind = tables.product_kind_units.get(kind)
    if from_kind is not None:
        return UnitTier.PRODUCT_KIND, from_kind, str(kind)

    return UnitTier.KILOGRAM_DEFAULT, tables.kilogram_code, None


def _report(
    tier: UnitTier,
    okei: str,
    invoice_unit: str | None,
    source_text: str | None,
    conflicted: bool,
    line_id: str,
    tables: ReferenceTables,
    review: Review,
) -> None:
    """What the operator is told about how this line's unit was chosen."""
    if conflicted:
        review.needs_review(
            "line supplementary unit",
            f"The nomenclature prescribes {tables.unit(okei).name_hy} for the assigned "
            f"commodity code and the invoice states "
            f"{tables.unit(invoice_unit).name_hy if invoice_unit else 'nothing'}. The "
            "code wins, because it is what box 41 is counted in — but check the figure "
            "is really expressed in that unit and not in the seller's.",
            line_id=line_id,
            remedy="The quantity restated in the unit the commodity code prescribes.",
        )
        return
    if tier is UnitTier.CODE_SUPPLEMENTARY and invoice_unit is None:
        review.guess(
            "line supplementary unit",
            f"The commodity code prescribes {tables.unit(okei).name_hy} and the invoice "
            "states no unit at all, so nothing confirms it.",
            line_id=line_id,
        )
    elif tier is UnitTier.PRODUCT_KIND:
        review.guess(
            "line supplementary unit",
            f"Neither the commodity code nor the invoice names a unit, so "
            f"{tables.unit(okei).name_hy} was inferred from the goods being "
            f"{source_text} by nature.",
            line_id=line_id,
            remedy="The unit the goods are actually counted or measured in.",
        )
    elif tier is UnitTier.KILOGRAM_DEFAULT:
        review.guess(
            "line supplementary unit",
            "Nothing on this line names a unit — not the commodity code, not the invoice "
            "column, not the goods themselves — so box 41 falls back to kilograms. A unit "
            "must always resolve, and this is the rung that guarantees it.",
            line_id=line_id,
            remedy="The unit the goods are counted or measured in.",
        )


def _emittable(okei: str, tables: ReferenceTables) -> UnitEntry:
    """The unit entry, having confirmed the portal can file it.

    Dossier 11 §D6 states the invariant: the set of units this product can emit must be a
    subset of the portal's own 32-unit classifier, because a unit outside it cannot be
    filed at all. That classifier did not transfer; what stands in for it is the curated
    unit table, whose thirteen rows are units the predecessor filed and the portal
    accepted. Resolution can only ever produce a code from that table, so this can only
    fail on a table that has been edited into an inconsistent state — which is exactly
    when it should.
    """
    entry = tables.unit_by_code.get(okei)
    if entry is None:
        raise AssemblyError(
            f"unit {okei!r} was resolved and is not in the curated unit table, so nothing "
            "can say whether the portal is able to file it. A unit outside the portal's "
            "own classifier cannot be filed at all."
        )
    return entry
