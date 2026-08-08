"""The write direction: an internal declaration becomes the filed document.

Dossier 10 §3 M12. This module knows how a value is written and nothing about how it was
produced — no model, no stage, no tenancy, no reference data. It receives values that are
already correct and decides only their expression.

Every element name, every namespace prefix and every child sequence used here comes from
`contract`, which takes them from `observed`, which is generated from the ground-truth
declarations. Nothing below names an element the corpus does not attest, and `_element`
and `_block` resolve each element's prefix from the same table rather than from anything
this module decides.

Four of its rules exist because breaking them broke real imports:

* **Absence is omission.** Never an empty element, never a self-closing one, never a
  placeholder in a typed leaf. The four party organization-name leaves may carry `-` and
  nothing else may.
* **Code and name are atomic.** A name written without its code imports successfully and
  the value is simply gone afterwards, with no message — the contract's quietest failure.
* **Order is fixed even for optional siblings.** Children are appended in the contract's
  sequence and never conditionally reordered, which is why every block below reads as one
  straight list.
* **A value the attested contract has nowhere to put is reported, not dropped.** The
  domain model carries vehicle plates, a crossing office, a delivery place, a customs
  zone and the filler's contact details; no filing in the evidence base carries an
  element for any of them. Writing an invented element would reject the file, so they
  become review items naming what could not be filed.

Everything this module cannot supply becomes a review item keyed by domain concept, so
the operator learns what to fill in on the portal rather than discovering a blank later.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from deepclare.domain.declaration import (
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
    a schema-valid value, a value the filed format has no element for. Everything
    assembly already knew about arrives separately."""

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


# --- element construction -------------------------------------------------------------


def _element(name: str, text: str | None) -> Element | None:
    """One leaf, under the prefix the evidence puts it in."""
    return leaf(name, text, prefix=c.prefix_for(name))


def _block(name: str, children: list[Element | None]) -> Element | None:
    """One container, under the prefix the evidence puts it in."""
    return container(name, children, prefix=c.prefix_for(name))


def _unfilable(concept: str, detail: str, review: list[ReviewItem]) -> None:
    """Record a value the attested contract has no element for."""
    review.append(ReviewItem(kind=ReviewKind.OMITTED, concept=concept, detail=detail))


# --- document -------------------------------------------------------------------------


def _root(declaration: Declaration, review: list[ReviewItem]) -> Element:
    """Procedure, mode, the whole shipment, and the person who filled it in.

    The shipment container wraps everything except the two header codes and the filler.
    Its absence was the single defect that made every earlier emitted file unimportable,
    and no leaf inside it moves without it.
    """
    root = _block(
        c.ROOT,
        [
            _element(c.CUSTOMS_PROCEDURE, c.PROCEDURE_IMPORT),
            _element(c.CUSTOMS_MODE_CODE, c.MODE_CODE_HOME_USE),
            _shipment(declaration, review),
            _filler(declaration.filler, review),
        ],
    )
    if root is None:  # pragma: no cover - a declaration always has goods and constants
        raise ValueError("a declaration produced no elements at all")
    return root.model_copy(update={"attributes": c.ROOT_ATTRIBUTES})


def _shipment(declaration: Declaration, review: list[ReviewItem]) -> Element | None:
    children: list[Element | None] = [
        _origin_country_name(declaration, review),
        _element(c.SPECIFICATION_NUMBER, c.SINGLE_SPECIFICATION),
        _element(c.SPECIFICATION_LIST_NUMBER, c.SINGLE_SPECIFICATION),
        _element(c.TOTAL_GOODS_NUMBER, integer_text(declaration.total_goods_number.value)),
        _total_packages(declaration, review),
        _element(c.TOTAL_SHEET_NUMBER, c.SINGLE_SHEET),
        _consignor(declaration.consignor, review),
    ]
    children.extend(_importer_trio(declaration.importer, review))
    children.append(_goods_location(declaration.goods_location, review))
    children.append(_consignment(declaration.consignment, review))
    children.append(_contract_terms(declaration.consignment, review))
    children.extend(_goods_item(item, review) for item in declaration.goods)
    return _block(c.SHIPMENT, children)


def _origin_country_name(
    declaration: Declaration, review: list[ReviewItem]
) -> Element | None:
    """Box 16. The one country field with no code half, so nothing pairs with it."""
    if declaration.origin_country_name is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="shipment origin country",
                detail="No origin country was resolved, so box 16 was left out. 69 of the "
                "71 ground truths carry it; fill it on the portal.",
            )
        )
        return None
    return _element(c.ORIGIN_COUNTRY_NAME_SHIPMENT, declaration.origin_country_name.value)


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
    return _element(
        c.TOTAL_PACKAGE_NUMBER, decimal_text(declaration.total_package_number.value)
    )


# --- parties --------------------------------------------------------------------------


def _organization_name(
    organization: Organization | None, concept: str, review: list[ReviewItem]
) -> Element | None:
    """The name leaf, falling back to the one placeholder the contract permits."""
    if organization is not None and organization.name is not None:
        written = organization.name.value.strip()
        if written:
            return _element(c.ORGANIZATION_NAME, written)
    review.append(
        ReviewItem(
            kind=ReviewKind.PLACEHOLDER,
            concept=concept,
            detail=f"No name was read for this party, so `{c.ABSENT_ORGANIZATION_NAME}` "
            "was filed. This is a free-text leaf and one of only four elements in the "
            "document permitted to carry a placeholder.",
            remedy="The party's name on the invoice or the consignment note.",
        )
    )
    return _element(c.ORGANIZATION_NAME, c.ABSENT_ORGANIZATION_NAME)


def _consignor(organization: Organization | None, review: list[ReviewItem]) -> Element | None:
    """Box 2 — the foreign seller or shipper. Free text with no tax code anywhere."""
    address = None
    if organization is not None and organization.address is not None:
        address = _block(
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
    return _block(c.CONSIGNOR, [name, address])


def _importer_trio(
    organization: Organization | None, review: list[ReviewItem]
) -> list[Element | None]:
    """Boxes 8, 9 and 14 — one company, three identical blocks.

    Dossier 03 §5.3 records that the portal discards all three wholesale and re-fills
    them from the state register via its own tax-code lookup, so their content is an
    import preview rather than filed data. They are written anyway: the deciding
    experiment — a tax code matching the authenticated account — was never run, and all
    71 ground truths file the three blocks byte for byte identically.
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
        _block(role, [name, features, address])
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
    return _block(c.ORGANIZATION_FEATURES, [_element(c.TAX_CODE, code_text(digits))])


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
        street = _element(c.STREET_HOUSE, written)
    return _block(
        c.ADDRESS,
        [
            _element(c.COUNTRY_CODE, c.DOMESTIC_COUNTRY_CODE),
            _element(c.COUNTRY_NAME, c.DOMESTIC_COUNTRY_NAME),
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
        _element(c.COUNTRY_CODE, code_text(country.code.value)),
        _element(c.COUNTRY_NAME, country.name.value),
    ]


# --- goods location -------------------------------------------------------------------


def _goods_location(
    location: GoodsLocation | None, review: list[ReviewItem]
) -> Element | None:
    """Box 30 — present in every ground truth, and derivable from no document."""
    if location is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="goods location",
                detail="No declarant profile supplied a goods location, so box 30 was "
                "left out. It is a property of where this importer clears, not of the "
                "shipment, and all 71 ground truths carry it.",
                remedy="The importer's warehouse information type and customs office.",
            )
        )
        return None
    if location.customs_zone_number is not None:
        _unfilable(
            "customs zone number",
            "A customs zone was supplied and none of the 71 ground truths carries an "
            "element for it, so it was not filed. Set it on the portal if box 30 needs it.",
            review,
        )
    return _block(
        c.GOODS_LOCATION,
        [
            _element(
                c.GOODS_LOCATION_INFORMATION_TYPE,
                code_text(location.information_type_code.value),
            ),
            _element(c.GOODS_LOCATION_OFFICE, code_text(location.customs_office_code.value)),
            _element(c.GOODS_LOCATION_COUNTRY_CODE, code_text(location.country_code.value)),
        ],
    )


# --- consignment and contract terms ----------------------------------------------------


def _consignment(consignment: Consignment, review: list[ReviewItem]) -> Element | None:
    """Boxes 19, 17 and 25 — and nothing else. The crossing office and the vehicle
    records have no element in any filing in the evidence base."""
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
        indicator = _element(
            c.CONTAINER_INDICATOR, boolean_text(consignment.container_indicator.value)
        )

    if consignment.dispatch_country is not None:
        _unfilable(
            "dispatch country",
            "A dispatch country was resolved and no filing in the evidence base carries "
            "a dispatch-country element, so it was not filed.",
            review,
        )
    if consignment.border_office is not None:
        _unfilable(
            "border crossing office",
            "A crossing office was resolved and no filing in the evidence base carries a "
            "border-office block, so it was not filed. Box 12 is filled on the portal.",
            review,
        )

    return _block(
        c.CONSIGNMENT,
        [
            indicator,
            _element(c.DESTINATION_COUNTRY_CODE, c.DOMESTIC_COUNTRY_CODE),
            _element(c.DESTINATION_COUNTRY_NAME, c.DOMESTIC_COUNTRY_NAME),
            _transport(
                c.DEPARTURE_TRANSPORT,
                consignment.departure_transport,
                "arrival transport",
                review,
            ),
            _transport(
                c.BORDER_TRANSPORT,
                consignment.border_transport,
                "border transport",
                review,
            ),
        ],
    )


def _transport(
    element_name: str,
    block: TransportBlock | None,
    concept: str,
    review: list[ReviewItem],
) -> Element | None:
    """One transport block: the mode code, and only the mode code.

    All 71 ground truths carry exactly one child here. The vehicle plates and the vehicle
    count the domain model holds have no element anywhere in the evidence base, so they
    are reported rather than written — the alternative is inventing an element name,
    which rejects the file with no field named.
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
    if block.vehicles or block.vehicle_quantity is not None:
        _unfilable(
            f"{concept} vehicles",
            f"{len(block.vehicles)} vehicle record(s) were read and no filing in the "
            "evidence base carries a transport-means element, so the plates were not "
            "filed. Box 18 and box 21 are filled on the portal.",
            review,
        )
    return _block(
        element_name, [_element(c.TRANSPORT_MODE_CODE, code_text(block.mode_code.value))]
    )


def _contract_terms(consignment: Consignment, review: list[ReviewItem]) -> Element | None:
    """Currency, total, trade country and Incoterms — a sibling of the consignment block,
    not a child of it.

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
        currency = _element(c.CONTRACT_CURRENCY_CODE, code_text(consignment.currency_code.value))

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
        total = _element(
            c.TOTAL_INVOICE_AMOUNT, decimal_text(consignment.total_invoice_amount.value)
        )

    trade_country = None
    if consignment.trade_country_code is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="trade country",
                detail="Trade-country detection found nothing in the seller's address or "
                "name, so box 11 was left out. 69 of the 71 ground truths carry it.",
            )
        )
    else:
        trade_country = _element(
            c.TRADE_COUNTRY_CODE, code_text(consignment.trade_country_code.value)
        )

    return _block(
        c.CONTRACT_TERMS,
        [currency, total, trade_country, _delivery_terms(consignment.delivery_terms, review)],
    )


def _delivery_terms(terms: DeliveryTerms | None, review: list[ReviewItem]) -> Element | None:
    """Box 20 — the Incoterms code alone. No filing in the evidence base carries a place."""
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
    if terms.place is not None:
        _unfilable(
            "delivery place",
            "An Incoterms place was read and no filing in the evidence base carries a "
            "delivery-place element, so it was not filed.",
            review,
        )
    if terms.terms_code is None:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="delivery terms code",
                detail="No Incoterms code was read, so the block was left out; it is the "
                "block's only child.",
            )
        )
        return None
    return _block(c.DELIVERY_TERMS, [_element(c.DELIVERY_TERMS_CODE, terms.terms_code.value)])


# --- goods items ----------------------------------------------------------------------


def _goods_item(item: GoodsItem, review: list[ReviewItem]) -> Element | None:
    """One goods block, children in the contract's order. The only repeatable element in
    the document."""
    children: list[Element | None] = [
        _element(c.GOODS_NUMERIC, integer_text(item.item_number)),
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
    return _block(c.GOODS_ITEM, children)


def _description(item: GoodsItem, review: list[ReviewItem]) -> Element | None:
    written = item.description.value.strip()
    if not written:
        review.append(
            ReviewItem(
                kind=ReviewKind.OMITTED,
                concept="line goods description",
                detail="The line reached the filing adapter with an empty description, "
                "so box 31 was left out. All 2842 goods items in the evidence base carry "
                "one.",
                line_id=item.line_id,
            )
        )
        return None
    return _element(c.GOODS_DESCRIPTION, written)


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
    return _element(element_name, decimal_text(value.value))


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
    return _element(c.COMMODITY_CODE, code_text(item.commodity_code.value))


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
        _element(c.ORIGIN_COUNTRY_CODE, code_text(item.origin_country.code.value)),
        _element(c.ORIGIN_COUNTRY_NAME, item.origin_country.name.value),
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
    return _element(c.CUSTOMS_COST_METHOD, code_text(item.customs_cost_method.value))


def _preferences() -> Element | None:
    """Box 36 — the no-privilege marker, three times, and never anything else.

    A duty preference is derivable: every preferential line in the corpus is
    Iranian-origin under the EAEU–Iran agreement. It is deliberately never derived.
    Claiming one the goods do not qualify for under-declares duty, which is legally
    consequential; this marker merely over-declares and is corrected on the portal.
    """
    return _block(
        c.PREFERENCES,
        [
            _element(c.PREFERENCE_TAX, c.NO_PREFERENCE),
            _element(c.PREFERENCE_DUTY, c.NO_PREFERENCE),
            _element(c.PREFERENCE_RATE, c.NO_PREFERENCE),
        ],
    )


def _supplementary_quantity(item: GoodsItem, review: list[ReviewItem]) -> Element | None:
    """Box 41 — a figure, its unit name and its zero-padded unit code, in that order.

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
    return _block(
        c.SUPPLEMENTARY_QUANTITY,
        [
            _element(c.GOODS_QUANTITY, decimal_text(quantity.quantity.value)),
            _element(c.MEASURE_UNIT_NAME, quantity.unit_name.value),
            _element(c.MEASURE_UNIT_CODE, code_text(quantity.unit_code.value)),
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
        count = _element(c.PACKAGE_QUANTITY, decimal_text(packaging.package_count.value))

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
        type_code = _element(c.PACKAGE_TYPE_CODE, code_text(packaging.package_type_code.value))

    packing = None
    if packaging.packing_code is not None:
        packing = _block(
            c.PACKING_INFORMATION,
            [
                _element(c.PACKING_CODE, code_text(packaging.packing_code.value)),
                _element(c.PACKING_QUANTITY, decimal_text(packaging.packing_quantity.value))
                if packaging.packing_quantity is not None
                else None,
            ],
        )

    return _block(c.GOODS_PACKAGING, [count, type_code, packing])


def _goods_procedure() -> Element | None:
    """Boxes 37 and 1 — three zero-padded fixed-width tokens whose widths are contract."""
    return _block(
        c.GOODS_PROCEDURE,
        [
            _element(c.MAIN_MODE_CODE, c.MODE_CODE_HOME_USE),
            _element(c.PRECEDING_MODE_CODE, c.PRECEDING_MODE_NONE),
            _element(c.GOODS_TRANSFER_FEATURE, c.TRANSFER_FEATURE_NONE),
        ],
    )


# --- filler ---------------------------------------------------------------------------


def _filler(filler: FillerPerson | None, review: list[ReviewItem]) -> Element | None:
    """Box 54, at root level and outside the shipment. Surname and given name, and no
    contact block: no filing in the evidence base carries a phone or an address for the
    filler."""
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
    if filler.phone is not None or filler.email is not None:
        _unfilable(
            "filler contact details",
            "A phone or e-mail address was supplied and no filing in the evidence base "
            "carries a contact element under the filler, so neither was filed.",
            review,
        )
    return _block(
        c.FILLER,
        [
            _element(c.FILLER_SURNAME, filler.surname.value),
            _element(c.FILLER_GIVEN_NAME, filler.given_name.value),
        ],
    )
