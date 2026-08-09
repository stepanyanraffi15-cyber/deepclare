"""Score an HS-classification run. Reads results.jsonl, writes a report. No API calls.

    python -m evals.hs_classification.score runs/hs_deepseek [--json]

WHY PRECISION AND COVERAGE, NOT ACCURACY. The classifier may abstain, and the
specification wants it to: on a legal document a wrong value is a consequential
error while a missing one is work left for a human. A single accuracy number
hides that trade — a pipeline that abstains on everything and a pipeline that
guesses on everything can score alike. So the report separates:

    precision  of the codes it DID emit, how many were right
    coverage   how often it emitted one at all
    yield      precision x coverage -- the end-to-end useful rate

and reports them at 2/4/6/10 digits, because a code wrong at the chapter is a
different failure from one wrong in the last two digits.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import pathlib
import statistics


def load(run_dir: pathlib.Path) -> tuple[list[dict], list[dict], dict]:
    # Committed runs ship compressed so the tables can be re-derived without keys.
    plain, packed = run_dir / "results.jsonl", run_dir / "results.jsonl.gz"
    if plain.exists():
        text = plain.read_text(encoding="utf-8")
    elif packed.exists():
        text = gzip.decompress(packed.read_bytes()).decode("utf-8")
    else:
        raise SystemExit(f"no results.jsonl(.gz) in {run_dir}")
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    scored = [r for r in rows if "predicted" in r]
    failed = [r for r in rows if "error" in r]
    return scored, failed, manifest


def report(run_dir: pathlib.Path, as_json: bool) -> int:
    scored, failed, manifest = load(run_dir)
    if not scored:
        print(f"no scored rows in {run_dir}")
        return 1
    attempted = len(scored) + len(failed)
    committed = [r for r in scored if not r["abstained"]]
    n, c = len(scored), len(committed)

    def hits(key: str) -> int:
        if key == "chapter":
            return sum(r["predicted"][:2] == r["gold_10"][:2] for r in committed)
        return sum(r[key] for r in committed)

    levels = [("chapter (2)", "chapter"), ("heading (4)", "correct_4"),
              ("subheading (6)", "correct_6"), ("exact (10)", "correct_10")]
    summary = {
        "run": str(run_dir),
        "manifest": manifest,
        "attempted": attempted,
        "scored": n,
        "pipeline_failures": len(failed),
        "committed": c,
        "abstained": n - c,
        "coverage": c / n,
        "levels": {
            label: {"precision": hits(key) / c, "yield": hits(key) / n,
                    "end_to_end_yield": hits(key) / attempted}
            for label, key in levels
        },
    }

    # where the wrong answers go wrong
    bad = [r for r in committed if not r["correct_10"]]
    def where(r: dict) -> str:
        if r["predicted"][:2] != r["gold_10"][:2]:
            return "chapter wrong"
        if not r["correct_4"]:
            return "heading wrong"
        if not r["correct_6"]:
            return "subheading wrong"
        return "last 4 digits wrong"
    summary["error_profile"] = dict(collections.Counter(where(r) for r in bad))
    summary["failure_profile"] = dict(collections.Counter(
        ("degenerate output" if "not JSON" in r["error"]
         else "invented figure (refused)" if "no source document states" in r["error"]
         else "schema invalid" if "not a valid" in r["error"]
         else "other") for r in failed))

    # does confidence separate right from wrong? if not, the review gate is blind.
    ok = [r["confidence"] for r in committed if r["correct_10"] and r.get("confidence") is not None]
    no = [r["confidence"] for r in committed if not r["correct_10"] and r.get("confidence") is not None]
    if ok and no:
        summary["confidence"] = {
            "median_when_correct": round(statistics.median(ok), 3),
            "median_when_wrong": round(statistics.median(no), 3),
            "separates": abs(statistics.median(ok) - statistics.median(no)) >= 0.05,
        }

    usage = collections.defaultdict(lambda: [0, 0, 0])
    for r in scored:
        for call in r.get("usage", []):
            slot = usage[(call["node"], call["model"])]
            slot[0] += 1
            slot[1] += call.get("in") or 0
            slot[2] += call.get("out") or 0
    summary["usage"] = {f"{node} {model}": {"calls": v[0], "in": v[1], "out": v[2]}
                        for (node, model), v in sorted(usage.items())}

    if as_json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    print(f"{'=' * 78}\nHS CLASSIFICATION — {run_dir}\n{'=' * 78}")
    if manifest:
        print(f"  provider {manifest.get('provider')}  models {manifest.get('models')}")
        print(f"  reasoning {manifest.get('reasoning_tiers')}  commit {manifest.get('git_commit','')[:8]}"
              f"{' (dirty)' if manifest.get('git_dirty') else ''}")
        print(f"  nomenclature {manifest.get('nomenclature_vintage','?')[:10]}  "
              f"embedding {manifest.get('embedding','?')}")
    print(f"\n  attempted {attempted}  scored {n}  pipeline failures {len(failed)}")
    print(f"  committed {c} ({c/n:.0%})   abstained {n-c} ({(n-c)/n:.0%})")
    print(f"\n  {'level':<18}{'precision':>11}{'coverage':>10}{'yield':>8}")
    for label, key in levels:
        print(f"  {label:<18}{hits(key)/c:>10.0%}{c/n:>10.0%}{hits(key)/n:>8.0%}")
    print(f"\n  where the {len(bad)} wrong answers go wrong:")
    for k, v in collections.Counter(where(r) for r in bad).most_common():
        print(f"    {v:5} ({v/max(1,len(bad)):>4.0%})  {k}")
    if failed:
        print(f"\n  the {len(failed)} pipeline failures:")
        for k, v in summary["failure_profile"].items():
            print(f"    {v:5} {k}")
    if "confidence" in summary:
        conf = summary["confidence"]
        verdict = "separates" if conf["separates"] else "DOES NOT separate — review gate is blind"
        print(f"\n  confidence: correct {conf['median_when_correct']} vs "
              f"wrong {conf['median_when_wrong']}  -> {verdict}")
    if usage:
        tin = sum(v[1] for v in usage.values())
        tout = sum(v[2] for v in usage.values())
        print(f"\n  tokens: in {tin:,}  out {tout:,}   ({tin//n:,} / {tout//n:,} per line)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=pathlib.Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    return report(args.run_dir, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
