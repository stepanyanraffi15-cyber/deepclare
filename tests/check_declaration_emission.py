"""Emit a complete declaration from a hand-built internal object and print it.

Run:  .venv/bin/python tests/check_declaration_emission.py

Nothing here touches the network, a model or a dataset. It exists to be read against
dossier 03 §5 and §6 by eye — the goods-block child order, the prolog, the indentation,
the constants, the two permitted placeholders and the absence rule — and then to be run
back through the reader so the two directions can be compared on one document.

The values are invented for this demonstration. They are not a sample declaration and
they are not derived from anyone's filing.
"""

from __future__ import annotations

from decimal import Decimal

from deepclare.domain.declaration import (
    BorderOffice,
    CodedValue,
    Consignment,
    Declaration,
    DeliveryTerms,
    FillerPerson,
    GoodsItem,
    GoodsLocation,
    Organization,
    Packaging,
    PostalAddress,
    SupplementaryQuantity,
    TransportBlock,
    TransportMeansRecord,
)
from deepclare.domain.provenance import Provenance, Traced, ValueOrigin
from deepclare.filing import read_declaration, write_declaration

_EXTRACTED = Provenance(origin=ValueOrigin.EXTRACTED, source_document_id="invoice-1")
_SUPPLIED = Provenance(origin=ValueOrigin.SUPPLIED, supplied_by="declarant profile")
_DERIVED = Provenance(origin=ValueOrigin.DERIVED, rule="demonstration fixture")


def read(value: object) -> Traced:
    return Traced(value=value, provenance=_EXTRACTED)


def profile(value: object) -> Traced:
    return Traced(value=value, provenance=_SUPPLIED)


def derived(value: object) -> Traced:
    return Traced(value=value, provenance=_DERIVED)


def country(code: str, name: str) -> CodedValue:
    return CodedValue(code=read(code), name=read(name))


def build_declaration() -> Declaration:
    """Two goods lines: one complete, one where classification abstained."""
    complete_line = GoodsItem(
        item_number=1,
        line_id="1",
        description=read("ՊՈԼԻԷԹԻԼԵՆԱՅԻՆ ՊԱՐԿԵՐ, 40*60 ՍՄ, 12 ՏՈՒՓ 500 ՀԱՏԱՆՈՑ-6000 ՀԱՏ"),
        gross_weight=read(Decimal("1250.50")),
        net_weight=read(Decimal("1200")),
        invoiced_cost=read(Decimal("3400.00")),
        commodity_code=derived("39232900000"),
        origin_country=country("IR", "ԻՐԱՆ"),
        customs_cost_method=derived("1"),
        supplementary_quantity=SupplementaryQuantity(
            quantity=derived(Decimal("6000")),
            unit_code=derived("796"),
            unit_name=derived("ՀԱՏ"),
        ),
        packaging=Packaging(
            package_count=read(Decimal("12")),
            package_type_code=profile("1"),
            packing_code=derived("BX"),
            packing_quantity=derived(Decimal("12")),
        ),
    )
    abstained_line = GoodsItem(
        item_number=2,
        line_id="2",
        description=read("ՄԵՏԱՂԱԿԱՆ ԱՄՐԱԿՆԵՐ"),
        gross_weight=read(Decimal("80")),
        net_weight=derived(Decimal("72")),
        invoiced_cost=read(Decimal("220.5")),
        commodity_code=None,
        origin_country=None,
        customs_cost_method=derived("1"),
        supplementary_quantity=SupplementaryQuantity(
            quantity=derived(Decimal("72")),
            unit_code=derived("166"),
            unit_name=derived("ԿԳ"),
        ),
        packaging=Packaging(package_type_code=profile("1")),
    )

    return Declaration(
        origin_country_name=read("ԻՐԱՆ"),
        total_goods_number=derived(2),
        total_package_number=derived(Decimal("12")),
        consignor=Organization(
            name=read("PARS PLASTIC CO"),
            address=PostalAddress(country=country("IR", "ԻՐԱՆ")),
        ),
        importer=Organization(
            name=read("ԱՐԱՐԱՏ ԻՄՊՈՐՏ ՍՊԸ"),
            tax_code=read("01234567"),
            address=PostalAddress(
                street_house=read(
                    "ԵՐԵՎԱՆ, ԿԵՆՏՐՈՆ ՎԱՐՉԱԿԱՆ ՇՐՋԱՆ, ԱԲՈՎՅԱՆ ՓՈՂՈՑ 128 ՇԵՆՔ, 4-ՐԴ ՀԱՐԿ, "
                    "ԳՐԱՍԵՆՅԱԿ 12"
                )
            ),
        ),
        goods_location=GoodsLocation(
            information_type_code=profile("11"),
            customs_office_code=profile("05100010"),
            country_code=profile("AM"),
            customs_zone_number=profile("PP00002"),
        ),
        consignment=Consignment(
            container_indicator=derived(False),
            dispatch_country=country("IR", "ԻՐԱՆ"),
            border_office=BorderOffice(
                code=derived("05100005"),
                name=derived("ՄԵՂՐԻ"),
                country_code=derived("AM"),
            ),
            departure_transport=TransportBlock(
                mode_code=derived("31"),
                vehicles=(
                    TransportMeansRecord(identifier=read("12AB345")),
                    TransportMeansRecord(identifier=read("77XY910")),
                ),
                vehicle_quantity=derived(2),
            ),
            border_transport=TransportBlock(
                mode_code=derived("31"),
                vehicles=(
                    TransportMeansRecord(identifier=read("12AB345")),
                    TransportMeansRecord(identifier=read("77XY910")),
                ),
                vehicle_quantity=derived(2),
            ),
            currency_code=read("USD"),
            total_invoice_amount=derived(Decimal("3620.50")),
            trade_country_code=derived("IR"),
            delivery_terms=DeliveryTerms(terms_code=read("FCA"), place=read("TABRIZ")),
        ),
        goods=(complete_line, abstained_line),
        filler=FillerPerson(
            surname=profile("ՊԵՏՐՈՍՅԱՆ"),
            given_name=profile("ԱՐԱ"),
            phone=profile("+37410000000"),
            email=profile("filler@example.am"),
        ),
    )


def main() -> None:
    document = write_declaration(build_declaration())

    print("=" * 78)
    print("EMITTED DOCUMENT")
    print("=" * 78)
    print(document.xml, end="")

    print()
    print("=" * 78)
    print("CONFORMANCE, PER RULE")
    print("=" * 78)
    print(document.conformance.report())
    print()
    print(f"conforms = {document.conformance.conforms}   "
          f"filable = {document.conformance.filable}")

    print()
    print("=" * 78)
    print(f"REVIEW ITEMS FORCED BY THE CONTRACT ({len(document.review_items)})")
    print("=" * 78)
    for item in document.review_items:
        line = "" if item.line_id is None else f" (line {item.line_id})"
        print(f"[{item.kind.value:>12}] {item.concept}{line}")
        print(f"               {item.detail}")

    parsed = read_declaration(document.xml, filing_id="round-trip")
    print()
    print("=" * 78)
    print("READ BACK")
    print("=" * 78)
    print(f"goods lines read      : {len(parsed.declaration.goods)}")
    print(f"codes read            : "
          f"{[g.commodity_code.value if g.commodity_code else None for g in parsed.declaration.goods]}")
    print(f"importer tax code     : {parsed.declaration.importer.tax_code.value}")
    print(f"consignor name        : {parsed.declaration.consignor.name.value}")
    print(f"plates                : "
          f"{[v.identifier.value for v in parsed.declaration.consignment.departure_transport.vehicles]}")
    print(f"unread elements       : {len(parsed.unread)}")
    for element in parsed.unread:
        print(f"  {element.path}: {element.reason}")
    print(f"distinct element names: {len(parsed.census)}")

    rewritten = write_declaration(parsed.declaration)
    print(f"re-emitted identically: {rewritten.xml == document.xml}")


if __name__ == "__main__":
    main()
