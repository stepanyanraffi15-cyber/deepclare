"""The write direction: an internal declaration becomes the filed document.

Dossier 10 §3 M12. This module knows how a value is written and nothing about how it was
produced — no model, no stage, no tenancy, no reference data. It receives values that are
already correct and decides only their expression.

Three of its rules exist because breaking them broke real imports:

* **Absence is omission.** Never an empty element, never a self-closing one, never a
  placeholder in a typed leaf. Two organization-name leaves may carry `-` and nothing
  else may.
* **Code and name are atomic.** A name written without its code imports successfully and
  the value is simply gone afterwards, with no message — the contract's quietest failure.
* **Order is fixed even for optional siblings.** Children are appended in the contract's
  sequence and never conditionally reordered, which is why every block below reads as one
  straight list.

Everything this module cannot supply becomes a review item keyed by domain concept, so
the operator learns what to fill in on the portal rather than discovering a blank later.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

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
    TransportBlock,
)
from deepclare.domain.provenance import Traced
from deepclare.domain.review import ReviewItem, ReviewKind
from deepclare.filing import contract as c
from deepclare.filing.conformance import ConformanceResult, check
from deepclare.filing.document import Element, container, leaf, serialize
from deepclare.filing.values import (
    boolean_text,
    code_text,
    decimal_text,
    integer_text,
    truncated_text,
)


class FiledDocument(BaseModel):
    """What the adapter hands back: the document, its verdict, and what a human must do."""

    model_config = ConfigDict(frozen=True)

    xml: str
    tree: Element
    """The same document as elements, so a caller can inspect it without re-parsing."""

    review_items: tuple[ReviewItem, ...]
    """Only the items the contract itself forced — a truncation, an omission for want of
    a schema-valid value. Everything assembly already knew about arrives separately."""

    conformance: ConformanceResult


def write_declaration(declaration: Declaration) -> FiledDocument:
    """Write one declaration and say whether it may be filed."""
    review: list[ReviewItem] = []
    root = _root(declaration, review)
    xml = serialize(root)
    return FiledDocument(
        xml=xml,
        tree=root,
        review_items=tuple(review),
        conformance=check(root, xml),
    )


# --- shipment level -------------------------------------------------------------------


def _root(declaration: Declaration, review: list[ReviewItem]) -> Element:
    children: list[Element | None] = [
        leaf(c.CUSTOMS_PROCEDURE, c.PROCEDURE_IMPORT),
        leaf(c.CUSTOMS_MODE_CODE, c.MODE_CODE_HOME_USE),
        _origin_country_name(declaration, review),
        leaf(c.SPECIFICATION_NUMBER, c.SINGLE_SPECIFICATION),
        leaf(c.SPECIFICATION_LIST_NUMBER, c.SINGLE_SPECIFICATION),
        leaf(c.TOTAL_GOODS_NUMBER, integer_text(declaration.total_goods_number.value)),
        _total_packages(declaration, review),
        leaf(c.TOTAL_SHEET_NUMBER, c.SINGLE_SHEET),
        _consignor(declaration.consignor, review),
    ]
    children.extend(_importer_trio(declaration.importer, review))
    children.append(_goods_location(declaration.goods_location, review))
    children.extend(_goods_item(item, review) for item in declaration.goods)
    children.append(_consignment(declaration.consignment, review))
    children.append(_filler(declaration.filler, review))

    root = container(c.ROOT, children)
    if root is None:  # pragma: no cover - a declaration always has goods and constants
        raise ValueError("a declaration produced no elements at all")
    return root.model_copy(
        update={
            "attributes": (
                ("xmlns", c.NAMESPACE_URI),
                ("DocumentModeID", c.DOCUMENT_MODE_ID),
            )
        }
    )


def _origin_country_name(
    declaration: Declaration, review: list[ReviewItem]
) -> Element | None:
    """Box 16. The one country field with no code half, so nothing pairs with it."""
    if declaration.origin_country_name is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="shipment origin country",
                detail="No origin country was resolved, so box 16 was left out. Every "
                "accepted filing carries it; fill it on the portal.",
            )
        )
        return None
    return leaf(c.ORIGIN_COUNTRY_NAME_SHIPMENT, declaration.origin_country_name.value)


def _total_packages(declaration: Declaration, review: list[ReviewItem]) -> Element | None:
    if declaration.total_package_number is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="shipment package total",
                detail="No package total could be summed or borrowed, so box 6 was left "
                "out. The portal recomputes this field on import in any case.",
            )
        )
        return None
    return leaf(c.TOTAL_PACKAGE_NUMBER, decimal_text(declaration.total_package_number.value))


# --- parties --------------------------------------------------------------------------


def _organization_name(
    organization: Organization | None, concept: str, review: list[ReviewItem]
) -> Element | None:
    """The name leaf, falling back to the one placeholder the contract permits."""
    if organization is not None and organization.name is not None:
        written = organization.name.value.strip()
        if written:
            return leaf(c.ORGANIZATION_NAME, written)
    review.append(
        ReviewItem(
            kind=ReviewKind.PLACEHOLDER,
            concept=concept,
            detail=f"No name was read for this party, so `{c.ABSENT_ORGANIZATION_NAME}` "
            "was filed. This is a free-text leaf and one of only two elements in the "
            "document permitted to carry a placeholder.",
            remedy="The party's name on the invoice or the consignment note.",
        )
    )
    return leaf(c.ORGANIZATION_NAME, c.ABSENT_ORGANIZATION_NAME)


def _consignor(organization: Organization | None, review: list[ReviewItem]) -> Element | None:
    """Box 2 — the foreign seller or shipper. Free text with no tax code anywhere."""
    address = None
    if organization is not None and organization.address is not None:
        address = container(
            c.ADDRESS, _country_pair(organization.address.country, "consignor country", review)
        )
    elif organization is not None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="consignor country",
                detail="No trade country was detected from the seller or the consignment "
                "note, so the consignor address was left out entirely rather than "
                "written as an empty container.",
            )
        )
    name = _organization_name(organization, "consignor name", review)
    return container(c.CONSIGNOR, [name, address])


def _importer_trio(
    organization: Organization | None, review: list[ReviewItem]
) -> list[Element | None]:
    """Boxes 8, 9 and 14 — one company, three identical blocks.

    Dossier 03 §5.3 records that the portal discards all three wholesale and re-fills
    them from the state register via its own tax-code lookup, so their content is an
    import preview rather than filed data. They are written anyway: the deciding
    experiment — a tax code matching the authenticated account — was never run, and the
    corpus files them in every declaration.
    """
    if organization is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="importer",
                detail="The documents named no importer, so boxes 8, 9 and 14 were all "
                "left out. Fill the importer on the portal; it resolves the company "
                "from the tax code itself.",
            )
        )
        return [None, None, None]

    name = _organization_name(organization, "importer name", review)
    features = _tax_code(organization, review)
    address = _importer_address(organization, review)
    return [
        container(role, [name, features, address])
        for role in (c.CONSIGNEE, c.RESPONSIBLE_PERSON, c.DECLARANT)
    ]


def _tax_code(organization: Organization, review: list[ReviewItem]) -> Element | None:
    """The Armenian taxpayer number. Digits or nothing — never a bad value."""
    if organization.tax_code is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="importer tax code",
                detail="No tax code was read, so the wrapper was omitted. The portal "
                "reports this as a mandatory field on two boxes and resolves the "
                "company from it.",
                remedy="The importer's 8-digit ՀՎՀՀ.",
            )
        )
        return None
    digits = organization.tax_code.value.replace(" ", "")
    if not digits.isdigit():
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="importer tax code",
                detail=f"The tax code read as {organization.tax_code.value!r}, which is "
                "not all digits, so the wrapper was omitted rather than filed with a "
                "value the portal would reject.",
                remedy="The importer's 8-digit ՀՎՀՀ.",
            )
        )
        return None
    return container(c.ORGANIZATION_FEATURES, [leaf(c.TAX_CODE, code_text(digits))])


def _importer_address(organization: Organization, review: list[ReviewItem]) -> Element | None:
    """Country is constant — an import declarant into Armenia is Armenian by definition."""
    street = None
    if organization.address is not None and organization.address.street_house is not None:
        written, was_cut = truncated_text(organization.address.street_house.value, 50)
        if was_cut:
            review.append(
                ReviewItem(
                    kind=ReviewKind.GUESS,
                    concept="importer street address",
                    detail="The address ran past the 50-character cap and was truncated "
                    f"to {written!r}. One over-long leaf rejects the whole file's "
                    "format with no field named. The portal re-fills this address from "
                    "the account, so the filed value is only an import preview.",
                )
            )
        street = leaf(c.STREET_HOUSE, written)
    return container(
        c.ADDRESS,
        [
            leaf(c.COUNTRY_CODE, c.DOMESTIC_COUNTRY_CODE),
            leaf(c.COUNTRY_NAME, c.DOMESTIC_COUNTRY_NAME),
            street,
        ],
    )


def _country_pair(
    country: CodedValue | None, concept: str, review: list[ReviewItem]
) -> list[Element | None]:
    """A country's code and name, together or not at all."""
    if country is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept=concept,
                detail="No country resolved, so both the code and the name were left "
                "out. Writing the name alone imports successfully and loses the value.",
            )
        )
        return [None, None]
    return [
        leaf(c.COUNTRY_CODE, code_text(country.code.value)),
        leaf(c.COUNTRY_NAME, country.name.value),
    ]


# --- goods location -------------------------------------------------------------------


def _goods_location(
    location: GoodsLocation | None, review: list[ReviewItem]
) -> Element | None:
    """Box 30 — present in every accepted filing, and derivable from no document."""
    if location is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="goods location",
                detail="No declarant profile supplied a goods location, so box 30 was "
                "left out. It is a property of where this importer clears, not of the "
                "shipment, and every accepted filing carries it.",
                remedy="The importer's warehouse information type, customs office and "
                "customs zone.",
            )
        )
        return None
    zone = None
    if location.customs_zone_number is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="customs zone number",
                detail="The profile carries no customs zone, so that sub-block was left "
                "out of box 30.",
            )
        )
    else:
        zone = container(
            c.CUSTOMS_ZONE,
            [leaf(c.CUSTOMS_ZONE_NUMBER, code_text(location.customs_zone_number.value))],
        )
    return container(
        c.GOODS_LOCATION,
        [
            leaf(
                c.GOODS_LOCATION_INFORMATION_TYPE,
                code_text(location.information_type_code.value),
            ),
            leaf(c.GOODS_LOCATION_OFFICE_CODE, code_text(location.customs_office_code.value)),
            leaf(c.GOODS_LOCATION_COUNTRY_CODE, code_text(location.country_code.value)),
            zone,
        ],
    )


# --- goods items ----------------------------------------------------------------------


def _goods_item(item: GoodsItem, review: list[ReviewItem]) -> Element | None:
    """One goods block, children in the contract's order.

    The additional-sign slot sits between the commodity code and the origin country and
    is never written: it appears on 17% of filed goods items as a single Cyrillic letter
    and nothing records what triggers it.
    """
    children: list[Element | None] = [
        leaf(c.GOODS_NUMERIC, integer_text(item.item_number)),
        _description(item, review),
        _optional_decimal(c.GROSS_WEIGHT, item.gross_weight, "line gross weight", item, review),
        _optional_decimal(c.NET_WEIGHT, item.net_weight, "line net weight", item, review),
        _optional_decimal(c.INVOICED_COST, item.invoiced_cost, "line invoiced value", item, review),
        _commodity_code(item, review),
    ]
    children.extend(_origin_pair(item, review))
    children.append(_customs_cost_method(item, review))
    children.append(_preferences())
    children.append(_supplementary_quantity(item, review))
    children.append(_packaging(item, review))
    children.append(_goods_procedure())
    return container(c.GOODS_ITEM, children)


def _description(item: GoodsItem, review: list[ReviewItem]) -> Element | None:
    written = item.description.value.strip()
    if not written:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="line goods description",
                detail="The line reached the filing adapter with an empty description, "
                "so box 31 was left out. Every accepted filing carries one on every line.",
                line_id=item.line_id,
            )
        )
        return None
    return leaf(c.GOODS_DESCRIPTION, written)


def _optional_decimal(
    element_name: str,
    value: Traced[Decimal] | None,
    concept: str,
    item: GoodsItem,
    review: list[ReviewItem],
) -> Element | None:
    if value is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept=concept,
                detail="No value was resolved for this line, so the element was left out "
                "rather than filed as an empty or placeholder leaf.",
                line_id=item.line_id,
            )
        )
        return None
    return leaf(element_name, decimal_text(value.value))


def _commodity_code(item: GoodsItem, review: list[ReviewItem]) -> Element | None:
    """Box 33 — the eleven-digit filed code, or nothing and a stated reason."""
    if item.commodity_code is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="line commodity code",
                detail="Classification abstained on this line, so box 33 was left out. "
                "The portal validates this code against its own nomenclature, so a "
                "guessed value would be rejected by name rather than filed.",
                remedy="A commodity code chosen on the portal, or the material and use "
                "that would let classification decide.",
                line_id=item.line_id,
            )
        )
        return None
    return leaf(c.COMMODITY_CODE, code_text(item.commodity_code.value))


def _origin_pair(item: GoodsItem, review: list[ReviewItem]) -> list[Element | None]:
    """Box 34 — code and name together, or the value is silently dropped on import."""
    if item.origin_country is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="line origin country",
                detail="Neither the line nor the invoice stated an origin, so both the "
                "code and the name were left out.",
                line_id=item.line_id,
            )
        )
        return [None, None]
    return [
        leaf(c.ORIGIN_COUNTRY_CODE, code_text(item.origin_country.code.value)),
        leaf(c.ORIGIN_COUNTRY_NAME, item.origin_country.name.value),
    ]


def _customs_cost_method(item: GoodsItem, review: list[ReviewItem]) -> Element | None:
    """Box 43. Transaction value where a price exists, the reserve method otherwise."""
    if item.customs_cost_method is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="line customs-value method",
                detail="No customs-value method reached the adapter, so box 43 was left "
                "out. Assembly populates it on every line, so this is a gap upstream.",
                line_id=item.line_id,
            )
        )
        return None
    return leaf(c.CUSTOMS_COST_METHOD, code_text(item.customs_cost_method.value))


def _preferences() -> Element | None:
    """Box 36 — the no-privilege marker, three times, and never anything else.

    A duty preference is derivable: every preferential line in the corpus is
    Iranian-origin under the EAEU–Iran agreement. It is deliberately never derived.
    Claiming one the goods do not qualify for under-declares duty, which is legally
    consequential; this marker merely over-declares and is corrected on the portal.
    """
    return container(
        c.PREFERENCES,
        [
            leaf(c.PREFERENCE_TAX, c.NO_PREFERENCE),
            leaf(c.PREFERENCE_DUTY, c.NO_PREFERENCE),
            leaf(c.PREFERENCE_RATE, c.NO_PREFERENCE),
        ],
    )


def _supplementary_quantity(item: GoodsItem, review: list[ReviewItem]) -> Element | None:
    """Box 41 — a figure, its unit name and its zero-padded unit code.

    A line without this block hangs the portal's import at 100% with no message at all.
    The fallback that keeps it populated is a cross-field rule and belongs to assembly,
    which knows the resolved unit and can grade the fallback; this module refuses to
    invent a figure it could not grade, and instead fails conformance on the line.
    """
    if item.supplementary_quantity is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.NEEDS_REVIEW,
                concept="line supplementary quantity",
                detail="This line carries no quantity in any unit and no weight to fall "
                "back on, so box 41 is absent. A goods line without it hangs the "
                "portal's import at 100% with no message — supply a quantity before "
                "importing this file.",
                remedy="Any genuine figure for the line, with the unit it is expressed in.",
                line_id=item.line_id,
            )
        )
        return None
    quantity = item.supplementary_quantity
    return container(
        c.SUPPLEMENTARY_QUANTITY,
        [
            leaf(c.GOODS_QUANTITY, decimal_text(quantity.quantity.value)),
            leaf(c.MEASURE_UNIT_NAME, quantity.unit_name.value),
            leaf(c.MEASURE_UNIT_CODE, code_text(quantity.unit_code.value)),
        ],
    )


def _packaging(item: GoodsItem, review: list[ReviewItem]) -> Element | None:
    """Always emitted, so the 0/1/2 classifier is always in front of the user.

    Quantity before type, unconditionally. Both children are optional and the sequence is
    still enforced: the reversed order is the one ordering violation confirmed fatal by an
    observed rejection, and the message named no element.
    """
    packaging = item.packaging
    count = None
    if packaging.package_count is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="line package count",
                detail="No package count was resolved for this line, so it was left out.",
                line_id=item.line_id,
            )
        )
    else:
        count = leaf(c.PACKAGE_QUANTITY, decimal_text(packaging.package_count.value))

    type_code = None
    if packaging.package_type_code is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="line packaging classifier",
                detail="No 0/1/2 packaging classifier reached the adapter, so it was left "
                "out. Assembly defaults it to packaged on every line, so this is a gap "
                "upstream.",
                line_id=item.line_id,
            )
        )
    else:
        type_code = leaf(c.PACKAGE_TYPE_CODE, code_text(packaging.package_type_code.value))

    packing = None
    if packaging.packing_code is not None:
        packing = container(
            c.PACKING_INFORMATION,
            [
                leaf(c.PACKING_CODE, code_text(packaging.packing_code.value)),
                leaf(c.PACKING_QUANTITY, decimal_text(packaging.packing_quantity.value))
                if packaging.packing_quantity is not None
                else None,
            ],
        )

    return container(c.GOODS_PACKAGING, [count, type_code, packing])


def _goods_procedure() -> Element | None:
    """Boxes 37 and 1 — three zero-padded fixed-width tokens whose widths are contract."""
    return container(
        c.GOODS_PROCEDURE,
        [
            leaf(c.MAIN_MODE_CODE, c.MODE_CODE_HOME_USE),
            leaf(c.PRECEDING_MODE_CODE, c.PRECEDING_MODE_NONE),
            leaf(c.GOODS_TRANSFER_FEATURE, c.TRANSFER_FEATURE_NONE),
        ],
    )


# --- consignment ----------------------------------------------------------------------


def _consignment(consignment: Consignment, review: list[ReviewItem]) -> Element | None:
    indicator = None
    if consignment.container_indicator is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="container indicator",
                detail="No container indicator reached the adapter, so box 19 was left "
                "out. Assembly defaults it to false when there is no consignment note.",
            )
        )
    else:
        indicator = leaf(
            c.CONTAINER_INDICATOR, boolean_text(consignment.container_indicator.value)
        )
    children: list[Element | None] = [indicator]
    children.extend(
        _named_country_pair(
            consignment.dispatch_country,
            c.DISPATCH_COUNTRY_CODE,
            c.DISPATCH_COUNTRY_NAME,
            "dispatch country",
            review,
        )
    )
    children.append(leaf(c.DESTINATION_COUNTRY_CODE, c.DOMESTIC_COUNTRY_CODE))
    children.append(leaf(c.DESTINATION_COUNTRY_NAME, c.DOMESTIC_COUNTRY_NAME))
    children.append(_border_office(consignment.border_office, review))
    children.append(
        _transport(c.DEPARTURE_TRANSPORT, consignment.departure_transport, "arrival transport", review)
    )
    children.append(
        _transport(c.BORDER_TRANSPORT, consignment.border_transport, "border transport", review)
    )
    children.append(_contract_terms(consignment, review))
    return container(c.CONSIGNMENT, children)


def _named_country_pair(
    country: CodedValue | None,
    code_element: str,
    name_element: str,
    concept: str,
    review: list[ReviewItem],
) -> list[Element | None]:
    if country is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept=concept,
                detail="No country resolved, so the code and the name were both left out.",
            )
        )
        return [None, None]
    return [
        leaf(code_element, code_text(country.code.value)),
        leaf(name_element, country.name.value),
    ]


def _border_office(office: BorderOffice | None, review: list[ReviewItem]) -> Element | None:
    """Box 12. The code is required once the block exists, so an unmapped route omits all
    of it rather than filing a block the schema cannot accept."""
    if office is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="border crossing office",
                detail="The dispatch country mapped to no crossing office, so the whole "
                "block was left out. Its code leaf is required once the block exists.",
            )
        )
        return None
    return container(
        c.BORDER_OFFICE,
        [
            leaf(c.BORDER_OFFICE_CODE, code_text(office.code.value)),
            leaf(c.BORDER_OFFICE_NAME, office.name.value) if office.name else None,
            leaf(c.BORDER_OFFICE_COUNTRY_CODE, code_text(office.country_code.value))
            if office.country_code
            else None,
        ],
    )


def _transport(
    element_name: str,
    block: TransportBlock | None,
    concept: str,
    review: list[ReviewItem],
) -> Element | None:
    """One transport block. Departure/arrival and border carry identical content.

    A plate-less run writes no transport-means element at all: a meaningless placeholder
    identifier is worse than absence, because it would file a vehicle that does not exist.
    """
    if block is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept=concept,
                detail="No transport was resolved, so the block was left out.",
            )
        )
        return None
    if not block.vehicles:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept=f"{concept} vehicles",
                detail="No vehicle plate was read, so no transport-means element was "
                "written. A placeholder identifier would file a vehicle that does not "
                "exist.",
                remedy="The plates from box 25 of the consignment note.",
            )
        )
    children: list[Element | None] = [
        leaf(c.TRANSPORT_MODE_CODE, code_text(block.mode_code.value)),
        leaf(c.TRANSPORT_MEANS_QUANTITY, integer_text(block.vehicle_quantity.value))
        if block.vehicle_quantity is not None
        else None,
    ]
    children.extend(
        container(
            c.TRANSPORT_MEANS,
            [
                leaf(c.TRANSPORT_IDENTIFIER, vehicle.identifier.value),
                leaf(c.TRANSPORT_NATIONALITY_CODE, code_text(vehicle.nationality_country_code.value))
                if vehicle.nationality_country_code is not None
                else None,
            ],
        )
        for vehicle in block.vehicles
    )
    return container(element_name, children)


def _contract_terms(consignment: Consignment, review: list[ReviewItem]) -> Element | None:
    """Currency, total, trade country and Incoterms.

    The currency rate is never written. The invoice rarely carries one and the portal
    fills it, so filing a guessed rate would put a wrong exchange rate on a legal document
    to save a field the portal supplies anyway.
    """
    currency = None
    if consignment.currency_code is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="contract currency",
                detail="The invoice stated no currency, so the element was left out.",
            )
        )
    else:
        currency = leaf(c.CONTRACT_CURRENCY_CODE, code_text(consignment.currency_code.value))

    total = None
    if consignment.total_invoice_amount is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="total invoice amount",
                detail="No line totals summed and the invoice printed no goods total, so "
                "box 22 was left out.",
            )
        )
    else:
        total = leaf(c.TOTAL_INVOICE_AMOUNT, decimal_text(consignment.total_invoice_amount.value))

    trade_country = None
    if consignment.trade_country_code is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="trade country",
                detail="Trade-country detection found nothing in the seller's address or "
                "name, so box 11 was left out.",
            )
        )
    else:
        trade_country = leaf(c.TRADE_COUNTRY_CODE, code_text(consignment.trade_country_code.value))

    return container(
        c.CONTRACT_TERMS,
        [currency, total, trade_country, _delivery_terms(consignment.delivery_terms, review)],
    )


def _delivery_terms(terms: DeliveryTerms | None, review: list[ReviewItem]) -> Element | None:
    """Box 20. Each half is omitted on its own — this is not a code+name pair."""
    if terms is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="delivery terms",
                detail="The invoice stated no Incoterms, so the block was left out "
                "entirely rather than written as an empty container.",
            )
        )
        return None
    code_leaf = None
    if terms.terms_code is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="delivery terms code",
                detail="No Incoterms code was read, so that leaf was left out.",
            )
        )
    else:
        code_leaf = leaf(c.DELIVERY_TERMS_CODE, terms.terms_code.value)

    place_leaf = None
    if terms.place is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="delivery place",
                detail="No Incoterms place was read, so that leaf was left out.",
            )
        )
    else:
        place_leaf = leaf(c.DELIVERY_PLACE, terms.place.value)

    return container(c.DELIVERY_TERMS, [code_leaf, place_leaf])


# --- filler ---------------------------------------------------------------------------


def _filler(filler: FillerPerson | None, review: list[ReviewItem]) -> Element | None:
    """Box 54. No profile means no block — a placeholder name is semantically empty and
    risks the surname's own string facet, and the portal fills the filler from the session."""
    if filler is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="filler person",
                detail="No declarant profile supplied a filler, so box 54 was left out. "
                "The portal fills it from the logged-in session.",
            )
        )
        return None
    contact = container(
        c.FILLER_CONTACT,
        [
            leaf(c.FILLER_PHONE, filler.phone.value) if filler.phone is not None else None,
            leaf(c.FILLER_EMAIL, filler.email.value) if filler.email is not None else None,
        ],
    )
    return container(
        c.FILLER,
        [
            leaf(c.FILLER_SURNAME, filler.surname.value),
            leaf(c.FILLER_GIVEN_NAME, filler.given_name.value),
            contact,
        ],
    )
