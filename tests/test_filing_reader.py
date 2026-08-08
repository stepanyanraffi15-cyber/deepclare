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
