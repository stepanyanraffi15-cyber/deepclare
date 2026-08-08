"""Dossier 03 §5.5 — the filed goods description, box 31.

The description-writing stage produces the Armenian naming text. This module appends the
two deterministic segments to it: the size the invoice printed, and the quantity that was
computed. They are appended here rather than written there for one reason — **the
description model never computes a quantity**. Every figure in filed text is arithmetic
this module already did, so the sentence and box 41 cannot disagree.

    <naming text>, <size segment>, <quantity segment>

Each segment can be absent. The size segment is suppressed when the naming text already
states that size, matched on the numeric core so a `3*2.5` inside a cable designation
suppresses a `3*2.5MM2` restatement. The plain piece count is suppressed when box 41 files
exactly that figure as pieces — the majority filed convention — while the pack-math form
is always kept, because `2 ՏՈՒՓ 8 ՀԱՏԱՆՈՑ-16 ՀԱՏ` says something a bare `16 ՀԱՏ` does not.
"""

from __future__ import annotations

import re
from decimal import Decimal

from deepclare.assembly.quantities import LineQuantities
from deepclare.assembly.tables import ReferenceTables
from deepclare.assembly.trace import COMPUTED, Review, restated, transform
from deepclare.description.records import LineDescription, ProductKind
from deepclare.domain import InvoiceGoodsLine, SupplementaryQuantity, Traced

SEPARATOR = ", "

_DIGIT_RUN = re.compile(r"\d+(?:[.,]\d+)*")
_UNIT_AFTER_DIGIT = re.compile(r"(?<=\d)\s*([A-Za-z]+[0-9]?)")


def assemble_description(
    written: LineDescription,
    line: InvoiceGoodsLine,
    quantities: LineQuantities,
    filed_quantity: SupplementaryQuantity | None,
    tables: ReferenceTables,
    review: Review,
) -> Traced[str]:
    """The text box 31 carries: the naming text plus the computed segments."""
    naming = written.text.value.strip()
    segments = [naming]

    size = size_segment(line, naming, tables)
    if size is not None:
        segments.append(size)

    quantity = quantity_segment(quantities, filed_quantity, tables)
    if quantity is not None:
        segments.append(quantity)

    _report_gaps(written, line, quantities, tables, review)

    assembled = SEPARATOR.join(segments).upper()
    return restated(
        written.text,
        assembled,
        transform(
            "append-size-and-quantity-segments",
            naming,
            assembled,
            "box 31 states the size and the count as declarants write them, and every "
            "figure in it is computed rather than written by the description model",
        ),
    )


# --- the size segment -------------------------------------------------------------------


def size_segment(
    line: InvoiceGoodsLine, naming_text: str, tables: ReferenceTables
) -> str | None:
    """The invoice's printed size, Armenianised, unless the naming text already says it.

    Dossier 05 §6.8: separators become `*`, unit tokens become Armenian **only** where a
    digit precedes them — so apparel size L, a thread designation M8 and the letters
    inside a model code never convert — and the numbers stay verbatim.
    """
    if line.dimensions is None:
        return None
    printed = line.dimensions.value.strip()
    if not printed:
        return None

    armenianised = _armenianise_size(printed, tables)
    if _already_stated(naming_text, printed, tables):
        return None
    return armenianised


def _armenianise_size(printed: str, tables: ReferenceTables) -> str:
    text = printed.upper()
    for separator in tables.size_separators:
        text = re.sub(
            rf"(?<=\d)\s*{re.escape(separator.upper())}\s*(?=\d)",
            tables.size_separator_replacement,
            text,
        )

    def convert(match: re.Match[str]) -> str:
        token = match.group(1).upper()
        return tables.size_unit_by_token.get(token, match.group(1))

    return _UNIT_AFTER_DIGIT.sub(convert, text)


def _already_stated(naming_text: str, printed: str, tables: ReferenceTables) -> bool:
    """Whether the naming text already carries this size.

    Compared on the unit-stripped numeric core with digit boundaries, so `15MM` does not
    hide inside `135*115MM` and a `3*2.5` already in the text suppresses a `3*2.5MM2`.
    """
    core = _numeric_core(printed, tables)
    if not core:
        return False
    naming_core = _numeric_core(naming_text, tables)
    pattern = rf"(?<!\d){re.escape(core)}(?!\d)"
    return re.search(pattern, naming_core) is not None


def _numeric_core(text: str, tables: ReferenceTables) -> str:
    """Digits and separators only, with unit tokens and spacing taken out."""
    folded = text.upper()
    for separator in tables.size_separators:
        folded = folded.replace(separator.upper(), "*")
    folded = _UNIT_AFTER_DIGIT.sub("", folded)
    return re.sub(r"\s+", "", folded)


# --- the quantity segment ---------------------------------------------------------------


def quantity_segment(
    quantities: LineQuantities,
    filed_quantity: SupplementaryQuantity | None,
    tables: ReferenceTables,
) -> str | None:
    """The count, written as declarants write it.

    Three forms, in the order they are preferred: the pack math when the total came from
    packages times a per-package factor; a plain piece count; and, when there is no piece
    total at all, the package count with its Armenian noun.
    """
    total = quantities.total_items
    noun = tables.package_noun(
        quantities.packing_code.value if quantities.packing_code else None,
        in_pack_math=True,
    )

    if (
        total is not None
        and quantities.total_is_pack_math
        and quantities.package_count is not None
        and quantities.units_per_package is not None
    ):
        return (
            f"{_number(quantities.package_count.value)} {noun} "
            f"{_number(quantities.units_per_package)} {tables.per_package_noun}-"
            f"{_number(total.value)} {tables.piece_noun}"
        )

    if total is not None:
        if _box_41_already_states(total.value, filed_quantity, tables):
            return None
        return f"{_number(total.value)} {tables.piece_noun}"

    if quantities.package_count is not None:
        bulk_noun = tables.package_noun(
            quantities.packing_code.value if quantities.packing_code else None,
            in_pack_math=False,
        )
        return f"{_number(quantities.package_count.value)} {bulk_noun}"

    return None


def _box_41_already_states(
    total: Decimal, filed_quantity: SupplementaryQuantity | None, tables: ReferenceTables
) -> bool:
    """Whether box 41 files this very figure as pieces, making a bare count a repeat."""
    if filed_quantity is None:
        return False
    return (
        filed_quantity.unit_code.value == tables.pieces_code
        and filed_quantity.quantity.value == total
    )


def _number(value: Decimal) -> str:
    """A figure as filed text: no trailing zeros, no exponent, no thousands separator."""
    trimmed = value.normalize()
    if trimmed == trimmed.to_integral_value():
        trimmed = trimmed.quantize(Decimal(1))
    return format(trimmed, "f")


# --- what the text does not say and should ----------------------------------------------


def _report_gaps(
    written: LineDescription,
    line: InvoiceGoodsLine,
    quantities: LineQuantities,
    tables: ReferenceTables,
    review: Review,
) -> None:
    """Two content checks dossier 05 §5.4 makes, neither of which edits the text.

    A brand is never auto-inserted and a count is never invented. Both are told to the
    operator, whose wording it is.
    """
    if quantities.total_items is None and written.product_kind.value is ProductKind.PIECE:
        review.needs_review(
            "line goods description",
            "These are discrete goods and nothing on the invoice grounds a piece count, "
            "so box 31 states none. 83% of filed kilogram-unit descriptions of discrete "
            "goods still state one; it cannot be derived from a weight.",
            line_id=line.line_id,
            remedy="How many items the line holds.",
        )

    if line.trade_name is None:
        return
    brand = line.trade_name.value.strip()
    if not brand or not tables.is_brandable(brand):
        return
    if brand.upper() in written.text.value.upper():
        return
    review.needs_review(
        "line goods description",
        f"The invoice prints the trade name {brand!r} for this line and box 31 does not "
        "carry it. Filed descriptions include brands verbatim and never label them. It "
        "was not inserted automatically: the wording of a legal description is the "
        "operator's.",
        line_id=line.line_id,
        remedy=f"Add {brand!r} to the description if it is the goods' own mark.",
    )
