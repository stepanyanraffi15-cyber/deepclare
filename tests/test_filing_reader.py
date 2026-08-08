"""The read direction: what it recovers, what it tolerates, and what it refuses.

A filed declaration is not this repository's own output. It carries prefixes we did not
choose, blocks we never write, and a repetition idiom that renames instead of repeating.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from filing_fixtures import declaration, goods_item, traced

from deepclare.domain.provenance import ValueOrigin
from deepclare.filing.errors import MalformedFiledDocument
from deepclare.filing.reader import read_declaration
from deepclare.filing.writer import write_declaration

WRITTEN = write_declaration(declaration()).xml


def test_a_document_this_adapter_wrote_reads_back_and_re_emits_identically() -> None:
    parsed = read_declaration(WRITTEN, filing_id="f1")
    assert write_declaration(parsed.declaration).xml == WRITTEN


def test_values_come_back_typed_rather_than_as_text() -> None:
    item = read_declaration(WRITTEN, filing_id="f1").declaration.goods[0]
    assert item.gross_weight is not None
    assert item.gross_weight.value == Decimal("10")
    assert item.supplementary_quantity is not None
    assert item.supplementary_quantity.unit_code.value == "796"


def test_a_read_value_carries_provenance_naming_the_filing() -> None:
    parsed = read_declaration(WRITTEN, filing_id="filing-77")
    provenance = parsed.declaration.goods[0].description.provenance
    assert provenance.origin is ValueOrigin.EXTRACTED
    assert provenance.source_document_id == "filing-77"


def test_the_importer_trio_is_read_once_and_the_repeats_are_accounted_for() -> None:
    parsed = read_declaration(WRITTEN, filing_id="f1")
    assert parsed.declaration.importer is not None
    assert parsed.declaration.importer.tax_code is not None
    repeats = [item for item in parsed.unread if "identically" in item.reason]
    assert len(repeats) == 2


def test_every_unread_element_of_our_own_document_is_a_known_one() -> None:
    parsed = read_declaration(WRITTEN, filing_id="f1")
    assert all(item.known for item in parsed.unread)


def test_elements_are_located_by_local_name_whatever_the_prefix() -> None:
    prefixed = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<esad:ESADout_CU xmlns:esad="urn:customs.ru:one" xmlns:cat="urn:customs.ru:two">'
        "<esad:TotalGoodsNumber>1</esad:TotalGoodsNumber>"
        "<cat:ESADout_CUGoods>"
        "<cat:GoodsNumeric>1</cat:GoodsNumeric>"
        "<cat:GoodsDescription>ՊԱՐԿԵՐ</cat:GoodsDescription>"
        "<cat:GoodsTNVEDCode>39232900000</cat:GoodsTNVEDCode>"
        "</cat:ESADout_CUGoods>"
        "</esad:ESADout_CU>"
    )
    parsed = read_declaration(prefixed, filing_id="f2")
    assert parsed.declaration.goods[0].commodity_code is not None
    assert parsed.declaration.goods[0].commodity_code.value == "39232900000"


def test_an_address_under_a_different_namespace_is_still_found() -> None:
    mixed = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ESADout_CU xmlns="urn:customs.ru:one" xmlns:other="urn:customs.ru:three">'
        "<TotalGoodsNumber>1</TotalGoodsNumber>"
        "<ESADout_CUConsignor><OrganizationName>PARS</OrganizationName>"
        "<other:Address><other:CountryCode>IR</other:CountryCode>"
        "<other:CounryName>ԻՐԱՆ</other:CounryName></other:Address>"
        "</ESADout_CUConsignor>"
        "<ESADout_CUGoods><GoodsNumeric>1</GoodsNumeric>"
        "<GoodsDescription>ՊԱՐԿԵՐ</GoodsDescription></ESADout_CUGoods>"
        "</ESADout_CU>"
    )
    consignor = read_declaration(mixed, filing_id="f3").declaration.consignor
    assert consignor is not None
    assert consignor.address is not None
    assert consignor.address.country is not None
    assert consignor.address.country.code.value == "IR"


def test_the_un_namespaced_correction_artifact_is_tolerated_and_named() -> None:
    exported = WRITTEN.replace(
        "</ESADout_CUGoods>", "<customsCostBeforeKdt>100</customsCostBeforeKdt></ESADout_CUGoods>"
    )
    parsed = read_declaration(exported, filing_id="f4")
    artifact = next(item for item in parsed.unread if item.path.endswith("customsCostBeforeKdt"))
    assert artifact.known
    assert artifact.value == "100"


def test_a_repetition_by_renaming_is_reported_rather_than_missed() -> None:
    doubled = WRITTEN.replace(
        "<NetWeightQuantity>9</NetWeightQuantity>",
        "<NetWeightQuantity>9</NetWeightQuantity><NetWeightQuantity2>4</NetWeightQuantity2>",
    )
    parsed = read_declaration(doubled, filing_id="f5")
    repeat = next(item for item in parsed.unread if item.path.endswith("NetWeightQuantity2"))
    assert "repetition by renaming" in repeat.reason
    assert repeat.value == "4"


def test_a_presented_document_block_is_read_past(  ) -> None:
    with_documents = WRITTEN.replace(
        "</ESADout_CUGoods>",
        "<PresentedDocument><PrDocumentName>ԱԿՏ</PrDocumentName></PresentedDocument>"
        "</ESADout_CUGoods>",
    )
    parsed = read_declaration(with_documents, filing_id="f6")
    assert len(parsed.declaration.goods) == 1
    assert any(item.path.endswith("PresentedDocument") and item.known for item in parsed.unread)


def test_a_malformed_number_is_reported_and_does_not_become_a_value() -> None:
    broken = WRITTEN.replace(
        "<GrossWeightQuantity>10</GrossWeightQuantity>",
        "<GrossWeightQuantity>ten</GrossWeightQuantity>",
    )
    parsed = read_declaration(broken, filing_id="f7")
    assert parsed.declaration.goods[0].gross_weight is None
    assert any(item.reason == "not a decimal number" for item in parsed.unread)


def test_the_placeholder_organization_name_reads_back_as_an_absence() -> None:
    placeholder = WRITTEN.replace(
        "<OrganizationName>PARS PLASTIC CO</OrganizationName>",
        "<OrganizationName>-</OrganizationName>",
    )
    consignor = read_declaration(placeholder, filing_id="f8").declaration.consignor
    assert consignor is not None
    assert consignor.name is None


def test_the_census_counts_every_element_name_in_the_file() -> None:
    census = read_declaration(WRITTEN, filing_id="f9").census
    assert census["ESADout_CUGoods"] == 1
    assert census["OrganizationName"] == 4


def test_a_document_declaring_a_dtd_is_refused() -> None:
    with pytest.raises(MalformedFiledDocument):
        read_declaration('<!DOCTYPE x [<!ENTITY a "b">]><ESADout_CU/>', filing_id="f10")


def test_a_document_that_is_not_a_declaration_is_refused() -> None:
    with pytest.raises(MalformedFiledDocument):
        read_declaration("<Invoice><Line/></Invoice>", filing_id="f11")


def test_a_declaration_with_no_goods_count_is_refused() -> None:
    with pytest.raises(MalformedFiledDocument):
        read_declaration("<ESADout_CU><CustomsProcedure>IM</CustomsProcedure></ESADout_CU>", filing_id="f12")


def test_a_goods_line_with_no_code_reads_back_as_an_abstention() -> None:
    written = write_declaration(declaration(goods=(goods_item(commodity_code=None),))).xml
    assert read_declaration(written, filing_id="f13").declaration.goods[0].commodity_code is None


def test_two_transport_blocks_are_kept_apart() -> None:
    from deepclare.domain.declaration import Consignment, TransportBlock, TransportMeansRecord

    consignment = Consignment(
        container_indicator=traced(True),
        departure_transport=TransportBlock(
            mode_code=traced("31"),
            vehicles=(TransportMeansRecord(identifier=traced("12AB345")),),
            vehicle_quantity=traced(2),
        ),
        border_transport=TransportBlock(
            mode_code=traced("30"),
            vehicles=(TransportMeansRecord(identifier=traced("77XY910")),),
            vehicle_quantity=traced(1),
        ),
    )
    written = write_declaration(declaration(consignment=consignment)).xml
    read_back = read_declaration(written, filing_id="f14").declaration.consignment
    assert read_back.departure_transport is not None
    assert read_back.border_transport is not None
    assert read_back.departure_transport.mode_code.value == "31"
    assert read_back.border_transport.mode_code.value == "30"
