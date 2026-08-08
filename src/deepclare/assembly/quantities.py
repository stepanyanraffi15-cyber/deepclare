"""Dossier 03 §4.3 — piece and package arithmetic.

Two figures come out of here and they are computed together on purpose: the resolved
package count, and the total item count. Box 41's pieces figure and box 31's quantity text
are written from the *same* package count, so the number in the figure and the number in
the sentence can never contradict each other.

Three rules decide everything:

* **Only factors printed on the same invoice line multiply.** A consignment note's package
  count is routinely a pallet count — a different packaging level from the invoice's
  cartons — and multiplying across levels fabricates a total.
* **The undecidable shape files nothing.** An unlabelled quantity column, a printed
  per-package factor, and a package count that disagrees with the quantity: the quantity
  might be packages or it might be items, either multiplication risks a wrong figure, and
  wrong arithmetic on a legal document is worse than an absent figure.
* **The arithmetic is exact.** Everything is `Decimal` end to end. No float artefact may
  reach the filed document, and the recorded case is a spreadsheet cell that read
  50.400000000000006.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from deepclare.assembly.inputs import LineDraft
from deepclare.assembly.tables import ReferenceTables
from deepclare.assembly.trace import COMPUTED, Review, derived
from deepclare.domain import ConsignmentNote, InvoiceGoodsLine, Traced

INTEGER_TOLERANCE = Decimal("0.000001")
"""How far from a whole number a division may land and still be trusted. Dossier 03 §4.3
sets it; only a clean division is real declarant arithmetic."""


class PackageCountSource(BaseModel):
    """Where a package count came from, so the wording of its review item can say so."""

    model_config = ConfigDict(frozen=True)

    rule: str
    is_guess: bool
    detail: str | None = None


class LineQuantities(BaseModel):
    """One line's resolved packaging and piece arithmetic."""

    model_config = ConfigDict(frozen=True)

    line_id: str

    package_count: Traced[Decimal] | None = None
    """Box 6 per line, and the multiplier the piece total and the box 31 text share."""

    packing_code: Traced[str] | None = None

    units_per_package: Decimal | None = None
    """Only ever the invoice's own printed per-package factor. Never derived."""

    total_items: Traced[Decimal] | None = None
    """The total number of discrete items on the line, when it is decidable."""

    total_is_pack_math: bool = False
    """Whether the total came from packages x per-package, which is what box 31 writes
    out in full rather than as a bare count."""


def resolve_quantities(
    draft: LineDraft,
    note: ConsignmentNote | None,
    single_line_shipment: bool,
    tables: ReferenceTables,
    review: Review,
) -> LineQuantities:
    """Everything §4.3 decides for one line."""
    line = draft.line
    package_count, source = _package_count(line, note, single_line_shipment, tables)
    if package_count is not None and source is not None and source.is_guess:
        review.guess(
            "line package count",
            source.detail or "The package count was derived rather than printed.",
            line_id=line.line_id,
            remedy="The number of packages printed on the invoice for this line.",
        )
    elif package_count is None:
        review.omitted(
            "line package count",
            "Neither the invoice nor the consignment note gives a package count this "
            "line can use, so none was filed.",
            line_id=line.line_id,
            remedy="The number of packages for this line.",
        )

    packing_code = _packing_code(line, note, tables, review)
    units_per_package = (
        line.units_per_package.value if line.units_per_package is not None else None
    )

    total, is_pack_math = _total_items(
        line, package_count, units_per_package, tables, review
    )
    return LineQuantities(
        line_id=line.line_id,
        package_count=package_count,
        packing_code=packing_code,
        units_per_package=units_per_package,
        total_items=total,
        total_is_pack_math=is_pack_math,
    )


# --- the package count ------------------------------------------------------------------


def _package_count(
    line: InvoiceGoodsLine,
    note: ConsignmentNote | None,
    single_line_shipment: bool,
    tables: ReferenceTables,
) -> tuple[Traced[Decimal] | None, PackageCountSource | None]:
    """The four rungs of §4.3's package-count ladder, in order."""
    if line.package_count is not None:
        return line.package_count, PackageCountSource(
            rule="invoice line package count", is_guess=False
        )

    if line.quantity is not None and _quantity_counts_packages(line, tables):
        label = line.unit.value if line.unit is not None else None
        return line.quantity, PackageCountSource(
            rule=f"invoice quantity column labelled {label!r}"
            if label
            else "unlabelled invoice quantity column read as packages",
            is_guess=False,
        )

    if note is not None and note.package_count is not None and single_line_shipment:
        return note.package_count, PackageCountSource(
            rule="consignment-note total, single-line shipment",
            is_guess=True,
            detail=f"The invoice gives no package count, so the consignment note's total "
            f"of {note.package_count.value} was used. This is only sound because the "
            "shipment has one line: a note's count is shipment-level and routinely counts "
            "pallets rather than the invoice's cartons.",
        )

    derived_count = _packages_from_pack_size(line, tables)
    if derived_count is not None:
        count, kilograms, per_package = derived_count
        return count, PackageCountSource(
            rule="kilograms divided by printed per-package weight",
            is_guess=True,
            detail=f"The invoice prints {per_package} kg per package and {kilograms} kg "
            f"on the line, so {count.value} packages. Only a division that comes out "
            "whole is trusted, and this one does.",
        )

    return None, None


def _quantity_counts_packages(line: InvoiceGoodsLine, tables: ReferenceTables) -> bool:
    """Whether this line's quantity column is counting packages rather than items.

    Two shapes count: a unit word that names a package — cartons, bags, pallets — and an
    unlabelled column on a line that prints a per-package factor, which is the shape real
    declarants multiply (12 of 13 golden retail lines).
    """
    label = line.unit.value if line.unit is not None else None
    if tables.counts_packages(label):
        return True
    unlabelled = label is None or not label.strip()
    return unlabelled and line.units_per_package is not None


def _packages_from_pack_size(
    line: InvoiceGoodsLine, tables: ReferenceTables
) -> tuple[Traced[Decimal], Decimal, Decimal] | None:
    """Packages as kilograms divided by the printed weight of one package.

    Real declarant arithmetic: 3000 kg of a printed 25 kg bag is 120 bags. Trusted only
    when the division is exact, and only against a weight the invoice itself printed —
    dividing a distributed weight would compound one guess into another.
    """
    if line.package_weight_kg is None or line.package_weight_kg.value <= 0:
        return None
    kilograms = _printed_kilograms(line, tables)
    if kilograms is None or kilograms <= 0:
        return None

    packages = kilograms / line.package_weight_kg.value
    whole = packages.to_integral_value()
    if abs(packages - whole) > INTEGER_TOLERANCE:
        return None
    return (
        derived(
            whole,
            "packages from kilograms divided by the printed per-package weight",
            COMPUTED,
        ),
        kilograms,
        line.package_weight_kg.value,
    )


def _printed_kilograms(line: InvoiceGoodsLine, tables: ReferenceTables) -> Decimal | None:
    """A kilogram magnitude the invoice itself printed for this line."""
    if line.quantity is not None and line.unit is not None:
        if tables.resolve_unit(line.unit.value) == tables.kilogram_code:
            return line.quantity.value
    for weight in (line.net_weight, line.gross_weight):
        if weight is not None:
            unit = line.weight_unit.value if line.weight_unit is not None else None
            if unit is None or tables.resolve_unit(unit) == tables.kilogram_code:
                return weight.value
    return None


# --- packing code -----------------------------------------------------------------------


def _packing_code(
    line: InvoiceGoodsLine,
    note: ConsignmentNote | None,
    tables: ReferenceTables,
    review: Review,
) -> Traced[str] | None:
    """The UN/ECE code for how the goods are packed, from whatever text names it.

    Dossier 03 §4.3 records the asymmetry as found: package *type* is borrowed from the
    consignment note without the single-line condition the *count* carries. The invoice
    still wins where it states one — it is the authoritative document everywhere else.
    """
    printed = line.package_type or (note.package_type if note is not None else None)
    if printed is None:
        return None
    code = tables.packing_code(printed.value)
    if code is None:
        review.omitted(
            "line packing type",
            f"The packing is described as {printed.value!r}, which resolves to none of "
            "the eight packing kinds this product can infer, so no packing code was "
            "filed. Eight kinds can be inferred from text; hundreds can be chosen on the "
            "portal.",
            line_id=line.line_id,
            remedy="The UN/ECE packing code for this packaging.",
        )
        return None
    review.guess(
        "line packing type",
        f"{printed.value!r} was read as packing code {code}.",
        line_id=line.line_id,
    )
    return derived(code, f"packing text {printed.value!r} mapped to a UN/ECE code", COMPUTED)


# --- the total item count ---------------------------------------------------------------


def _total_items(
    line: InvoiceGoodsLine,
    package_count: Traced[Decimal] | None,
    units_per_package: Decimal | None,
    tables: ReferenceTables,
    review: Review,
) -> tuple[Traced[Decimal] | None, bool]:
    """How many discrete items the line holds, or nothing and a stated reason."""
    quantity = line.quantity.value if line.quantity is not None else None
    unit = tables.resolve_unit(line.unit.value) if line.unit is not None else None

    if unit == tables.pieces_code and quantity is not None:
        _check_pack_math_reconciles(line, quantity, package_count, units_per_package, review)
        return line.quantity, False

    if unit is not None and tables.counts_in_its_own_unit(unit):
        # The line is counted in pairs or in thousands, and a per-package factor on such
        # a line counts the same thing. Multiplying gives more pairs, not pieces, and
        # filing that as a piece total would contradict box 41's own figure.
        return None, False

    if units_per_package is None:
        return None, False

    if _is_undecidable(line, package_count, tables):
        review.needs_review(
            "line total item count",
            f"The invoice prints {units_per_package} items per package and a package "
            f"count that does not agree with the quantity column, and the column carries "
            "no unit. The quantity may be counting packages or items and the two "
            "multiplications give different answers, so no piece total was filed at all.",
            line_id=line.line_id,
            remedy="What the quantity column counts, or a printed total item count.",
        )
        return None, False

    if package_count is None:
        return None, False

    total = package_count.value * units_per_package
    review.guess(
        "line total item count",
        f"{package_count.value} packages of {units_per_package} gives {total} items. "
        "Both factors are printed on this invoice line; the multiplication is this "
        "product's.",
        line_id=line.line_id,
    )
    return (
        derived(
            total,
            "package count multiplied by the printed per-package item count",
            COMPUTED,
        ),
        True,
    )


def _is_undecidable(
    line: InvoiceGoodsLine, package_count: Traced[Decimal] | None, tables: ReferenceTables
) -> bool:
    """The shape §4.3 refuses to guess at.

    A printed package count that disagrees with the quantity column means the two columns
    are counting different things, and nothing on the line says which is which.
    """
    if line.package_count is None or line.quantity is None:
        return False
    if package_count is None:
        return False
    label = line.unit.value if line.unit is not None else None
    quantity_might_be_packages = tables.counts_packages(label) or not (label or "").strip()
    return quantity_might_be_packages and line.package_count.value != line.quantity.value


def _check_pack_math_reconciles(
    line: InvoiceGoodsLine,
    quantity: Decimal,
    package_count: Traced[Decimal] | None,
    units_per_package: Decimal | None,
    review: Review,
) -> None:
    """A printed piece total against a printed multiplication that disagrees with it.

    Dossier 03 §4.3: the total is filed alone and the disagreement is flagged. The printed
    total is the invoice's own statement; the multiplication is an inference about it.
    """
    if package_count is None or units_per_package is None:
        return
    product = package_count.value * units_per_package
    if product == quantity:
        return
    review.needs_review(
        "line total item count",
        f"The invoice states {quantity} pieces, and {package_count.value} packages of "
        f"{units_per_package} would be {product}. The stated total was filed and the "
        "multiplication was not; the two do not reconcile and one of the three printed "
        "figures is wrong.",
        line_id=line.line_id,
        remedy="Which of the quantity, the package count and the per-package factor the "
        "invoice actually means.",
    )
