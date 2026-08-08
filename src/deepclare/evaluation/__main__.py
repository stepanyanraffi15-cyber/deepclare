"""Runnable entry point for the evaluation harness.

    python -m deepclare.evaluation CORPUS_DIR --from-file ground_truth.xml --cases 10

The `--from-file` mode scores an XML file each case already holds. Pointed at each
case's own ground truth it is the harness's self-check and every figure must come out
perfect; pointed at `declaration.xml` it scores whatever a previous run wrote there.

The pipeline mode is not wired here. Producing a declaration is a parameter of
`score_corpus` — a callable taking the case's input paths and returning XML — so the
run graph plugs in without this file learning anything about it.

Exit codes: 0 every selected case scored, 1 a case produced nothing, 2 the environment
or the corpus could not be read.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import ModuleType

from deepclare.classification.features import ClassificationFeatures
from deepclare.config import ConfigurationError, load_settings
from deepclare.evaluation.cases import CorpusError, discover_cases, select
from deepclare.evaluation.harness import score_corpus
from deepclare.evaluation.manifest import Production, build_manifest
from deepclare.evaluation.producers import emitted_file
from deepclare.evaluation.render import render_report
from deepclare.evaluation.scorer import ScorerUnavailableError, bind_scorer, scorer_root
from deepclare.models import Decoding
from deepclare.reference.store import ArtifactUnavailableError


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)

    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(exc, file=sys.stderr)
        return 2

    try:
        root = scorer_root(Path(args.corpus), args.scorer)
        scorer = bind_scorer(root)
        cases = discover_cases(Path(args.corpus))
        selection = select(cases, args.cases)
        manifest = build_manifest(
            settings=settings,
            production=Production.PRE_EMITTED,
            producer=f"read from {args.from_file!r} in each case directory",
            corpus_dir=Path(args.corpus),
            scorer_dir=root,
            features=ClassificationFeatures(),
            decoding=Decoding(max_output_tokens=settings.genai_max_output_tokens),
            scoring_thresholds=_thresholds(scorer),
        )
    except (CorpusError, ScorerUnavailableError, ArtifactUnavailableError) as exc:
        print(exc, file=sys.stderr)
        return 2

    report = score_corpus(
        selection=selection,
        produce=emitted_file(args.from_file),
        scorer=scorer,
        manifest=manifest,
    )

    if args.json:
        text = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    else:
        text = render_report(report)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"written to {args.out}", file=sys.stderr)
    else:
        print(text)

    return 0 if report.complete else 1


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m deepclare.evaluation",
        description="Score produced declarations against a corpus of ground truth.",
    )
    parser.add_argument("corpus", help="corpus directory; cases are found recursively")
    parser.add_argument(
        "--from-file",
        default="declaration.xml",
        help=(
            "score this XML file from each case directory instead of running the "
            "pipeline. Use ground_truth.xml for the harness's own self-check."
        ),
    )
    parser.add_argument(
        "--cases",
        type=int,
        default=None,
        help="score only the first N cases in name order (a prefix, not a sample)",
    )
    parser.add_argument(
        "--scorer",
        type=Path,
        default=None,
        help="directory holding the evalkit package; found above the corpus by default",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--out", help="write the report to this path instead of stdout")
    return parser.parse_args(argv)


def _thresholds(scorer: ModuleType) -> dict[str, float | bool]:
    """The scorer's own pass thresholds, pinned into the report that used them."""
    default = scorer.DEFAULT
    return {
        "numeric_eps": default.numeric_eps,
        "numeric_rel": default.numeric_rel,
        "chrf_min": default.chrf_min,
        "require_code_exact": default.require_code_exact,
        "require_rubric": default.require_rubric,
    }


if __name__ == "__main__":
    raise SystemExit(main())
