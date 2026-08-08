"""Assembling one complete declaration from everything the run produced.

The per-line rules live beside this — units, weights, quantities, packaging, origin. This
module is the shipment level: the parties, the totals, the consignment, and the values
that come from the declarant's profile because no document carries them.

It decides **what a value should be**. It does not know how any value is written: element
names, ordering, formatting, and the difference between omitting an element and emitting
an empty one all belong to the filing adapter. Review items raised here are keyed by
domain concept, never by an element path — an item naming an XML element has leaked the
filing contract upward.
"""

from __future__ import annotations

from decimal import Decimal

from deepclare.assembly.countries import coded_country, detect_in_party, trade_country
from deepclare.assembly.inputs import AssemblyInput, DeclarantProfile
from deepclare.assembly.lines import assemble_line
from deepclare.assembly.tables import ReferenceTables
from deepclare.assembly.trace import Review, derived, supplied, transform
from deepclare.assembly.transport import resolve_transport
from deepclare.assembly.weights import resolve_weights
from deepclare.domain import ReviewItem, Traced
from deepclare.domain.declaration import (
    Consignment,
    Declaration,
    FillerPerson,
    GoodsLocation,
    Organization,
    PostalAddress,
)

STAGE = "assembly"

DESTINATION_COUNTRY_CODE = "AM"
"""An import declaration into Armenia has exactly one destination, by definition of the
procedure being filed. It is a constant, not a detection."""


def assemble_declaration(
    submission: AssemblyInput, tables: ReferenceTables
) -> tuple[Declaration, tuple[ReviewItem, ...]]:
    """Everything the shipment files, plus the account of what needed a human."""
    review = Review()
    invoice = submission.invoice
    note = submission.consignment_note

    weights = resolve_weights(submission, tables, review)
    invoice_origin = getattr(invoice, "origin_country", None)
    single_line = len(submission.lines) == 1

    goods = []
    for position, draft in enumerate(submission.lines, start=1):
        item, _unit = assemble_line(
            draft,
            position,
            weights[draft.line.line_id],
            note,
            invoice_origin,
            single_line,
            tables,
            review,
        )
        goods.append(item)

    declaration = Declaration(
        origin_country_name=_origin_name(invoice_origin, tables, review),
        total_goods_number=derived(len(goods), "one goods item per invoice line", 1.0),
        total_package_number=_total_packages(goods, note, review),
        consignor=_consignor(submission, tables, review),
        importer=_importer(submission, tables, review),
        goods_location=_goods_location(submission.profile, review),
        consignment=_consignment(submission, tables, review),
        goods=tuple(goods),
        filler=_filler(submission.profile, review),
    )
    return declaration, review.items


# --- shipment-level values ------------------------------------------------------------


def _origin_name(
    origin: Traced[str] | None, tables: ReferenceTables, review: Review
) -> Traced[str] | None:
    """Box 16 carries a name with no code half, so it resolves on its own."""
    if origin is None:
        review.omitted("shipment origin country",
            "no document stated an overall country of origin",
            remedy="set it on the portal, or supply an invoice that states it",
        )
        return None

    match = _country_by_alias(origin.value, tables)
    if match is None or not match.name_hy:
        review.omitted("shipment origin country",
            f"'{origin.value}' does not resolve to a country with a filable name",
            remedy="set it on the portal",
        )
        return None

    return origin.with_transform(
        transform(
            "resolve-country-name",
            origin.value,
            match.name_hy,
            "the filed name is the customs classifier's own, not a translation",
        ),
        match.name_hy,
    )


def _country_by_alias(printed: str, tables: ReferenceTables):
    folded = printed.strip().upper()
    for entry in tables.countries:
        if entry.code == folded:
            return entry
        if any(alias.upper() == folded for alias in entry.aliases):
            return entry
        if entry.name_hy and entry.name_hy.upper() == folded:
            return entry
    return None


def _total_packages(goods, note, review: Review) -> Traced[Decimal] | None:
    counted = [item.package_quantity for item in goods if item.package_quantity]
    if counted:
        return derived(
            sum((c.value for c in counted), Decimal(0)),
            "sum of the per-line package counts",
            0.9,
        )

    note_count = getattr(note, "package_count", None) if note is not None else None
    if note_count is not None:
        return derived(
            Decimal(str(note_count.value)),
            "the consignment note's own package total, no line carrying one",
            0.5,
        )

    review.omitted("total packages",
        "no goods line and no consignment note stated a package count",
    )
    return None


def _consignor(
    submission: AssemblyInput, tables: ReferenceTables, review: Review
) -> Organization | None:
    """The foreign seller. Its country is detected from whatever text names it."""
    seller = getattr(submission.invoice, "seller", None)
    sender = (
        getattr(submission.consignment_note, "sender", None)
        if submission.consignment_note is not None
        else None
    )
    party = seller or sender
    if party is None:
        review.placeholder("foreign consignor",
            "neither the invoice nor the consignment note named a seller",
            remedy="fill the consignor on the portal",
        )
        return Organization()

    detected = detect_in_party(party, tables)
    address = None
    if detected is None:
        review.omitted("consignor country",
            "no country could be read from the seller's address or name",
            remedy="fill the consignor's country on the portal",
        )
    else:
        entry, evidence = detected
        country = coded_country(
            entry, f"detected in the consignor's own text: {evidence}", 0.7
        )
        if country is None:
            review.omitted("consignor country",
                f"'{entry.code}' has no filable classifier name, and the code cannot "
                f"be filed without it",
            )
        else:
            address = PostalAddress(country=country)

    return Organization(name=getattr(party, "name", None), address=address)


def _importer(
    submission: AssemblyInput, tables: ReferenceTables, review: Review
) -> Organization | None:
    """One company fills boxes 8, 9 and 14; the adapter fans it out into three blocks."""
    buyer = getattr(submission.invoice, "buyer", None)
    profile = submission.profile.importer

    name = getattr(buyer, "name", None)
    tax_code = getattr(buyer, "tax_code", None)
    if name is None and profile is not None and profile.name:
        name = supplied(profile.name, "declarant profile")
    if tax_code is None and profile is not None and profile.tax_code:
        tax_code = supplied(profile.tax_code, "declarant profile")

    if name is None:
        review.placeholder("importer",
            "no document named the importing company and no profile supplied one",
            remedy="fill the importer on the portal",
        )
        return Organization()

    home = tables.country_by_code.get(DESTINATION_COUNTRY_CODE)
    country = (
        coded_country(
            home,
            "an import declarant is Armenian by definition of the procedure filed",
            1.0,
        )
        if home is not None
        else None
    )
    return Organization(
        name=name,
        tax_code=tax_code,
        address=PostalAddress(
            country=country, street_house=getattr(buyer, "address", None)
        ),
    )


def _goods_location(profile: DeclarantProfile, review: Review) -> GoodsLocation | None:
    """Where the goods sit while clearing. No source document carries any of it."""
    location = profile.goods_location
    if location is None:
        review.omitted("goods location",
            "no declarant profile supplied one, and no document carries it",
            remedy="set the goods location on the portal",
        )
        return None

    if not location.confirmed:
        review.guess("goods location",
            f"defaulted to customs office {location.customs_office_code}, information "
            f"type {location.information_type_code}",
            remedy="confirm the office — clearing at the wrong one is a real-world error",
        )

    return GoodsLocation(
        information_type_code=supplied(
            location.information_type_code, "declarant profile"
        ),
        customs_office_code=supplied(location.customs_office_code, "declarant profile"),
        country_code=supplied(location.country_code, "declarant profile"),
        customs_zone_number=(
            supplied(location.customs_zone_number, "declarant profile")
            if location.customs_zone_number
            else None
        ),
    )


def _consignment(
    submission: AssemblyInput, tables: ReferenceTables, review: Review
) -> Consignment:
    note = submission.consignment_note
    invoice = submission.invoice
    block = resolve_transport(note, tables, review)
    home = tables.country_by_code.get(DESTINATION_COUNTRY_CODE)

    return Consignment(
        container_indicator=_container_indicator(note, tables, review),
        destination_country=(
            coded_country(
                home, "every import under this procedure arrives in Armenia", 1.0
            )
            if home is not None
            else None
        ),
        departure_transport=block,
        border_transport=block,
        currency_code=getattr(invoice, "currency", None),
        total_invoice_amount=_total_amount(submission, review),
        trade_country_code=_trade_country(submission, tables, review),
    )


def _container_indicator(note, tables: ReferenceTables, review: Review) -> Traced[bool]:
    if note is None:
        review.guess("container indicator",
            "no consignment note, so containerisation could not be read anywhere",
            remedy="confirm whether the goods travelled in a container",
        )
        return derived(
            False, "no consignment note to read a container keyword from", 0.3
        )

    printed = getattr(note, "goods_description", None)
    text = str(getattr(printed, "value", printed) or "")
    hit = tables.mentions_container(text) if hasattr(tables, "mentions_container") else any(
        word.upper() in text.upper() for word in tables.container_keywords
    )
    return derived(
        hit, "a container keyword in the consignment note's own goods text", 0.7
    )


def _total_amount(submission: AssemblyInput, review: Review) -> Traced[Decimal] | None:
    totals = [
        draft.line.total_price
        for draft in submission.lines
        if getattr(draft.line, "total_price", None) is not None
    ]
    if totals:
        return derived(
            sum((Decimal(str(t.value)) for t in totals), Decimal(0)),
            "sum of the per-line totals, which excludes any service row by construction",
            0.95,
        )

    printed = getattr(submission.invoice, "total_amount", None)
    if printed is not None:
        return printed

    review.omitted("total invoice amount",
        "no goods line carried a total and the invoice printed none",
    )
    return None


def _trade_country(
    submission: AssemblyInput, tables: ReferenceTables, review: Review
) -> Traced[str] | None:
    seller = getattr(submission.invoice, "seller", None)
    sender = (
        getattr(submission.consignment_note, "sender", None)
        if submission.consignment_note is not None
        else None
    )
    detected = trade_country(
        seller, sender, getattr(submission.invoice, "origin_country", None), tables
    )
    if detected is None:
        review.omitted("trade country",
            "no counterparty country could be detected from any party's text",
            remedy="fill the trade country on the portal",
        )
        return None

    entry, evidence = detected
    return derived(
        entry.code, f"detected from the commercial counterparty: {evidence}", 0.7
    )


def _filler(profile: DeclarantProfile, review: Review) -> FillerPerson | None:
    """The person completing the declaration. No document carries it."""
    filler = profile.filler
    if filler is None:
        review.omitted("filler",
            "no declarant profile supplied the person completing the declaration",
            remedy="the portal fills this from the logged-in session",
        )
        return None

    return FillerPerson(
        surname=supplied(filler.surname, "declarant profile"),
        given_name=supplied(filler.given_name, "declarant profile"),
    )
