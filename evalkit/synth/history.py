"""Reverse seeding — build a goods pool from the ground-truth history DB.

Flips the generator. Instead of deriving ground truth from a real invoice (limited to
the handful we own), start from the goods we ALREADY own — the history index: ~1900
unique goods, each with an Armenian description + HS code + unit + origin + weights +
(often) a brand — and manufacture matching invoice inputs. That scales the pool ~10-20x.

Invoice English names come free from the brand/part where present; the unbranded ones
are TRANSLATED from their Armenian description (a faithful translation of real ground
truth, not an invention) via `derive_english_names`. Real party names in the records are
collected as forbidden terms for the leak scan.
"""

from __future__ import annotations

import json
from pathlib import Path

from .ir import GoodLine
from .seed import Seed, keep_forbidden


def _f(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _clean(v) -> str | None:
    return v if v and str(v) not in ("None", "") else None


def load_history_seed(path: str | Path, limit: int | None = None) -> Seed:
    """A goods pool built straight from the history index records (jsonl)."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    records = [json.loads(x) for x in lines if x.strip()]
    if limit:
        records = records[:limit]

    pool: list[GoodLine] = []
    forbidden: set[str] = set()
    for r in records:
        if not _clean(r.get("code")):
            continue  # no HS code → can't be a valid ground-truth line
        net = _f(r.get("net_weight")) or 100.0
        gross = _f(r.get("gross_weight")) or round(net * 1.05, 1)
        brand, part = _clean(r.get("brand")), _clean(r.get("part_number"))
        trade = " ".join(x for x in (brand, part) if x) or None
        # deterministic plausible price (history goods are quantity/price-stripped)
        price = 1.0 + (int((r.get("record_key") or "0")[:6] or "0", 16) % 3900) / 100
        pool.append(
            GoodLine(
                source_name=trade or (r.get("description") or "GOODS")[:40],
                trade_name=trade,
                armenian_desc=r.get("description") or "",
                hs_code=_clean(r.get("code")) or "",
                unit=_clean(r.get("measure_unit_code")) or "166",
                origin=_clean(r.get("origin_country_code")) or "",
                brand=brand,
                material=None,
                quantity=net,
                net_weight=net,
                gross_weight=max(gross, net),
                unit_price=round(price, 2),
                package_count=max(1, int(net // 25) or 1),
                package_type="BAG",
            )
        )
        for key in ("importer_name", "sender_name", "importer_unn", "sender_unn"):
            v = _clean(r.get(key))
            if v and keep_forbidden(str(v)):
                forbidden.add(str(v))
    return Seed(pool=pool, forbidden_terms=forbidden, currency="USD", incoterms="CPT")


def derive_english_names(seed: Seed, model, batch: int = 25) -> dict[int, str]:
    """{index: english_name} — the product name for the invoice, for EVERY good.

    Translates the Armenian ground-truth description into what a foreign seller prints:
    the substance of the product (material, type, grade) WITHOUT the brand (which goes in
    the Model column) or the volatile quantities/packaging. A brand-only invoice line is
    unusable — the pipeline can't recover "pasteurized cream 50%" from "NOVBAR".
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    from pydantic import BaseModel

    class _Name(BaseModel):
        id: str
        english: str | None = None

    class _Names(BaseModel):
        items: list[_Name] = []

    prompt = (
        "Translate each Armenian customs goods description into a concise English product name a "
        "foreign seller prints on a commercial invoice — 3-8 words that KEEP the key attributes "
        "(material, type, grade, fat %, dimensions, etc.) but DROP quantities, weights, packaging, "
        "and any brand or mark. Return every id with its english name."
    )
    structured = model.with_structured_output(_Names)
    goods = list(enumerate(seed.pool))
    out: dict[int, str] = {}
    for start in range(0, len(goods), batch):
        chunk = goods[start : start + batch]
        human = "GOODS (JSON):\n" + json.dumps(
            [{"id": str(i), "hy": g.armenian_desc} for i, g in chunk], ensure_ascii=False
        )
        result = structured.invoke([SystemMessage(content=prompt), HumanMessage(content=human)])
        for m in result.items:
            if m.english and m.id.isdigit():
                out[int(m.id)] = m.english
    return out
