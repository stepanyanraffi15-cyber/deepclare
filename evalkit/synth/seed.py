"""Build a clean goods pool from an authoritative filed declaration.

Deliberately seeds from the declaration XML — NOT the scan cache, which is stale
and degraded (null trade names/codes). The declaration is the broker-confirmed
truth: Armenian description, HS code, unit, origin, and the volatile numerics,
with the trade name/brand embedded right in the Armenian text.

Also returns the real party names/tax IDs found in the seed so the leak scanner
(``guardrails``) can prove none of them survive into the synthetic output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from .ir import GoodLine

# A few Armenian material stems (extend per corpus).
_MATERIAL_STEMS = ("ՊՈՂՊԱՏ", "ՄԵՏԱՂ", "ՓԱՅՏ", "ԱՊԱԿԻ", "ՊԼԱՍՏ", "ԿԱՈՒՉ", "ԹՈՒՂԹ", "ԲԱՄԲԱԿ")

_ARMENIAN = re.compile(r"[԰-֏]")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(elem: ET.Element, name: str) -> str | None:
    for c in elem.iter():
        if _local(c.tag) == name and c.text and c.text.strip():
            return c.text.strip()
    return None


def _num(elem: ET.Element, name: str) -> float | None:
    raw = _text(elem, name)
    if raw is None:
        return None
    try:
        return float(raw.replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _product_name(desc: str) -> str | None:
    """The printed product identifier — the contiguous Latin run (brand + model) inside the
    Armenian text, e.g. 'MEILOSE GMC 3110', 'ARIEL 4000', 'MS116-1-1.6 ABB'. Handles the
    styles across seeds: brand+model (chemicals), brand+number (detergents), and
    model /BRAND/ QTY (electrical — the trailing pack count is dropped)."""
    start = re.search(r"[A-Za-z]", desc)
    if not start:
        return None
    tokens: list[str] = []
    for tok in re.split(r"[\s,]+", desc[start.start() :]):
        tok = tok.strip("/").strip()
        if not tok or _ARMENIAN.search(tok):
            break  # the Latin span ended (hit Armenian text)
        if re.search(r"[A-Za-z]", tok) or re.fullmatch(r"[\d.\-]+", tok):
            tokens.append(tok)
        else:
            break
    if re.search(r"/\s*[A-Za-z]", desc):  # a /BRAND/ delimiter → the trailing number is a qty
        while tokens and re.fullmatch(r"\d+", tokens[-1]):
            tokens.pop()
    name = " ".join(tokens[:6]).strip()
    return name or None


def _brand(product_name: str | None) -> str | None:
    """The brand within the product name — the first all-letters token (skips model codes)."""
    if not product_name:
        return None
    for tok in product_name.split():
        if tok.isalpha() and len(tok) >= 2:
            return tok
    return product_name.split()[0]


def _material(desc: str) -> str | None:
    up = desc.upper()
    for stem in _MATERIAL_STEMS:
        if stem in up:
            return stem
    return None


def keep_forbidden(term: str | None) -> bool:
    """A term worth scrubbing: a real party name (>=4 chars, not a bare code) or a real tax ID
    (>=6 digits). Rejects junk like the unit code '006' that spuriously matches everywhere."""
    if not term:
        return False
    t = str(term).strip()
    return len(t) >= 6 if t.isdigit() else len(t) >= 4


@dataclass(frozen=True)
class Seed:
    pool: list[GoodLine]
    forbidden_terms: set[str]  # real names/tax IDs that must never leak
    currency: str
    incoterms: str


def load_seed(declaration_xml: str | Path) -> Seed:
    """Parse a declaration (a file path OR the XML string itself) into a goods pool."""
    text = declaration_xml if isinstance(declaration_xml, str) and declaration_xml.lstrip().startswith("<") \
        else Path(declaration_xml).read_text(encoding="utf-8")
    root = ET.fromstring(text)
    pool: list[GoodLine] = []
    for node in root.iter():
        if _local(node.tag) != "ESADout_CUGoods":
            continue
        desc = _text(node, "GoodsDescription") or ""
        trade = _product_name(desc)
        qty = _num(node, "GoodsQuantity") or 0.0
        net = _num(node, "NetWeightQuantity") or qty
        gross = _num(node, "GrossWeightQuantity") or net
        cost = _num(node, "InvoicedCost") or 0.0
        pkg = _num(node, "PakageQuantity")
        pool.append(
            GoodLine(
                source_name=trade or (desc.split(",")[0][:40] if desc else "GOODS"),
                trade_name=trade,
                armenian_desc=desc,
                hs_code=_text(node, "GoodsTNVEDCode") or "",
                unit=_text(node, "MeasureUnitQualifierCode") or "166",
                origin=_text(node, "OriginCountryCode") or "",
                brand=_brand(trade),
                material=_material(desc),
                quantity=qty,
                net_weight=net,
                gross_weight=gross,
                unit_price=round(cost / qty, 4) if qty else 0.0,
                package_count=int(pkg) if pkg else 1,
                package_type="BAG",
            )
        )

    forbidden: set[str] = set()
    for name in ("OrganizationName", "PersonSurname", "PersonName"):
        for c in root.iter():
            if _local(c.tag) == name and c.text:
                forbidden.add(c.text.strip())
    for tax in ("UNN", "INN", "TaxpayerID"):
        forbidden.add(_text(root, tax))
    forbidden = {t for t in forbidden if keep_forbidden(t)}

    # NB: the declaration's CustCostCurrencyCode is the customs-VALUATION currency (AMD);
    # the invoice/trade currency (what InvoicedCost is denominated in) is USD/EUR — use that.
    return Seed(
        pool=pool,
        forbidden_terms=forbidden,
        currency="USD",
        incoterms="CPT",
    )
