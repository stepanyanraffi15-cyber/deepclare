"""Run the corpus: produce a declaration per case, score it, roll the numbers up.

The scoring is the vendored scorer's, in full. What is added here is the part it does not
do: holding a bucket of goods lines out of the aggregate because no correct answer for
them exists, weighting the roll-up by line rather than by case, and reporting commodity-
code agreement at every digit depth rather than as one exact-match rate.

One invariant this module depends on and checks rather than assumes: the scorer builds
exactly one line score per aligned pair, in the order of the pairs. That is what lets a
line score be joined back to the labelled goods line it came from, which is what makes
the unresolvable-label bucket possible at all. The join is zipped strictly, so a change
in the scorer raises here instead of silently pairing the wrong rows.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import ModuleType
from typing import Any

from deepclare.evaluation.cases import CaseInputs, CaseSelection
from deepclare.evaluation.corpus_facts import (
    CODES_ABSENT_FROM_NOMENCLATURE,
    CODES_ABSENT_PROVENANCE,
    DESCRIPTION_LANGUAGE_CAVEAT,
    SYNTHETIC_LABEL_CAVEAT,
)
from deepclare.evaluation.manifest import RunManifest
from deepclare.evaluation.producers import DeclarationProducer
from deepclare.evaluation.report import (
    CODE_LEVELS,
    Aggregates,
    CaseFailure,
    CaseOutcome,
    EvaluationReport,
    LineOutcome,
    aggregate,
)


def score_corpus(
    *,
    selection: CaseSelection,
    produce: DeclarationProducer,
    scorer: ModuleType,
    manifest: RunManifest,
    unresolvable_codes: frozenset[str] = CODES_ABSENT_FROM_NOMENCLATURE,
    unresolvable_provenance: str = CODES_ABSENT_PROVENANCE,
) -> EvaluationReport:
    """Score every selected case and return the report.

    A case whose producer raises is recorded as a failure and the run continues: on a
    corpus where each case is a full pipeline run, losing seventy results to the
    seventy-first is worse than reporting seventy with the seventy-first named. It is
    recorded, not swallowed — the report lists it and refuses to call itself complete.
    """
    started = time.monotonic()
    outcomes: list[CaseOutcome] = []
    failures: list[CaseFailure] = []

    for case in selection.cases:
        try:
            outcomes.append(_score_case(case, produce, scorer, unresolvable_codes))
        except Exception as exc:  # noqa: BLE001 — recorded and reported, never hidden
            failures.append(
                CaseFailure(name=case.name, error_type=type(exc).__name__, error=str(exc))
            )

    aggregates: Aggregates = aggregate(outcomes, unresolvable_codes, unresolvable_provenance)
    return EvaluationReport(
        manifest=manifest,
        selection_rule=selection.rule,
        cases_available=selection.available,
        aggregates=aggregates,
        cases=tuple(outcomes),
        failures=tuple(failures),
        caveats=(SYNTHETIC_LABEL_CAVEAT, DESCRIPTION_LANGUAGE_CAVEAT),
        seconds=time.monotonic() - started,
    )


def _score_case(
    case: CaseInputs,
    produce: DeclarationProducer,
    scorer: ModuleType,
    unresolvable_codes: frozenset[str],
) -> CaseOutcome:
    started = time.monotonic()

    produced_xml = produce(case)
    mine = scorer.parse_declaration(produced_xml)
    gold = scorer.parse_declaration(Path(case.ground_truth_xml))

    alignment = scorer.align(list(mine.goods), list(gold.goods))
    scored = scorer.score_case(
        mine, gold, name=case.name, atoms=case.atoms(), alignment=alignment
    )

    lines = [
        _line_outcome(case.name, pair, line, mine, gold, unresolvable_codes)
        for pair, line in zip(alignment.pairs, scored.lines, strict=True)
    ]
    missed_unresolvable = sum(
        1
        for index in alignment.unmatched_gold
        if digits(gold.goods[index].hs_code) in unresolvable_codes
    )

    return CaseOutcome(
        name=case.name,
        produced_lines=len(mine.goods),
        gold_lines=len(gold.goods),
        matched=len(alignment.pairs),
        invented=len(alignment.unmatched_mine),
        missed=len(alignment.unmatched_gold),
        missed_unresolvable=missed_unresolvable,
        totals_ok=dict(scored.totals_ok),
        passed=scored.passed,
        seconds=time.monotonic() - started,
        lines=tuple(lines),
    )


def _line_outcome(
    case_name: str,
    pair: tuple[int, int, float],
    line: Any,
    mine: Any,
    gold: Any,
    unresolvable_codes: frozenset[str],
) -> LineOutcome:
    """`line`, `mine` and `gold` are the bound scorer's own types — a LineScore and two
    Declarations. They are `Any` because the scorer is imported at run time from a
    directory the caller names, so there is no static import to annotate against."""
    mine_index, gold_index, similarity = pair
    gold_code = digits(gold.goods[gold_index].hs_code)
    produced_code = digits(mine.goods[mine_index].hs_code)
    return LineOutcome(
        case=case_name,
        gold_index=gold_index,
        similarity=similarity,
        gold_code=gold_code,
        produced_code=produced_code,
        code_exact=line.code_exact,
        code_prefix_len=line.code_prefix_len,
        agrees_at={level: bool(line.code_levels.get(level, False)) for level in CODE_LEVELS},
        numeric_exact=dict(line.numeric),
        unit_exact=line.unit_exact,
        origin_exact=line.origin_exact,
        desc_chrf=line.desc_chrf,
        desc_token_f1=line.desc_token_f1,
        desc_exact=line.desc_exact,
        rubric=dict(line.rubric),
        unresolvable_label=gold_code in unresolvable_codes,
        passed=line.passed,
    )


def digits(code: str) -> str:
    """The comparable form of a code: its digits, in order, and nothing else."""
    return "".join(character for character in code if character.isdigit())
