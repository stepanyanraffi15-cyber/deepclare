"""Per-seed enrichment: the generic invoice product name for each model.

The declaration only holds the Armenian text (with the model embedded); the invoice
prints a GENERIC product column (e.g. "CELLULOSE ETHER") separately from the MODEL
column (e.g. "MEILOSE GMC 3112D"). Those generic names come from the invoice scan.

For new_folder2 they are transcribed from the scan in logs/agent.log (product
categories — not private data). Lines absent from the map keep their trade name as
the product cell. Other seeds get their own map (from a fresh scan when we add them).
"""

from __future__ import annotations

from dataclasses import replace

from .seed import Seed

# Generic invoice product name keyed by trade name — new_folder2 (from the log scan).
GENERIC_BY_TRADE: dict[str, str] = {
    "ACTICIDE LA 1209": "BIOCIDE PRESERVATIVE",
    "DERFOAM LDR": "DEFOAMER ADDITIVE BASED ON MINERAL OIL",
    "MEILOSE GMC 3112D": "CELLULOSE ETHER",
    "MEILOSE GMC 3110": "CELLULOSE ETHER",
    "DERFIBER 330": "CELLULOSE ETHER",
    "DERKIM GPR 12": "MELAMINE RESIN",
    "HISA A2388 N": "CHEMICAL ADDITIVE FOR PAINTS",
}
# Unbranded lines (no trade name) keyed by HS code.
GENERIC_BY_HS: dict[str, str] = {
    "29151200000": "FORMIC ACID SALTS",
}


def apply_name_map(seed: Seed, name_map: dict) -> Seed:
    """Set each good's invoice `source_name` from a {good-index: english_name} map.

    The English name is the product description. A branded good keeps its brand as the
    Model column (two-column line: "Pasteurized cream 50% | NOVBAR"); an unbranded good
    clears trade_name (single column). Goods without a mapped name keep what they had.
    """
    pool = []
    for i, line in enumerate(seed.pool):
        name = name_map.get(str(i), name_map.get(i))
        if name:
            pool.append(replace(line, source_name=name, trade_name=line.trade_name if line.brand else None))
        else:
            pool.append(line)
    return Seed(pool=pool, forbidden_terms=seed.forbidden_terms, currency=seed.currency,
                incoterms=seed.incoterms)


def enrich_generic_names(seed: Seed, mapping: dict[str, str] | None = None) -> Seed:
    """Fill each pool line's `source_name` with its generic invoice product name."""
    trade_map = mapping or GENERIC_BY_TRADE
    pool = []
    for line in seed.pool:
        generic = None
        if line.trade_name and line.trade_name in trade_map:
            generic = trade_map[line.trade_name]
        elif line.hs_code in GENERIC_BY_HS:
            generic = GENERIC_BY_HS[line.hs_code]
        pool.append(replace(line, source_name=generic) if generic else line)
    return Seed(pool=pool, forbidden_terms=seed.forbidden_terms, currency=seed.currency, incoterms=seed.incoterms)
