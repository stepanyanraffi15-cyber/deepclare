"""Render a case to the ground-truth declaration (ESADout_CU XML) + rubric atoms.

The XML is the *expected output* of the pipeline for the invoice/CMR rendered from
the same case, so it is correct by construction. Only the leaves the verifier reads
are emitted (goods fields + shipment totals + party names) — enough for scoring and
for the leak scanner to have real party text to check against, without pretending
to be a full schema-complete filing.
"""

from __future__ import annotations

import json
from xml.etree import ElementTree as ET

from .ir import Case


def _leaf(parent: ET.Element, tag: str, text: str | float | int | None) -> None:
    if text is None:
        return
    el = ET.SubElement(parent, tag)
    el.text = f"{text:g}" if isinstance(text, float) else str(text)


def _party(parent: ET.Element, tag: str, case_party) -> None:
    block = ET.SubElement(parent, tag)
    _leaf(block, "OrganizationName", case_party.name)
    addr = ET.SubElement(block, "Address")
    _leaf(addr, "CountryCode", case_party.country)
    _leaf(addr, "StreetHouse", case_party.address)
    if case_party.tax_id:
        _leaf(block, "UNN", case_party.tax_id)


def render_xml(case: Case) -> str:
    root = ET.Element("ESADout_CU")
    shipment = ET.SubElement(root, "ESADout_CUGoodsShipment")
    _leaf(shipment, "TotalGoodsNumber", len(case.goods))
    _leaf(shipment, "TotalPackageNumber", case.total_packages)
    _leaf(shipment, "TotalCustCost", case.total_cost)
    _leaf(shipment, "CustCostCurrencyCode", case.currency)
    _party(shipment, "ESADout_CUConsignor", case.seller)
    _party(shipment, "ESADout_CUConsignee", case.buyer)

    for i, g in enumerate(case.goods, start=1):
        node = ET.SubElement(shipment, "ESADout_CUGoods")
        _leaf(node, "GoodsNumeric", i)
        _leaf(node, "GoodsDescription", g.armenian_desc)
        _leaf(node, "GrossWeightQuantity", g.gross_weight)
        _leaf(node, "NetWeightQuantity", g.net_weight)
        _leaf(node, "InvoicedCost", g.invoiced_cost)
        _leaf(node, "GoodsTNVEDCode", g.hs_code)
        _leaf(node, "OriginCountryCode", g.origin)
        _leaf(node, "GoodsQuantity", g.quantity)
        _leaf(node, "MeasureUnitQualifierCode", g.unit)
        pack = ET.SubElement(node, "ESADGoodsPackaging")
        _leaf(pack, "PakageQuantity", g.package_count)
        _leaf(pack, "PakageTypeCode", g.package_type)

    return ET.tostring(root, encoding="unicode")


def render_atoms(case: Case) -> str:
    """The per-line brand/trade_name/material that make the verifier's rubric exact."""
    return json.dumps({"goods": [g.atoms() for g in case.goods]}, ensure_ascii=False, indent=1)
