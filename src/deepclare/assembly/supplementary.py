"""Dossier 03 §4.2 — the quantity–unit pairing rule. Box 41.

One sentence carries the whole module: **a figure is filed only in a unit it is genuinely
expressed in.** A kilogram magnitude filed under a piece code is not an imprecise
declaration, it is a false one, and the portal will accept it without a murmur.

Count units are exactly three — pieces, pairs, thousands of pieces — and everything else
is a magnitude. A count unit takes a count and nothing else; a magnitude takes a figure
measured in that magnitude and nothing else.

The fallback exists for a mechanical reason rather than a legal one: **a goods line with
no supplementary quantity hangs the portal's import at 100% with no message at all**. So
when no figure in the resolved unit exists, the line's own weight is filed as kilograms —
a genuine figure in its own unit, under its own label, with the operator told the unit is
not the one the code wants. Only a line with no quantity *and* no weight files nothing.
"""

from __future__ import annotations

from decimal import Decimal

from deepclare.assembly.quantities import LineQuantities
from deepclare.assembly.tables import ReferenceTables
from deepclare.assembly.trace import Review, VERBATIM, derived
from deepclare.assembly.units import ResolvedUnit
from deepclare.assembly.weights import LineWeights
from deepclare.domain import InvoiceGoodsLine, SupplementaryQuantity, Traced


def resolve_supplementary_quantity(
    line: InvoiceGoodsLine,
    unit: ResolvedUnit,
    quantities: LineQuantities,
    weights: LineWeights,
    tables: ReferenceTables,
    review: Review,
) -> SupplementaryQuantity | None:
    """The figure box 41 files, in the unit it is genuinely expressed in, or nothing."""
    figure = _figure_in_the_resolved_unit(line, unit, quantities, weights, tables)
    if figure is not None:
        return SupplementaryQuantity(
            quantity=figure, unit_code=unit.code, unit_name=unit.name
        )
    return _weight_fallback(line, unit, weights, tables, review)


def _figure_in_the_resolved_unit(
    line: InvoiceGoodsLine,
    unit: ResolvedUnit,
    quantities: LineQuantities,
    weights: LineWeights,
    tables: ReferenceTables,
) -> Traced[Decimal] | None:
    """A figure this line genuinely states in the resolved unit, or None.

    The order matters only where two sources could both answer. Kilograms take the net
    weight before an invoice quantity because the weight is what the box means; pieces
    take the piece arithmetic because the invoice's own quantity column may be counting
    packages.
    """
    okei = unit.okei
    invoice_unit = (
        tables.resolve_unit(line.unit.value) if line.unit is not None else None
    )

    if okei == tables.kilogram_code:
        if weights.net is not None:
            return weights.net
        if invoice_unit == tables.kilogram_code and line.quantity is not None:
            return line.quantity
        return None

    if okei == tables.pieces_code:
        return quantities.total_items

    # Everything else — pairs, thousands, metres, square metres, litres, tonnes — is
    # filed only from a figure the invoice itself stated in that same unit. There is no
    # producer in this product for a model-estimated total, so nothing else can be.
    if invoice_unit == okei and line.quantity is not None:
        return line.quantity
    return None


def _weight_fallback(
    line: InvoiceGoodsLine,
    unit: ResolvedUnit,
    weights: LineWeights,
    tables: ReferenceTables,
    review: Review,
) -> SupplementaryQuantity | None:
    """The line's weight as kilograms, because an empty box 41 hangs the import.

    Graded by what the resolved unit was. If it was kilograms, this is the same unit by
    another route and a soft guess. If it was anything else, the filed figure is in the
    wrong unit for the commodity code — the portal imports it without complaint and box
    41 then says something the code does not mean, so the operator is told to restate it.
    """
    weight = weights.net or weights.gross
    if weight is None:
        review.needs_review(
            "line supplementary quantity",
            "This line states no quantity in "
            f"{unit.resolution.name_hy} and carries no weight to fall back on, so box 41 "
            "is empty. A goods line without it hangs the portal's import at 100% with no "
            "message; supply a figure before importing the file.",
            line_id=line.line_id,
            remedy="Any genuine figure for the line, with the unit it is expressed in.",
        )
        return None

    kilogram = tables.unit(tables.kilogram_code)
    which = "net" if weights.net is not None else "gross"
    if unit.okei == tables.kilogram_code:
        review.guess(
            "line supplementary quantity",
            f"The invoice states no quantity in kilograms, so the line's {which} weight "
            f"of {weight.value} kg was filed as the quantity. It is a genuine figure in "
            "the right unit, but it is the weight rather than a stated quantity.",
            line_id=line.line_id,
        )
    else:
        review.needs_review(
            "line supplementary quantity",
            f"The commodity code counts this line in {unit.resolution.name_hy} and "
            f"nothing on the line states a figure in that unit, so the {which} weight of "
            f"{weight.value} kg was filed instead, labelled as kilograms. The portal "
            "imports this without complaint and box 41 is then in the wrong unit for the "
            f"code — restate the quantity in {unit.resolution.name_hy} on the portal.",
            line_id=line.line_id,
            remedy=f"The line's quantity in {unit.resolution.name_hy}.",
        )

    rule = f"line {which} weight filed as the supplementary quantity in kilograms"
    return SupplementaryQuantity(
        quantity=weight,
        unit_code=derived(kilogram.okei, rule, VERBATIM),
        unit_name=derived(kilogram.name_hy, rule, VERBATIM),
    )
