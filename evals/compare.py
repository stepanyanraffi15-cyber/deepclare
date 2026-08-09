"""Paired comparison of two runs on the lines they both processed. No API calls.

    python -m evals.compare results/hs_gemini_tenth results/hs_deepseek_flash_baseline
    python -m evals.compare A B --full C      # add a third column scored over all of C

WHY PAIRED. Two runs over different samples are not comparable: a provider that
drew easier lines looks better for a reason that has nothing to do with it. So
this intersects on line id (`<case>:<line_id>`) and scores both sides over
exactly the same lines. `--full` adds the second run scored over its whole set,
which shows whether the intersection was a representative slice or a lucky draw.

WHY PRECISION AND COVERAGE SEPARATELY. The classifier abstains by design -- on a
legal document a wrong value is consequential where a missing one is work left
for a human. Merging the two into one accuracy number cannot distinguish a
pipeline that abstains on everything from one that guesses on everything.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import pathlib


def load(run_dir: pathlib.Path) -> dict[str, dict]:
    """results.jsonl, or results.jsonl.gz -- committed runs ship compressed."""
    plain, packed = run_dir / "results.jsonl", run_dir / "results.jsonl.gz"
    if plain.exists():
        text = plain.read_text(encoding="utf-8")
    elif packed.exists():
        text = gzip.decompress(packed.read_bytes()).decode("utf-8")
    else:
        raise SystemExit(f"no results.jsonl(.gz) in {run_dir}")
    rows = (json.loads(line) for line in text.splitlines() if line.strip())
    return {r["id"]: r for r in rows if "predicted" in r}


def stats(rows: list[dict]) -> dict:
    committed = [r for r in rows if not r["abstained"]]
    k = len(committed) or 1
    return {
        "total": len(rows),
        "committed": len(committed),
        "coverage": len(committed) / max(1, len(rows)),
        "p2": sum(r["predicted"][:2] == r["gold_10"][:2] for r in committed) / k,
        "p4": sum(r["predicted"][:4] == r["gold_10"][:4] for r in committed) / k,
        "p6": sum(r["predicted"][:6] == r["gold_10"][:6] for r in committed) / k,
        "p10": sum(r["correct_10"] for r in committed) / k,
        "hits": sum(r["correct_10"] for r in committed),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=pathlib.Path, help="first run directory")
    ap.add_argument("b", type=pathlib.Path, help="second run directory")
    ap.add_argument("--full", type=pathlib.Path,
                    help="also score this run over its entire set (usually the same as b)")
    ap.add_argument("--labels", default="", help="comma-separated column labels")
    ap.add_argument("--dump", type=pathlib.Path, help="write the per-line overlap as JSONL")
    args = ap.parse_args()

    A, B = load(args.a), load(args.b)
    shared = sorted(set(A) & set(B),
                    key=lambda i: (i.split(":")[0], int(i.split(":")[1])))
    if not shared:
        raise SystemExit("the two runs share no lines")

    labels = [s.strip() for s in args.labels.split(",")] if args.labels else \
             [args.a.name, args.b.name]
    sa, sb = stats([A[i] for i in shared]), stats([B[i] for i in shared])
    cols = [(f"{labels[0]} ({len(shared)})", sa), (f"{labels[1]} ({len(shared)})", sb)]
    if args.full:
        full = load(args.full)
        cols.append((f"{args.full.name} (full set)", stats(list(full.values()))))

    w = max(24, *(len(c[0]) + 2 for c in cols))
    print(f"{'metric':<26}" + "".join(f"{c[0]:>{w}}" for c in cols))
    print("-" * (26 + w * len(cols)))
    print(f"{'committed / total':<26}"
          + "".join(f"{f'{c[1]['committed']}/{c[1]['total']}':>{w}}" for c in cols))
    for label, key in (("coverage", "coverage"), ("precision @2 (chapter)", "p2"),
                       ("precision @4 (heading)", "p4"), ("precision @6", "p6"),
                       ("precision @10 (exact)", "p10")):
        print(f"{label:<26}" + "".join(f"{c[1][key]:>{w - 1}.0%} " for c in cols))
    print(f"{'correct answers':<26}" + "".join(f"{c[1]['hits']:>{w}}" for c in cols))

    verdicts = collections.Counter()
    for i in shared:
        a_ok, b_ok = A[i]["correct_10"], B[i]["correct_10"]
        verdicts["both correct" if a_ok and b_ok else
                 f"{labels[0]} only" if a_ok else
                 f"{labels[1]} only" if b_ok else "neither"] += 1
    print(f"\n{'verdict':<26}{'lines':>8}{'share':>8}")
    for key, count in verdicts.most_common():
        print(f"{key:<26}{count:>8}{count / len(shared):>8.0%}")

    pair = [i for i in shared if not A[i]["abstained"] and not B[i]["abstained"]]
    if pair:
        ha = sum(A[i]["correct_10"] for i in pair)
        hb = sum(B[i]["correct_10"] for i in pair)
        print(f"\nboth committed: {len(pair)} lines -> "
              f"{labels[0]} {ha}/{len(pair)}={ha / len(pair):.0%}  "
              f"{labels[1]} {hb}/{len(pair)}={hb / len(pair):.0%}")
    same = sum(1 for i in shared if A[i]["predicted"] == B[i]["predicted"])
    print(f"identical output (incl. both abstaining): {same}/{len(shared)} = {same / len(shared):.0%}")

    if args.dump:
        args.dump.parent.mkdir(parents=True, exist_ok=True)
        with args.dump.open("w", encoding="utf-8") as handle:
            for i in shared:
                a, b = A[i], B[i]
                handle.write(json.dumps({
                    "id": i, "source_name": a["source_name"], "gold_10": a["gold_10"],
                    f"{labels[0]}_pred": a["predicted"],
                    f"{labels[0]}_correct_10": a["correct_10"],
                    f"{labels[0]}_abstained": a["abstained"],
                    f"{labels[1]}_pred": b["predicted"],
                    f"{labels[1]}_correct_10": b["correct_10"],
                    f"{labels[1]}_abstained": b["abstained"],
                }, ensure_ascii=False) + "\n")
        print(f"\nper-line overlap -> {args.dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
