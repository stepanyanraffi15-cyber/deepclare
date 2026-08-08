"""evalkit — a standalone verifier for customs-declaration (ESADout_CU) output.

Compares a produced declaration XML against a ground-truth one and returns
numbers: line precision/recall/F1, exact-match on numeric fields, hierarchical
commodity-code agreement, and description quality (chrF + token-F1 + an
attribute rubric). Stdlib-only core; optional semantic / LLM-judge tiers plug in.

Typical use::

    from evalkit import parse_declaration, score_case
    case = score_case(parse_declaration(mine_xml), parse_declaration(gold_xml), "case-001")
    print(case.as_dict())
"""

from __future__ import annotations

from .align import Alignment, align, line_similarity
from .codes import CodeScore, score_code
from .parse import Declaration, Good, parse_declaration
from .rubric import RubricResult, detect_brand, score_rubric
from .score import (
    DEFAULT,
    CaseScore,
    LineScore,
    Thresholds,
    corpus_summary,
    score_case,
    score_line,
)
from .textmetrics import chrf, normalized_exact, token_f1

__all__ = [
    "Alignment",
    "CaseScore",
    "CodeScore",
    "DEFAULT",
    "Declaration",
    "Good",
    "LineScore",
    "RubricResult",
    "Thresholds",
    "align",
    "chrf",
    "corpus_summary",
    "detect_brand",
    "line_similarity",
    "normalized_exact",
    "parse_declaration",
    "score_case",
    "score_code",
    "score_line",
    "score_rubric",
    "token_f1",
]
