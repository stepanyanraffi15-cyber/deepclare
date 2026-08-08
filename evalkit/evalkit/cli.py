"""Command-line runner: score one pair, or a whole corpus folder.

    python -m evalkit pair MINE.xml GOLD.xml [--atoms ground_truth.json]
    python -m evalkit corpus CORPUS_DIR [--mine declaration.xml] [--gold ground_truth.xml] [--json]

Corpus layout — one folder per case::

    corpus/case-001/declaration.xml     # produced output ("mine")
    corpus/case-001/ground_truth.xml    # expected declaration ("gold")
    corpus/case-001/ground_truth.json   # optional: {"goods": [{"brand","trade_name","material"}, ...]}

Exit code is non-zero if any case fails its thresholds, so it drops straight into CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .parse import parse_declaration
from .score import CaseScore, corpus_summary, score_case


def _fmt(x: float) -> str:
    return f"{x:.2f}"


def _fmt_opt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def format_case(case: CaseScore) -> str:
    r = case.rubric_rate
    lines = [
        f"{case.name} — {'PASS' if case.passed else 'FAIL'}",
        f"  lines      P={_fmt(case.line_precision)} R={_fmt(case.line_recall)} "
        f"F1={_fmt(case.line_f1)}  (mine {case.n_mine} / gold {case.n_gold})",
        f"  numeric    exact {_fmt(case.numeric_exact_rate)}   ["
        + " ".join(f"{k.split('_')[0]} {_fmt(v)}" for k, v in case.numeric_by_field.items())
        + "]",
        f"  codes      exact {_fmt(case.code_exact_rate)}   @6 {_fmt(case.code_level_rate.get(6, 0.0))}"
        f"   meanPrefix {case.mean_prefix_len:.1f}",
        f"  desc       chrF {_fmt(case.desc_chrf)}   tokF1 {_fmt(case.desc_token_f1)}"
        f"   exact {_fmt(case.desc_exact_rate)}",
        f"  rubric     brand {_fmt_opt(r['brand_retained'])}  trade {_fmt_opt(r['trade_name_present'])}"
        f"  material {_fmt_opt(r['material_stated'])}  no-hallu {_fmt_opt(r['no_hallucinated_brand'])}",
        "  totals     " + " ".join(f"{k}={'ok' if v else 'X'}" for k, v in case.totals_ok.items()),
        f"  line-pass  {_fmt(case.line_pass_rate)}"
        + (f"   (excused {case.excused_external} external)" if case.excused_external else ""),
    ]
    return "\n".join(lines)


def _read_source(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.exists() else None


def _load_atoms(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    goods = data.get("goods") if isinstance(data, dict) else data
    return goods if isinstance(goods, list) else None


def cmd_pair(args: argparse.Namespace) -> int:
    mine = parse_declaration(Path(args.mine))
    gold = parse_declaration(Path(args.gold))
    atoms = _load_atoms(Path(args.atoms)) if args.atoms else None
    source = _read_source(Path(args.source)) if args.source else None
    case = score_case(mine, gold, name=Path(args.mine).stem, atoms=atoms, source_text=source)
    if args.json:
        print(json.dumps(case.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_case(case))
    return 0 if case.passed else 1


def cmd_corpus(args: argparse.Namespace) -> int:
    root = Path(args.dir)
    cases: list[CaseScore] = []
    # Recurse: any directory (at any depth) that holds the gold file is a case — so a corpus
    # nested per seed (corpus/new_folder2/case-001/...) scores in one run.
    for folder in sorted({p.parent for p in root.rglob(args.gold)}):
        name = str(folder.relative_to(root))
        mine_p, gold_p = folder / args.mine, folder / args.gold
        if not mine_p.exists():
            print(f"— {name}: skipped (missing {args.mine})")
            continue
        atoms = _load_atoms(folder / args.atoms)
        source = _read_source(folder / args.source)
        case = score_case(
            parse_declaration(mine_p), parse_declaration(gold_p),
            name=name, atoms=atoms, source_text=source,
        )
        cases.append(case)
        if not args.json:
            print(format_case(case) + "\n")

    summary = corpus_summary(cases)
    if args.json:
        print(json.dumps({"summary": summary, "cases": [c.as_dict() for c in cases]},
                         ensure_ascii=False, indent=2))
    else:
        print("=== corpus ===")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    return 0 if all(c.passed for c in cases) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evalkit", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pair", help="score one output vs one ground-truth XML")
    p.add_argument("mine")
    p.add_argument("gold")
    p.add_argument("--atoms", help="ground_truth.json with per-line brand/trade_name/material")
    p.add_argument("--source", help="after-scan invoice/CMR text; gold values absent from it are excused")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_pair)

    c = sub.add_parser("corpus", help="score every case folder under a directory")
    c.add_argument("dir")
    c.add_argument("--mine", default="declaration.xml", help="produced-output filename per case")
    c.add_argument("--gold", default="ground_truth.xml", help="ground-truth filename per case")
    c.add_argument("--atoms", default="ground_truth.json", help="per-line atoms filename per case")
    c.add_argument("--source", default="source.txt", help="per-case after-scan source text filename")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_corpus)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
