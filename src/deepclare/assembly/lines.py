"""One goods line, from its drafts to the item that will be filed.

The order the steps run in is the order the rules depend on each other, and it is not
rearrangeable: packages and pieces first, because the unit ladder's fallback and box 31's
sentence both read them; the unit next; then the figure, which needs both; then the text,
which must state the same numbers the figure does.

Two of this module's rules are legal rather than arithmetic:

* **No duty preference is ever claimed.** A preference is derivable — in the corpus every
  preferential line is Iranian-origin under the EAEU–Iran agreement — and it is
  deliberately never derived. Claiming one the goods do not qualify for under-declares
  duty, which is consequential; the safe marker merely over-declares and is corrected on
  the portal. The operator is told what their own history did instead.
* **A code is filed or it is not.** An abstention files nothing and hands over the
  classifier's rationale and the fact that would resolve it. Box 33 is validated
  server-side against the portal's own nomenclature, so a guess is rejected by name rather
  than quietly accepted.
"""

from __future__ import annotations

from decimal import Decimal

from deepclare.assembly.countries import line_origin
from deepclare.assembly.descriptions import assemble_description
from deepclare.assembly.inputs import LineDraft, UnitResolution
from deepclare.assembly.quantities import LineQuantities, resolve_quantities
from deepclare.assembly.supplementary import resolve_supplementary_quantity
from deepclare.assembly.tables import ReferenceTables
from deepclare.assembly.trace import Review, VERBATIM, constant, restated, transform
from deepclare.assembly.units import resolve_unit
from deepclare.assembly.weights import LineWeights
from deepclare.domain import (
    CodedValue,
    ConsignmentNote,
    GoodsItem,
    Packaging,
    Traced,
)

NATIONAL_SUBDIVISION_DIGIT = "0"
"""The eleventh digit of a filed commodity code. Zero on 97.7% of the corpus; the non-zero
national splits are not in the ten-digit index and cannot be reached from it."""

TRANSACTION_VALUE = "1"
RESERVE_METHOD = "6"
PACKAGED = "1"
"""The portal's 0/1/2 packaging classifier. Always a guess — the operator picks."""

IRANIAN_ORIGIN = "IR"


def assemble_line(
    draft: LineDraft,
    item_number: int,
    weights: LineWeights,
    note: ConsignmentNote | None,
    invoice_origin: Traced[str] | None,
    single_line_shipment: bool,
    tables: ReferenceTables,
    review: Review,
) -> tuple[GoodsItem, UnitResolution]:
    """Everything one goods line files."""
    line = draft.line
    quantities = resolve_quantities(draft, note, single_line_shipment, tables, review)
    unit = resolve_unit(draft, tables, review)
    supplementary = resolve_supplementary_quantity(
        line, unit, quantities, weights, tables, review
    )
    description = assemble_description(
        draft.description, line, quantities, supplementary, tables, review
    )
    origin = line_origin(line.origin_country, invoice_origin, tables, review, draft.line_id)

    _report_preference(origin, draft.line_id, review)

    return (
        GoodsItem(
            item_number=item_number,
            line_id=draft.line_id,
            description=description,
            gross_weight=weights.gross,
            net_weight=weights.net,
            invoiced_cost=_invoiced_cost(draft, review),
            commodity_code=_filed_code(draft, review),
            origin_country=origin,
            customs_cost_method=_customs_cost_method(draft, review),
            supplementary_quantity=supplementary,
            packaging=_packaging(quantities, review, draft.line_id),
        ),
        unit.resolution,
    )


def _invoiced_cost(draft: LineDraft, review: Review) -> Traced[Decimal] | None:
    """Box 42 — the line's own total price, printed or nothing.

    Deliberately not derived from a unit price times the quantity. The quantity column is
    routinely a package count while the unit price is per item, and the two multiplied
    then give a value that is wrong by the pack size on a field customs assesses duty from.
    """
    if draft.line.total_price is not None:
        return draft.line.total_price
    review.omitted(
        "line invoiced value",
        "The invoice prints no line total, so box 42 was left out. It was not computed "
        "from the unit price: the quantity column may be counting packages, and the "
        "product of the two would then be wrong by the pack size on the field duty is "
        "assessed from.",
        line_id=draft.line_id,
        remedy="The line's total price.",
    )
    return None


def _customs_cost_method(draft: LineDraft, review: Review) -> Traced[str]:
    """Box 43 — transaction value where a sale price exists, the reserve method otherwise.

    EAEU Customs Code articles 39 and 45: method 1 is the default whenever a sale price
    exists. Customs may later re-determine the value to method 6, which is a correction
    made after filing and is never pre-empted here.
    """
    if draft.line.total_price is not None:
        return constant(
            TRANSACTION_VALUE, "transaction value, the line carries a sale price"
        )
    review.guess(
        "line customs-value method",
        "The invoice prices this line nowhere, so the reserve method was filed rather "
        "than transaction value. Confirm it: transaction value is the correct method "
        "whenever a sale price exists, and customs re-determining the value afterwards "
        "is not something this draft predicts.",
        line_id=draft.line_id,
        remedy="The line's price, which would make this transaction value.",
    )
    return constant(RESERVE_METHOD, "reserve method, the line carries no sale price")


def _filed_code(draft: LineDraft, review: Review) -> Traced[str] | None:
    """Box 33 — the ten-digit leaf plus the Armenian national subdivision digit."""
    classification = draft.classification
    if classification.code is None:
        review.omitted(
            "line commodity code",
            f"Classification abstained on this line. {classification.rationale}",
            line_id=draft.line_id,
            remedy=classification.resolving_evidence
            or "A commodity code chosen on the portal.",
        )
        return None

    leaf = classification.code.value
    filed = leaf + NATIONAL_SUBDIVISION_DIGIT
    if classification.needs_review:
        review.needs_review(
            "line commodity code",
            f"{filed} was assigned at a confidence of {classification.confidence:.2f} and "
            f"is flagged for confirmation. {classification.rationale}",
            line_id=draft.line_id,
            remedy=classification.resolving_evidence
            or "Confirm the code against the goods themselves.",
        )
    return restated(
        classification.code,
        filed,
        transform(
            "append-national-subdivision-digit",
            leaf,
            filed,
            "the filed code carries an eleventh Armenian national digit, zero on all but "
            "the rare national splits, which are not reachable from the ten-digit index",
        ),
    )


def _packaging(quantities: LineQuantities, review: Review, line_id: str) -> Packaging:
    """Boxes 6 and 31 — how many packages, of what kind, in what packing.

    The 0/1/2 classifier is filed on every line as a guess. It is a product decision
    rather than an importer requirement: putting the dropdown in front of the operator on
    every line is what stops a bulk consignment being filed as packaged by omission.
    """
    review.guess(
        "line packaging classifier",
        "The line was filed as packaged, which is the default. The portal offers three "
        "values — without packaging, packaged, and unpackaged in equipped containers — "
        "and nothing in the documents chooses between them.",
        line_id=line_id,
    )
    return Packaging(
        package_count=quantities.package_count,
        package_type_code=constant(PACKAGED, "the portal's packaged classifier, defaulted"),
        packing_code=quantities.packing_code,
        packing_quantity=quantities.package_count
        if quantities.packing_code is not None
        else None,
    )


def _report_preference(origin: CodedValue | None, line_id: str, review: Review) -> None:
    """The duty preference that is derivable and is never derived.

    Told, not filed. The asymmetry decides it: filing a preference these goods may not
    qualify for under-declares duty and is legally consequential, while the safe marker
    over-declares and is corrected on the portal in a minute.
    """
    if origin is None or origin.code.value != IRANIAN_ORIGIN:
        return
    review.needs_review(
        "line duty preference",
        "These goods are of Iranian origin, and in the filed corpus 89% of Iranian-origin "
        "lines claim the EAEU–Iran free-trade preference on customs duty. The no-privilege "
        "marker was filed instead and no preference was claimed. Claim it on the portal "
        "only if these goods qualify and you hold the certificate of origin: claiming one "
        "they do not qualify for under-declares duty.",
        line_id=line_id,
        remedy="A EUR.1 or equivalent certificate of origin for these goods.",
    )
