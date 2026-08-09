"""Manual check: can flat top-k retrieval find the gold code without narrowing?

Makes real embedding calls (NOT collected by pytest). Run by hand:

    .venv/bin/python -m evals.hs_classification.retrieval_recall [--lines 300] [--with-m8]

THE QUESTION. The shipped classifier narrows to a chapter and heading before it searches.
The alternative is to search all 13,279 leaves flat and let a model pick from the top-k.
Whether that can work at all is decided by one number: if the gold code is not among the
top-k, no picker can recover it. That is measurable with embeddings alone.

THE SHAPE MATTERS. `reference/index.py` records a symmetry contract -- every leaf was
embedded as an English `<chapter> — <heading> — <leaf>` phrase, because ~3 in 10 leaf
names are literally "other" and mean nothing alone. Their measurement: a query in that
form scores 0.84 against the correct leaf where a plain English phrase scores 0.65. So
"just embed the invoice line" is the 0.65 case, and the arms below separate the two.

ARMS
  raw-en      the invoice line verbatim -- the literal "just embed the input"
  gold-hy     the corpus's filed Armenian description
  shaped-en   chapter/heading/leaf text of the GOLD code, joined per the contract.
              It uses the answer, so it is not deployable -- it is the ceiling any
              query writer could reach, which is the number that decides the design.
  written-hy  M8's Armenian (needs generation calls; --with-m8 only)
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
from decimal import Decimal

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

import qdrant_client

from deepclare.config import load_settings
from deepclare.embedding import GeminiEmbedder
from deepclare.reference.store import NomenclatureStore

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORPUS = ROOT / "evalkit" / "corpus" / "oneToOne"

# Confirmed absent from the live tariff: unreachable labels, not misses.
FABRICATED = {"39069090090", "39100000090", "39269097098"}
KS = (1, 10, 30, 100)


def sample(n: int) -> list[dict]:
    """Round-robin across cases -- case-001 is all automotive-electrical and would
    flatter or punish any strategy for the wrong reason."""
    per_case = []
    for case in sorted(CORPUS.glob("case-*")):
        goods = json.loads((case / "ir.json").read_text())["goods"]
        per_case.append([g for g in goods if g["hs_code"] not in FABRICATED])
    out, depth = [], 0
    while len(out) < n and any(len(c) > depth for c in per_case):
        for lines in per_case:
            if depth < len(lines) and len(out) < n:
                out.append(lines[depth])
        depth += 1
    return out


def shaped_en(store: NomenclatureStore, code10: str) -> str | None:
    """Mirror reference.index.embedding_text() for the gold code."""
    leaf = store.entry(code10)
    if leaf is None:
        return None
    chapter = store.entry(code10[:2])
    heading = store.entry(code10[:4])
    parts = [
        (e.name_en or e.name_hy or e.code).strip().rstrip(":").strip()
        for e in (chapter, heading, leaf)
        if e is not None
    ]
    return " — ".join(dict.fromkeys(parts))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=int, default=300)
    ap.add_argument("--with-m8", action="store_true", help="add the M8 arm (generation calls)")
    args = ap.parse_args()

    settings = load_settings()
    client = qdrant_client.QdrantClient(path=str(settings.qdrant_path))
    store = NomenclatureStore(
        artifact_dir=settings.reference_dir,
        qdrant_client=client,
        collection=settings.qdrant_collection,
        embedder=GeminiEmbedder(settings),
    )

    rows = sample(args.lines)
    for g in rows:
        g["_want"] = g["hs_code"][:-1]
        g["_shaped"] = shaped_en(store, g["_want"])
    missing = [g for g in rows if g["_shaped"] is None]
    if missing:
        print(f"WARNING {len(missing)} gold codes absent from the store; dropped")
        rows = [g for g in rows if g["_shaped"] is not None]

    arms = {"raw-en": lambda g: g["source_name"],
            "gold-hy": lambda g: g["armenian_desc"],
            "shaped-en": lambda g: g["_shaped"]}

    if args.with_m8:
        from deepclare.description import DescriptionWriter, build_line_contexts
        from deepclare.domain import (
            InvoiceGoodsLine, InvoiceRecord, Provenance, Traced, ValueOrigin,
        )
        from deepclare.models import GenerativeModel
        prov = Provenance(origin=ValueOrigin.EXTRACTED, source_document_id="invoice")
        with GenerativeModel(settings) as model:
            writer = DescriptionWriter(model, settings.prompts_dir)
            record = InvoiceRecord(source_document_id="invoice", goods_lines=tuple(
                InvoiceGoodsLine(
                    line_id=str(i + 1),
                    description=Traced[str](value=g["source_name"], provenance=prov),
                    unit=Traced[str](value=str(g["unit"]), provenance=prov),
                    unit_price=Traced[Decimal](value=Decimal(str(g["unit_price"])), provenance=prov),
                ) for i, g in enumerate(rows)))
            for g, ctx in zip(rows, build_line_contexts(record, ())):
                g["_m8"] = writer.write(ctx).description_hy
        arms["written-hy"] = lambda g: g["_m8"]

    print("=" * 96)
    print("SAMPLE QUERIES (check shaped-en against the contract in reference/index.py)")
    print("=" * 96)
    for g in rows[:3]:
        print(f"  gold {g['_want']}")
        for name, fn in arms.items():
            print(f"    {name:11} {str(fn(g))[:78]}")

    # Sanity: scoped to the gold heading, the gold leaf should rank near the top.
    probe = rows[0]
    scoped = store.search(probe["_shaped"], prefixes=[probe["_want"][:4]], limit=10)
    ranks = [c.code for c in scoped.candidates]
    pos = ranks.index(probe["_want"]) + 1 if probe["_want"] in ranks else None
    print(f"\nsanity: gold {probe['_want']} scoped to heading {probe['_want'][:4]} "
          f"-> rank {pos or 'NOT FOUND (vectors and tree may disagree)'} of {len(ranks)}")

    print(f"\nsweeping {len(rows)} lines x {len(arms)} arms ...")
    hits = {a: {k: 0 for k in KS} for a in arms}
    found_any: set[int] = set()
    for i, g in enumerate(rows):
        for name, fn in arms.items():
            text = fn(g)
            if not text:
                continue
            outcome = store.search(text, prefixes=None, limit=max(KS))
            codes = [c.code for c in outcome.candidates]
            if g["_want"] in codes:
                found_any.add(i)
                rank = codes.index(g["_want"]) + 1
                for k in KS:
                    if rank <= k:
                        hits[name][k] += 1
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(rows)}")

    n = len(rows)
    print(f"\n{'=' * 96}\nUNSCOPED RECALL over {n} lines ({len(set(g['_want'] for g in rows))} distinct codes)\n{'=' * 96}")
    print(f"  {'arm':<12}" + "".join(f"@{k:<9}" for k in KS))
    for name in arms:
        print(f"  {name:<12}" + "".join(f"{hits[name][k]/n:<10.0%}" for k in KS))
    dead = n - len(found_any)
    print(f"\n  retrieval-dead (no arm found it at {max(KS)}): {dead}/{n} = {dead/n:.0%}")
    if dead:
        print("  examples:")
        for i, g in enumerate(rows):
            if i not in found_any:
                print(f"    {g['_want']}  {g['source_name'][:52]}")
                if sum(1 for j, _ in enumerate(rows) if j not in found_any and j <= i) >= 6:
                    break


if __name__ == "__main__":
    main()
