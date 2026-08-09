"""End-to-end eval: scanned documents -> the full pipeline -> declaration XML -> evalkit.

    python -m evals.end_to_end.run --cases 3 --out runs/e2e

WHAT THIS EXERCISES that the classification eval does not: page reading from the
actual scanned PDFs (vision), role inference, spreadsheet/consignment-note
handling, description composition, classification, the consistency pass,
declaration assembly, and the filing-format adapter that emits ESADout_CU. It is
the only eval that can catch a defect in how the pieces are wired together.

SCORING IS NOT REIMPLEMENTED HERE. `evalkit` already compares a produced
declaration against a ground-truth one with the right metric per field type --
exact for numerics, hierarchical for codes, chrF plus an attribute rubric for
descriptions -- and exits non-zero when a case misses its thresholds. This module
only *produces* the XML and stages it where evalkit expects to find it:

    <out>/case-NNN/declaration.xml     what the pipeline produced
    <out>/case-NNN/ground_truth.xml    copied from the corpus
    <out>/case-NNN/ground_truth.json   per-line atoms, when the case has them

then runs `python -m evalkit corpus <out>`.

DELIBERATELY SMALL. Each case is a full vision run over multi-page scans, so this
is minutes and real money per case, not seconds. It answers "is the chain intact
and roughly right", while the classification eval answers "how good is the code".
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORPUS = ROOT / "evalkit" / "corpus" / "oneToOne"


def stage_case(case: pathlib.Path, dest: pathlib.Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("ground_truth.xml", "ground_truth.json"):
        src = case / name
        if src.exists():
            shutil.copy2(src, dest / name)


def run_case(case: pathlib.Path, dest: pathlib.Path, timeout: int,
             env: dict[str, str] | None = None) -> dict:
    """Invoke the product's own CLI, so the eval tests what ships."""
    invoice = case / "invoice.pdf"
    cmr = case / "cmr.pdf"
    cmd = [sys.executable, "-m", "deepclare", "run", str(invoice), "--out", str(dest)]
    if cmr.exists():
        cmd += ["--consignment-note", str(cmr)]

    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          cwd=ROOT, env=env)
    elapsed = round(time.time() - started, 1)

    produced = sorted(dest.glob("*.xml"))
    produced = [p for p in produced if p.name != "ground_truth.xml"]
    # evalkit's corpus command looks for a fixed filename per case.
    if produced and not (dest / "declaration.xml").exists():
        shutil.copy2(produced[0], dest / "declaration.xml")

    return {
        "case": case.name,
        "returncode": proc.returncode,
        "elapsed_s": elapsed,
        "produced_xml": (dest / "declaration.xml").exists(),
        "stderr_tail": proc.stderr.strip()[-600:] if proc.returncode else "",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=3, help="how many corpus cases to run")
    ap.add_argument("--case-ids", default="", help="comma-separated ids, overrides --cases")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "runs" / "e2e")
    ap.add_argument("--timeout", type=int, default=1800, help="per-case seconds")
    ap.add_argument("--skip-score", action="store_true")
    ap.add_argument("--allow-gemini", action="store_true",
                    help="required: this eval runs the full product pipeline, whose "
                         "vision and generation stages are all billed to Google.")
    ap.add_argument("--qdrant-path", default="",
                    help="point at a COPY of the collection. Local Qdrant is "
                         "single-process, so this eval cannot share data/qdrant_exim "
                         "with a concurrently running classification sweep.")
    args = ap.parse_args()
    # evalkit runs with cwd=evalkit/, so a relative --out would resolve there.
    args.out = args.out.resolve()
    if not args.allow_gemini:
        raise SystemExit(
            "REFUSING: the end-to-end pipeline runs entirely on Gemini (vision, "
            "reading, description, classification). Pass --allow-gemini to spend "
            "Google credits."
        )

    if args.case_ids:
        chosen = [CORPUS / c.strip() for c in args.case_ids.split(",") if c.strip()]
    else:
        # Smallest cases first: this eval is about whether the chain holds, and a
        # 554-line invoice would spend an hour proving the same thing as a 4-line one.
        by_size = sorted(
            CORPUS.glob("case-*"),
            key=lambda p: len(json.loads((p / "ir.json").read_text())["goods"]),
        )
        chosen = by_size[: args.cases]

    args.out.mkdir(parents=True, exist_ok=True)
    from evals.common.manifest import build, write

    from deepclare.config import load_settings
    settings = load_settings()
    write(args.out / "manifest.json", build(
        eval_name="end_to_end",
        provider="gemini",
        models={"cheap": settings.genai_model_cheap,
                "standard": settings.genai_model_standard,
                "strong": settings.genai_model_strong},
        extra={"cases": [c.name for c in chosen],
               "line_counts": {c.name: len(json.loads((c / "ir.json").read_text())["goods"])
                               for c in chosen},
               "scored_by": "evalkit corpus"},
    ))

    import os
    child_env = dict(os.environ)
    if args.qdrant_path:
        child_env["QDRANT_PATH"] = args.qdrant_path

    print(f"running {len(chosen)} case(s): {', '.join(c.name for c in chosen)}\n")
    outcomes = []
    for case in chosen:
        dest = args.out / case.name
        stage_case(case, dest)
        print(f"  {case.name} ...", flush=True)
        try:
            outcome = run_case(case, dest, args.timeout, child_env)
        except subprocess.TimeoutExpired:
            outcome = {"case": case.name, "returncode": -1, "elapsed_s": args.timeout,
                       "produced_xml": False, "stderr_tail": "timed out"}
        outcomes.append(outcome)
        status = "ok" if outcome["produced_xml"] else "NO XML"
        print(f"    {status}  exit {outcome['returncode']}  {outcome['elapsed_s']}s")
        if outcome["stderr_tail"]:
            print(f"    stderr: {outcome['stderr_tail'][:300]}")

    (args.out / "run_log.json").write_text(json.dumps(outcomes, indent=2))
    produced = sum(o["produced_xml"] for o in outcomes)
    print(f"\n{produced}/{len(outcomes)} cases produced a declaration")

    if args.skip_score or not produced:
        if not produced:
            print("nothing to score")
            return 1
        return 0

    print(f"\n{'=' * 78}\nevalkit\n{'=' * 78}")
    scored = subprocess.run(
        [sys.executable, "-m", "evalkit", "corpus", str(args.out)],
        cwd=ROOT / "evalkit", capture_output=True, text=True,
    )
    print(scored.stdout or scored.stderr)
    return scored.returncode


if __name__ == "__main__":
    raise SystemExit(main())
