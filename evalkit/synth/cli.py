"""Generate a synthetic corpus from one authoritative declaration.

    python -m synth generate --seed PATH/TO/cusad.xml --n 12 --out corpus/

Each case is written as ground_truth.xml + ground_truth.json (rubric atoms) + a
human-readable ir.json. The leak scanner runs on every file before it is written;
a case that would leak a real party name is refused, never written. Invoice/CMR
PDFs are a later step (they need a PDF renderer) — this stage produces the ground
truth the whole corpus is anchored to.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict
from pathlib import Path

from .enrich import enrich_generic_names
from .guardrails import consistency, leak_scan
from .recombine import make_cases, partition, partition_by_size
from .render_xml import render_atoms, render_xml
from .seed import Seed, load_seed


def _emit_family(seed: Seed, out: Path, n: int, render_gt, docs) -> tuple[int, int]:
    out.mkdir(parents=True, exist_ok=True)
    written, refused = 0, 0
    for idx, case in enumerate(make_cases(seed, n), 1):
        xml = render_gt(case) if render_gt else render_xml(case)
        atoms = render_atoms(case)
        ir = json.dumps(asdict(case), ensure_ascii=False, indent=1, default=str)

        problems = consistency(case)
        for label, blob in (("xml", xml), ("atoms", atoms), ("ir", ir)):
            leaks = leak_scan(blob, seed.forbidden_terms)
            if leaks:
                problems.append(f"{label} leaks real term(s): {leaks}")
        if problems:
            refused += 1
            print(f"  ✗ {out.name}/{case.case_id} refused: {problems}")
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
    return written, refused


def cmd_generate(args: argparse.Namespace) -> int:
    out = Path(args.out)
    try:
        from .to_declaration_input import render_ground_truth as render_gt  # real, portal-valid
    except ImportError as exc:
        render_gt = None
        print(f"  (agent renderer unavailable — {exc}; minimal XML, NOT portal-importable)")
    docs = None
    if not args.no_docs:
        try:
            from . import render_docs as docs  # Pillow-backed; optional
        except ImportError as exc:
            print(f"  (input docs disabled — {exc}; XML/atoms only)")

    # 1:1 mode: each real declaration → one case (real goods + fake parties), names translated.
    if args.declarations:
        from .declarations import generate_one_to_one
        from .match_names import gemini_model

        w, r = generate_one_to_one(args.declarations, out, gemini_model(), args.limit, render_gt, docs)
        print(f"\nwrote {w} 1:1 case(s) to {out}/  ({r} refused)")
        return 0 if r == 0 else 1

    if args.history:
        from .history import load_history_seed

        seed = load_history_seed(args.history, args.limit)
    else:
        seed = enrich_generic_names(load_seed(Path(args.seed)))
    if args.names:
        from .enrich import apply_name_map

        seed = apply_name_map(seed, json.loads(Path(args.names).read_text(encoding="utf-8")))
    print(f"seed pool: {len(seed.pool)} goods | forbidden terms: {len(seed.forbidden_terms)}")

    # One family, or cut a big pool into coherent sub-invoice families (by count or by size).
    if args.family_size:
        families = partition_by_size(seed, args.family_size)
    elif args.partition:
        families = partition(seed, args.partition)
    else:
        families = [seed]
    multi = len(families) > 1
    total_w, total_r = 0, 0
    for i, fam in enumerate(families, 1):
        dest = out / f"part-{i:02d}" if multi else out
        w, r = _emit_family(fam, dest, args.n, render_gt, docs)
        total_w += w
        total_r += r
        label = f"part-{i:02d} ({len(fam.pool)} goods)" if multi else "family"
        print(f"  ✓ {label}: {w} case(s){f', {r} refused' if r else ''}")

    print(f"\nwrote {total_w} case(s) to {out}/  ({total_r} refused)")
    return 0 if total_r == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="synth", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="generate a synthetic corpus from a seed declaration")
    g.add_argument("--seed", help="path to an authoritative declaration XML")
    g.add_argument("--history", metavar="records.jsonl",
                   help="reverse mode: seed the goods pool from the history DB instead of a declaration")
    g.add_argument("--declarations", metavar="imported_xmls.jsonl",
                   help="1:1 mode: one case per real declaration (real goods, fake parties)")
    g.add_argument("--limit", type=int, help="cap the number of history records used")
    g.add_argument("--n", type=int, default=12, help="number of cases (default 12)")
    g.add_argument("--out", default="corpus", help="output corpus directory")
    g.add_argument("--partition", type=int, metavar="K",
                   help="cut a big seed into K coherent sub-invoice families (by HS chapter)")
    g.add_argument("--family-size", type=int, metavar="N",
                   help="cut into HS-chapter families of at most N goods (splits huge chapters)")
    g.add_argument("--names", metavar="MAP.json",
                   help="{good-index: english_name} map (from match_names) for unbranded seeds")
    g.add_argument("--no-docs", action="store_true", help="emit ground truth only (skip PDFs/XLSX)")
    g.set_defaults(func=cmd_generate)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
