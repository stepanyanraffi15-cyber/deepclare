"""1:1 seeding — each real declaration becomes one case (real goods, fake parties).

The honest, non-random alternative to recombination: instead of shuffling goods into
invented baskets, take each real filed declaration as it is — its true goods, quantities,
and weights — and only invent the parties. The English invoice names are translated from
the Armenian descriptions (brand kept in the Model column); the output declaration is
re-rendered from the real goods + fake declarant, so no real party ever leaks.

Reads the org-wide imported declarations (`data/imported_xmls.jsonl`, one XML per line).
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict
from pathlib import Path

from .enrich import apply_name_map
from .guardrails import consistency, leak_scan
from .history import derive_english_names
from .recombine import make_case_direct
from .render_xml import render_atoms, render_xml
from .seed import Seed, load_seed


def iter_declaration_seeds(jsonl_path: str | Path, limit: int | None = None, min_goods: int = 1):
    """Yield one Seed per real declaration with >= min_goods goods (in file order)."""
    count = 0
    for line in Path(jsonl_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if limit and count >= limit:
            break
        try:
            xml = json.loads(line).get("xml")
            seed = load_seed(xml) if xml else None
        except Exception:  # skip a malformed record, never crash the batch
            continue
        if seed and len(seed.pool) >= min_goods:
            count += 1
            yield seed


def generate_one_to_one(jsonl_path, out_dir, model=None, limit=None, render_gt=None, docs=None,
                        min_goods=1, names_by_decl=None):
    """Generate 1:1 cases from real declarations. Returns (written, refused).

    names_by_decl: optional list of {pool-index: english_name} per declaration (same order),
    to reuse already-reviewed translations instead of re-deriving them.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written, refused = 0, 0
    for idx, seed in enumerate(iter_declaration_seeds(jsonl_path, limit, min_goods), 1):
        if names_by_decl is not None:
            seed = apply_name_map(seed, names_by_decl[idx - 1])
        else:
            seed = _named(seed, model)
        case = make_case_direct(seed, idx)
        if case is None:
            continue
        xml = render_gt(case) if render_gt else render_xml(case)
        atoms = render_atoms(case)
        ir = json.dumps(asdict(case), ensure_ascii=False, indent=1, default=str)

        problems = consistency(case)
        for label, blob in (("xml", xml), ("atoms", atoms), ("ir", ir)):
            if leak_scan(blob, seed.forbidden_terms):
                problems.append(f"{label} leaks a real term")
        if problems:
            refused += 1
            print(f"  ✗ {case.case_id} refused: {problems[:1]}")
            continue

        folder = out / case.case_id
        folder.mkdir(exist_ok=True)
        (folder / "ground_truth.xml").write_text(xml, encoding="utf-8")
        (folder / "ground_truth.json").write_text(atoms, encoding="utf-8")
        (folder / "ir.json").write_text(ir, encoding="utf-8")
        if docs is not None:
            (folder / "invoice.pdf").write_bytes(docs.render_invoice_pdf(case, random.Random(1000 + idx)))
            (folder / "cmr.pdf").write_bytes(docs.render_cmr_pdf(case, random.Random(2000 + idx)))
            (folder / "invoice.xlsx").write_bytes(docs.render_invoice_xlsx(case))
        written += 1
        print(f"  ✓ {case.case_id}: {len(case.goods)} lines")
    return written, refused


def _named(seed: Seed, model) -> Seed:
    """Translate each good's description into its English invoice name."""
    return apply_name_map(seed, derive_english_names(seed, model))
