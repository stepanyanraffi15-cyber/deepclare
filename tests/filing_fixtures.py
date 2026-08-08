"""A minimal internal declaration the filing tests vary one field at a time.

Values are invented. Nothing here is a sample declaration and nothing is derived from
anyone's filing.
"""

from __future__ import annotations

from decimal import Decimal

from deepclare.domain.declaration import (
    CodedValue,
    Consignment,
    Declaration,
    GoodsItem,
    Organization,
    Packaging,
    PostalAddress,
    SupplementaryQuantity,
)
from deepclare.domain.provenance import Provenance, Traced, ValueOrigin

EXTRACTED = Provenance(origin=ValueOrigin.EXTRACTED, source_document_id="invoice-1")


def traced(value: object) -> Traced:
    return Traced(value=value, provenance=EXTRACTED)


def coded(code: str, name: str) -> CodedValue:
    return CodedValue(code=traced(code), name=traced(name))


def goods_item(**overrides: object) -> GoodsItem:
    fields: dict[str, object] = {
        "item_number": 1,
        "line_id": "1",
        "description": traced("ՊԱՐԿԵՐ"),
        "gross_weight": traced(Decimal("10")),
        "net_weight": traced(Decimal("9")),
        "invoiced_cost": traced(Decimal("100")),
        "commodity_code": traced("39232900000"),
        "origin_country": coded("IR", "ԻՐԱՆ"),
        "customs_cost_method": traced("1"),
        "supplementary_quantity": SupplementaryQuantity(
            quantity=traced(Decimal("500")),
            unit_code=traced("796"),
            unit_name=traced("ՀԱՏ"),
        ),
        "packaging": Packaging(
            package_count=traced(Decimal("4")), package_type_code=traced("1")
        ),
    }
    fields.update(overrides)
    return GoodsItem(**fields)


def declaration(**overrides: object) -> Declaration:
    fields: dict[str, object] = {
        "origin_country_name": traced("ԻՐԱՆ"),
        "total_goods_number": traced(1),
        "total_package_number": traced(Decimal("4")),
        "consignor": Organization(
            name=traced("PARS PLASTIC CO"),
            address=PostalAddress(country=coded("IR", "ԻՐԱՆ")),
        ),
        "importer": Organization(name=traced("ԱՐԱՐԱՏ ՍՊԸ"), tax_code=traced("01234567")),
        "consignment": Consignment(container_indicator=traced(False)),
        "goods": (goods_item(),),
    }
    fields.update(overrides)
    return Declaration(**fields)
