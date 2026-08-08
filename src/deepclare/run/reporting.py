"""The declaration, presented to the review surface as values keyed by domain concept.

M13 is handed two streams: the review items every module raised, and the values those
modules produced. This module produces the second stream, and it does exactly one thing —
it names each value's domain concept and hands the value over with the account its
producer already attached. Nothing here computes, rounds, re-checks or fills anything: a
review surface that can disagree with the declaration is a second implementation of the
declaration.

The concept names are the ones assembly and the filing adapter already raise their items
under, because the report joins an item to its value on `(concept, line)`. A value named
differently from the item about it is not wrong — it still appears in the line's
provenance table — but the operator then reads the finding and the value in two places
instead of one.

An element name never appears here. That is the whole point of concept keying: it holds
before anything has decided how a value is written, which is what lets the join exist at
all.
"""

from __future__ import annotations

from deepclare.domain import Declaration, GoodsItem, Organization, Traced
from deepclare.review.values import ReportedValue, reported


def reported_values(declaration: Declaration) -> tuple[ReportedValue, ...]:
    """Every value of one declaration a reviewer might have to check."""
    values: list[ReportedValue] = []
    _shipment(declaration, values)
    for item in declaration.goods:
        _line(item, values)
    return tuple(values)


def _shipment(declaration: Declaration, into: list[ReportedValue]) -> None:
    _add(into, "shipment origin country", declaration.origin_country_name)
    _add(into, "total goods number", declaration.total_goods_number)
    _add(into, "total packages", declaration.total_package_number)

    _party(into, "consignor", declaration.consignor)
    _party(into, "importer", declaration.importer)

    location = declaration.goods_location
    if location is not None:
        _add(into, "goods location", location.customs_office_code)
        _add(into, "customs zone number", location.customs_zone_number)

    consignment = declaration.consignment
    _add(into, "container indicator", consignment.container_indicator)
    _add(into, "contract currency", consignment.currency_code)
    _add(into, "total invoice amount", consignment.total_invoice_amount)
    _add(into, "trade country", consignment.trade_country_code)
    if consignment.dispatch_country is not None:
        _add(into, "dispatch country", consignment.dispatch_country.code)
    if consignment.departure_transport is not None:
        _add(into, "transport mode", consignment.departure_transport.mode_code)
        for position, vehicle in enumerate(
            consignment.departure_transport.vehicles, start=1
        ):
            _add(into, f"transport vehicle {position}", vehicle.identifier)
    if consignment.border_office is not None:
        _add(into, "border crossing office", consignment.border_office.code)
    if consignment.delivery_terms is not None:
        _add(into, "delivery terms code", consignment.delivery_terms.terms_code)
        _add(into, "delivery place", consignment.delivery_terms.place)

    if declaration.filler is not None:
        _add(into, "filler", declaration.filler.surname)


def _party(into: list[ReportedValue], role: str, party: Organization | None) -> None:
    if party is None:
        return
    _add(into, f"{role} name", party.name)
    _add(into, f"{role} tax code", party.tax_code)
    if party.address is None:
        return
    _add(into, f"{role} street address", party.address.street_house)
    if party.address.country is not None:
        _add(into, f"{role} country", party.address.country.code)


def _line(item: GoodsItem, into: list[ReportedValue]) -> None:
    line = item.line_id
    _add(into, "line goods description", item.description, line)
    _add(into, "line commodity code", item.commodity_code, line)
    _add(into, "line gross weight", item.gross_weight, line)
    _add(into, "line net weight", item.net_weight, line)
    _add(into, "line invoiced value", item.invoiced_cost, line)
    _add(into, "line customs-value method", item.customs_cost_method, line)
    if item.origin_country is not None:
        _add(into, "line origin country", item.origin_country.code, line)
    if item.supplementary_quantity is not None:
        _add(into, "line supplementary quantity", item.supplementary_quantity.quantity, line)
        _add(into, "line supplementary unit", item.supplementary_quantity.unit_code, line)
    _add(into, "line package count", item.packaging.package_count, line)
    _add(into, "line packing type", item.packaging.packing_code, line)
    _add(into, "line packaging classifier", item.packaging.package_type_code, line)


def _add(
    into: list[ReportedValue],
    concept: str,
    traced: Traced | None,
    line_id: str | None = None,
) -> None:
    """Report a value, or report nothing.

    An absent value is not reported as an empty one. Whatever left it out already said so
    as a review item, and a blank row in the provenance table would read as a value that
    was produced and came out empty.
    """
    if traced is not None:
        into.append(reported(concept, traced, line_id))
