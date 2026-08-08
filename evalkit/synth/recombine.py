"""Recombine a goods pool into a synthetic case — the anonymise + shuffle + jitter step.

Each case is a fictional *basket*: a subset of the pool, reordered, quantities and
prices jittered, with fresh fake parties. The combination never occurred in
reality even though every ingredient is realistic — which is what breaks the link
to any single real shipment while keeping each field plausible.

Deterministic in the seed: ``make_case(seed, n)`` always yields the same case, so
the corpus is reproducible and reviewable.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict

from .fake import armenian_importer, carrier, foreign_seller
from .ir import Case, GoodLine
from .seed import Seed


def partition(seed: Seed, k: int) -> list[Seed]:
    """Cut one large seed pool into k coherent sub-invoice families.

    Goods are grouped by HS chapter (2 digits) so each family stays product-coherent,
    then chapters are packed into k size-balanced bins. Turns a 135-line invoice into a
    handful of realistic smaller invoices to synthesise on independently. Families with
    fewer than 2 goods are dropped.
    """
    chapters: dict[str, list[GoodLine]] = defaultdict(list)
    for g in seed.pool:
        chapters[(g.hs_code or "")[:2]].append(g)
    bins: list[list[GoodLine]] = [[] for _ in range(k)]
    for _, goods in sorted(chapters.items(), key=lambda kv: -len(kv[1])):
        smallest = min(range(k), key=lambda i: len(bins[i]))
        bins[smallest].extend(goods)
    return [
        Seed(pool=b, forbidden_terms=seed.forbidden_terms, currency=seed.currency,
             incoterms=seed.incoterms)
        for b in bins
        if len(b) >= 2
    ]


def partition_by_size(seed: Seed, max_size: int) -> list[Seed]:
    """Split a big pool into HS-chapter-coherent families of at most `max_size` goods.

    Unlike ``partition`` (a fixed number of bins), this caps family size — so a huge
    chapter (e.g. 484 vehicle-part goods) becomes several evenly-sized families instead
    of one basket too big for a few invoices to sample.
    """
    chapters: dict[str, list[GoodLine]] = defaultdict(list)
    for g in seed.pool:
        chapters[(g.hs_code or "")[:2]].append(g)
    families: list[Seed] = []
    for goods in chapters.values():
        for i in range(0, len(goods), max_size):
            chunk = goods[i : i + max_size]
            if len(chunk) >= 2:
                families.append(Seed(pool=chunk, forbidden_terms=seed.forbidden_terms,
                                     currency=seed.currency, incoterms=seed.incoterms))
    return families

def _line_counts(pool_size: int) -> list[int]:
    """Invoice line-count buckets — bigger pools get bigger baskets to sample more goods."""
    counts = [2, 3, 5, 8]
    if pool_size >= 15:
        counts += [12, min(20, pool_size)]
    return counts


def _jitter_line(line: GoodLine, rng: random.Random,
                 q_band: tuple[float, float] = (0.7, 1.4),
                 p_band: tuple[float, float] = (0.9, 1.12)) -> GoodLine:
    q_factor = round(rng.uniform(*q_band), 3)
    p_factor = round(rng.uniform(*p_band), 3)
    qty = max(1.0, round(line.quantity * q_factor, 1))
    scale = qty / line.quantity if line.quantity else 1.0
    net = round(line.net_weight * scale, 1)
    gross = round(max(net, line.gross_weight * scale), 1)
    packages = max(1, math.ceil(line.package_count * scale))
    return GoodLine(
        source_name=line.source_name,
        trade_name=line.trade_name,
        armenian_desc=line.armenian_desc,
        hs_code=line.hs_code,
        unit=line.unit,
        origin=line.origin,
        brand=line.brand,
        material=line.material,
        quantity=qty,
        net_weight=net,
        gross_weight=gross,
        unit_price=round(line.unit_price * p_factor, 4),
        package_count=packages,
        package_type=line.package_type,
    )


def make_case(seed: Seed, index: int, rng_seed: int | None = None) -> Case:
    """One reproducible synthetic case. ``index`` names it; ``rng_seed`` drives choices."""
    rng = random.Random(rng_seed if rng_seed is not None else index)
    k = min(rng.choice(_line_counts(len(seed.pool))), len(seed.pool))
    chosen = rng.sample(seed.pool, k)
    goods = [_jitter_line(line, rng) for line in chosen]
    rng.shuffle(goods)

    dispatch = goods[0].origin or "CN"
    seller = foreign_seller(rng, dispatch)
    buyer = armenian_importer(rng)
    hauler = carrier(rng, dispatch)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return Case(
        case_id=f"case-{index:03d}",
        seller=seller,
        buyer=buyer,
        carrier=hauler,
        currency=seed.currency,
        incoterms=seed.incoterms,
        dispatch_country=dispatch,
        invoice_no=f"INV-{2026}-{rng.randint(1000, 9999)}",
        date=f"2026-{month:02d}-{day:02d}",
        goods=goods,
    )


def make_cases(seed: Seed, n: int) -> list[Case]:
    return [make_case(seed, i + 1) for i in range(n)]


def make_case_direct(seed: Seed, index: int) -> Case | None:
    """One case = the seed's real goods verbatim (no subset, no jitter), only fake parties.

    For the 1:1 path: each real declaration becomes one realistic case with its true basket
    and quantities — the honest, non-random alternative to recombination.
    """
    if not seed.pool:
        return None
    rng = random.Random(index)
    # Real basket, real order — but nudge the numbers slightly (a bit changed, not the exact shipment).
    goods = [_jitter_line(g, rng, q_band=(0.9, 1.1), p_band=(0.95, 1.05)) for g in seed.pool]
    dispatch = goods[0].origin or "CN"
    return Case(
        case_id=f"case-{index:03d}",
        seller=foreign_seller(rng, dispatch),
        buyer=armenian_importer(rng),
        carrier=carrier(rng, dispatch),
        currency=seed.currency,
        incoterms=seed.incoterms,
        dispatch_country=dispatch,
        invoice_no=f"INV-2026-{rng.randint(1000, 9999)}",
        date=f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
        goods=goods,
    )
