"""The case IR — one structured object every artifact is rendered *from*.

A case is a superset of the fields the invoice, the CMR, and the ground-truth
declaration each need; each renderer projects its own subset. Because all three
come from one object, they cannot disagree (invoice total = XML sum = CMR
weight) — that consistency is the whole reason for a spec-first IR.

Each ``GoodLine`` carries BOTH sides at once: the foreign invoice wording *and*
the Armenian/HS ground truth, so recombining lines keeps a correct declaration
for free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def _collapse(text: str) -> str:
    return re.sub(r"[^0-9a-z԰-֏]+", "", (text or "").lower())


@dataclass(frozen=True)
class Party:
    name: str
    address: str
    country: str  # ISO-3166 alpha-2
    tax_id: str | None = None  # ՀՎՀՀ (8 digits) for the Armenian importer


@dataclass(frozen=True)
class GoodLine:
    # --- invoice side (foreign) ---
    source_name: str  # what the seller prints, e.g. "CELLULOSE ETHER"
    trade_name: str | None  # brand + model, e.g. "MEILOSE GMC 3110"
    # --- declaration side (ground truth) ---
    armenian_desc: str  # GoodsDescription
    hs_code: str  # GoodsTNVEDCode
    unit: str  # MeasureUnitQualifierCode (166 = KG)
    origin: str  # OriginCountryCode (ISO-2)
    # --- atoms for the rubric ---
    brand: str | None
    material: str | None
    # --- volatile numerics (jittered per case) ---
    quantity: float
    net_weight: float
    gross_weight: float
    unit_price: float
    package_count: int
    package_type: str  # e.g. "BAG"

    @property
    def invoiced_cost(self) -> float:
        return round(self.quantity * self.unit_price, 2)

    def atoms(self) -> dict[str, str | None]:
        # Only assert an attribute the ground-truth description actually contains — otherwise the
        # rubric would demand a brand/model the declaration itself never states (history goods carry
        # brand in a separate field that isn't always in the Armenian text).
        desc = _collapse(self.armenian_desc)

        def stated(v: str | None) -> str | None:
            return v if v and _collapse(v) in desc else None

        return {"brand": stated(self.brand), "trade_name": stated(self.trade_name),
                "material": stated(self.material)}


@dataclass(frozen=True)
class Case:
    case_id: str
    seller: Party
    buyer: Party  # the Armenian importer
    carrier: Party
    currency: str
    incoterms: str
    dispatch_country: str  # ISO-2
    invoice_no: str
    date: str  # ISO yyyy-mm-dd
    goods: list[GoodLine] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return round(sum(g.invoiced_cost for g in self.goods), 2)

    @property
    def total_packages(self) -> int:
        return sum(g.package_count for g in self.goods)
