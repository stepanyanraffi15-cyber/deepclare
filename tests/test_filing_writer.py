"""The write direction, one contract rule per test."""

from __future__ import annotations

from decimal import Decimal

from filing_fixtures import coded, declaration, goods_item, traced

from deepclare.domain.declaration import (
    Consignment,
    DeliveryTerms,
    Organization,
    Packaging,
    PostalAddress,
)
from deepclare.domain.review import ReviewKind
from deepclare.filing import contract as c
from deepclare.filing.document import Element, walk
from deepclare.filing.writer import write_declaration


def child_names(root: Element, element_name: str) -> list[str]:
    block = next(item.element for item in walk(root) if item.element.name == element_name)
    return [child.name for child in block.children]


def paths(root: Element) -> list[str]:
    return [item.path for item in walk(root)]


def test_a_goods_block_follows_the_stated_emission_order() -> None:
    document = write_declaration(declaration())
    written = child_names(document.tree, c.GOODS_ITEM)
    expected = [name for name in c.SEQUENCES[c.GOODS_ITEM] if name in written]
    assert written == expected


def test_the_packaging_quantity_precedes_the_type_code() -> None:
    document = write_declaration(declaration())
    written = child_names(document.tree, c.GOODS_PACKAGING)
    assert written.index(c.PACKAGE_QUANTITY) < written.index(c.PACKAGE_TYPE_CODE)


def test_the_additional_sign_slot_is_never_written() -> None:
    document = write_declaration(declaration())
    assert c.ADDITIONAL_SIGN not in child_names(document.tree, c.GOODS_ITEM)


def test_the_misspellings_are_reproduced_character_for_character() -> None:
    document = write_declaration(declaration())
    for spelling in ("CounryName", "ESADout_CUConsigment", "PakageQuantity", "PakageTypeCode"):
        assert spelling in document.xml


def test_the_preference_marker_is_two_letters_and_not_two_zeros() -> None:
    document = write_declaration(declaration())
    block = next(
        item.element for item in walk(document.tree) if item.element.name == c.PREFERENCES
    )
    for child in block.children:
        assert [ord(character) for character in child.text or ""] == [79, 79]


def test_the_procedure_constants_keep_their_widths() -> None:
    document = write_declaration(declaration())
    block = next(
        item.element for item in walk(document.tree) if item.element.name == c.GOODS_PROCEDURE
    )
    assert [child.text for child in block.children] == ["40", "00", "000"]


def test_an_abstention_omits_the_code_and_raises_a_review_item() -> None:
    document = write_declaration(
        declaration(goods=(goods_item(commodity_code=None),))
    )
    assert c.COMMODITY_CODE not in child_names(document.tree, c.GOODS_ITEM)
    assert any(
        item.concept == "line commodity code" and item.kind is ReviewKind.OMITTED
        for item in document.review_items
    )


def test_an_absent_origin_omits_both_halves_of_the_pair() -> None:
    document = write_declaration(declaration(goods=(goods_item(origin_country=None),)))
    written = child_names(document.tree, c.GOODS_ITEM)
    assert c.ORIGIN_COUNTRY_CODE not in written
    assert c.ORIGIN_COUNTRY_NAME not in written


def test_a_missing_supplementary_quantity_fails_conformance_and_is_flagged() -> None:
    document = write_declaration(
        declaration(goods=(goods_item(supplementary_quantity=None),))
    )
    failed = {outcome.rule for outcome in document.conformance.failures}
    assert "goods-quantity-present" in failed
    assert any(
        item.kind is ReviewKind.NEEDS_REVIEW
        and item.concept == "line supplementary quantity"
        for item in document.review_items
    )


def test_a_missing_organization_name_files_the_one_permitted_placeholder() -> None:
    document = write_declaration(declaration(consignor=Organization()))
    consignor = next(
        item.element for item in walk(document.tree) if item.element.name == c.CONSIGNOR
    )
    assert consignor.children[0].text == c.ABSENT_ORGANIZATION_NAME
    assert any(item.kind is ReviewKind.PLACEHOLDER for item in document.review_items)
    assert document.conformance.conforms


def test_no_other_leaf_ever_carries_a_placeholder() -> None:
    document = write_declaration(
        declaration(consignor=Organization(), importer=Organization())
    )
    carrying = [
        item.path
        for item in walk(document.tree)
        if (item.element.text or "") == c.ABSENT_ORGANIZATION_NAME
    ]
    assert set(carrying) <= c.PLACEHOLDER_PERMITTED_PATHS


def test_an_over_long_street_address_is_truncated_and_recorded_as_a_guess() -> None:
    document = write_declaration(
        declaration(
            importer=Organization(
                name=traced("ԱՐԱՐԱՏ ՍՊԸ"),
                tax_code=traced("01234567"),
                address=PostalAddress(street_house=traced("Ա" * 80)),
            )
        )
    )
    street = next(
        item.element for item in walk(document.tree) if item.element.name == c.STREET_HOUSE
    )
    assert len(street.text or "") == 50
    assert any(
        item.kind is ReviewKind.GUESS and item.concept == "importer street address"
        for item in document.review_items
    )


def test_a_non_numeric_tax_code_omits_the_whole_wrapper() -> None:
    document = write_declaration(
        declaration(
            importer=Organization(name=traced("ԱՐԱՐԱՏ ՍՊԸ"), tax_code=traced("TIN-12x"))
        )
    )
    assert c.ORGANIZATION_FEATURES not in [item.element.name for item in walk(document.tree)]
    assert any(item.concept == "importer tax code" for item in document.review_items)


def test_the_importer_is_written_into_all_three_party_blocks() -> None:
    document = write_declaration(declaration())
    names = [item.element.name for item in walk(document.tree)]
    for role in (c.CONSIGNEE, c.RESPONSIBLE_PERSON, c.DECLARANT):
        assert role in names


def test_no_importer_at_all_omits_the_whole_trio() -> None:
    document = write_declaration(declaration(importer=None))
    names = [item.element.name for item in walk(document.tree)]
    for role in (c.CONSIGNEE, c.RESPONSIBLE_PERSON, c.DECLARANT):
        assert role not in names
    assert any(item.concept == "importer" for item in document.review_items)


def test_an_all_unknown_block_is_omitted_rather_than_written_empty() -> None:
    """The delivery-terms and contract-terms containers are two of the three the
    predecessor could serialize as `<tag />`, which appears in zero filed declarations."""
    document = write_declaration(
        declaration(consignment=Consignment(delivery_terms=DeliveryTerms()))
    )
    written = [item.element.name for item in walk(document.tree)]
    assert c.DELIVERY_TERMS not in written
    assert c.CONTRACT_TERMS not in written
    assert "/>" not in document.xml


def test_a_line_with_no_packaging_writes_no_packaging_block() -> None:
    document = write_declaration(declaration(goods=(goods_item(packaging=Packaging()),)))
    assert c.GOODS_PACKAGING not in [item.element.name for item in walk(document.tree)]


def test_packing_information_is_omitted_whole_when_no_code_resolves() -> None:
    document = write_declaration(
        declaration(
            goods=(
                goods_item(
                    packaging=Packaging(
                        package_count=traced(Decimal("4")),
                        package_type_code=traced("1"),
                        packing_quantity=traced(Decimal("4")),
                    )
                ),
            )
        )
    )
    assert c.PACKING_INFORMATION not in [item.element.name for item in walk(document.tree)]


def test_the_document_is_never_reported_filable_while_names_are_unconfirmed() -> None:
    document = write_declaration(declaration())
    assert document.conformance.conforms
    assert not document.conformance.filable
    assert {outcome.rule for outcome in document.conformance.unconfirmed} >= {
        "element-name-evidence",
        "namespace-assignment",
    }


def test_the_root_carries_the_fixed_document_mode_identifier() -> None:
    document = write_declaration(declaration())
    assert dict(document.tree.attributes)["DocumentModeID"] == "1006107E"


def test_goods_items_appear_in_the_order_they_were_given() -> None:
    document = write_declaration(
        declaration(
            total_goods_number=traced(2),
            goods=(
                goods_item(),
                goods_item(item_number=2, line_id="2", origin_country=coded("TR", "ԹՈՒՐՔԻԱ")),
            ),
        )
    )
    numbers = [
        item.element.children[0].text
        for item in walk(document.tree)
        if item.element.name == c.GOODS_ITEM
    ]
    assert numbers == ["1", "2"]
