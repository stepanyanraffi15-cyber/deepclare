"""Parse an ESADout_CU customs declaration (XML) into a comparable structure.

This is intentionally namespace-agnostic and forgiving: it matches elements by
their *local* name so it works whether or not the document declares a namespace,
and treats a missing leaf as ``None`` (never a crash). Only the fields the
verifier scores are extracted — the goal is a small canonical view, not a full
model of the schema.

Stdlib only, so the whole package copies into another repo unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class Good:
    """One goods line, reduced to the fields we measure."""

    numeric: int | None
    description: str
    hs_code: str
    origin: str | None
    unit: str | None  # MeasureUnitQualifierCode (e.g. 166 = KG)
    quantity: float | None  # GoodsQuantity
    net_weight: float | None  # NetWeightQuantity
    gross_weight: float | None  # GrossWeightQuantity
    invoiced_cost: float | None  # InvoicedCost
    package_count: float | None  # PakageQuantity


@dataclass(frozen=True)
class Declaration:
    """A whole declaration, reduced to goods + a few shipment totals."""

    goods: tuple[Good, ...]
    total_goods: int | None
    total_packages: float | None
    total_cost: float | None
    currency: str | None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first(elem: ET.Element, name: str) -> ET.Element | None:
    """First descendant (or self) whose local name is ``name``."""
    if _local(elem.tag) == name:
        return elem
    for child in elem.iter():
        if _local(child.tag) == name:
            return child
    return None


def _text(elem: ET.Element, name: str) -> str | None:
    node = _first(elem, name)
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def _num(elem: ET.Element, name: str) -> float | None:
    raw = _text(elem, name)
    if raw is None:
        return None
    cleaned = raw.replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _int(elem: ET.Element, name: str) -> int | None:
    value = _num(elem, name)
    return int(value) if value is not None else None


def _parse_good(node: ET.Element) -> Good:
    return Good(
        numeric=_int(node, "GoodsNumeric"),
        description=_text(node, "GoodsDescription") or "",
        hs_code=_text(node, "GoodsTNVEDCode") or "",
        origin=_text(node, "OriginCountryCode"),
        unit=_text(node, "MeasureUnitQualifierCode"),
        quantity=_num(node, "GoodsQuantity"),
        net_weight=_num(node, "NetWeightQuantity"),
        gross_weight=_num(node, "GrossWeightQuantity"),
        invoiced_cost=_num(node, "InvoicedCost"),
        package_count=_num(node, "PakageQuantity"),
    )


def parse_declaration(source: str | Path) -> Declaration:
    """Parse a declaration from an XML string or a file path."""
    text = _read(source)
    root = ET.fromstring(text)
    goods = tuple(
        _parse_good(node) for node in root.iter() if _local(node.tag) == "ESADout_CUGoods"
    )
    return Declaration(
        goods=goods,
        total_goods=_int(root, "TotalGoodsNumber"),
        total_packages=_num(root, "TotalPackageNumber"),
        total_cost=_num(root, "TotalCustCost"),
        currency=_text(root, "CustCostCurrencyCode"),
    )


def _read(source: str | Path) -> str:
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8")
    stripped = source.lstrip()
    if stripped.startswith("<"):
        return source
    return Path(source).read_text(encoding="utf-8")
