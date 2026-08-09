"""Roll per-field metrics up into per-line, per-case, and per-corpus scorecards.

The contract, by field type:
  * numeric (qty, weights, value, packages) — exact within a tolerance; the abs
    error is kept so a rounding blip is visibly distinct from a real error;
  * codes — exact plus hierarchical agreement (see ``codes``);
  * enums (unit, origin, currency) — exact after normalisation;
  * descriptions — chrF + token-F1 + the attribute rubric (see ``rubric``).

A line "passes" when every numeric field is exact, the code is exact, chrF clears
a floor, and no rubric check is violated. A case passes when its line F1 is 1.0
and every matched line passes. Everything is a number; nothing here needs a human.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .align import Alignment, align
from .codes import LEVELS, score_code
from .grounding import Source
from .parse import Declaration, Good
from .rubric import RubricResult, score_rubric
from .textmetrics import chrf, normalized_exact, token_f1

NUMERIC_FIELDS: tuple[str, ...] = (
    "quantity",
    "net_weight",
    "gross_weight",
    "invoiced_cost",
)


@dataclass(frozen=True)
class Thresholds:
    numeric_eps: float = 0.01
    numeric_rel: float = 1e-4
    chrf_min: float = 0.60
    require_code_exact: bool = True
    require_rubric: bool = True


DEFAULT = Thresholds()


def _num_equal(a: float | None, b: float | None, th: Thresholds) -> tuple[bool, float | None]:
    if a is None and b is None:
        return True, None
    if a is None or b is None:
        return False, None
    err = abs(a - b)
    tol = max(th.numeric_eps, th.numeric_rel * max(abs(a), abs(b)))
    return err <= tol, err


@dataclass(frozen=True)
class LineScore:
    gold_numeric: int | None
    numeric: dict[str, bool]  # field -> exact
    numeric_error: dict[str, float | None]
    unit_exact: bool
    origin_exact: bool
    code_exact: bool
    code_prefix_len: int
    code_levels: dict[int, bool]
    desc_chrf: float
    desc_token_f1: float
    desc_exact: bool
    rubric: dict[str, bool | None]
    excused: tuple[str, ...]  # gold values not in the source scan → external, not our miss
    passed: bool


def score_line(
    mine: Good,
    gold: Good,
    atoms: dict | None = None,
    th: Thresholds = DEFAULT,
    source: Source | None = None,
) -> LineScore:
    source = source or Source(None)
    numeric: dict[str, bool] = {}
    numeric_error: dict[str, float | None] = {}
    excused: list[str] = []
    for name in NUMERIC_FIELDS:
        ok, err = _num_equal(getattr(mine, name), getattr(gold, name), th)
        numeric[name] = ok
        numeric_error[name] = err
        if not ok and not source.has_number(getattr(gold, name)):
            excused.append(name)  # gold has a value the scan never carried

    code = score_code(mine.hs_code, gold.hs_code)
    unit_exact = (mine.unit or "") == (gold.unit or "")
    origin_exact = (mine.origin or "") == (gold.origin or "")
    if not origin_exact and not source.has_text(gold.origin):
        excused.append("origin")
    if not unit_exact and not source.has_text(gold.unit):
        excused.append("unit")
    r_chrf = chrf(mine.description, gold.description)
    atoms = atoms or {}
    rubric: RubricResult = score_rubric(
        mine.description,
        gold.description,
        brand=atoms.get("brand"),
        trade_name=atoms.get("trade_name"),
        material=atoms.get("material"),
    )
    rubric_d = rubric.as_dict()

    passed = (
        all(numeric[f] or f in excused for f in NUMERIC_FIELDS)
        and (code.exact or not th.require_code_exact)
        and r_chrf >= th.chrf_min
        and (not th.require_rubric or all(v for v in rubric_d.values() if v is not None))
    )
    return LineScore(
        gold_numeric=gold.numeric,
        numeric=numeric,
        numeric_error=numeric_error,
        unit_exact=unit_exact,
        origin_exact=origin_exact,
        code_exact=code.exact,
        code_prefix_len=code.prefix_len,
        code_levels=code.levels,
        desc_chrf=r_chrf,
        desc_token_f1=token_f1(mine.description, gold.description),
        desc_exact=normalized_exact(mine.description, gold.description),
        rubric=rubric_d,
        excused=tuple(excused),
        passed=passed,
    )


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _rate(flags: list[bool]) -> float:
    return sum(1 for f in flags if f) / len(flags) if flags else 1.0


def _rate_opt(flags: list[bool]) -> float | None:
    """Like ``_rate`` but None when there was nothing to assert (vs. a false 1.0)."""
    return sum(1 for f in flags if f) / len(flags) if flags else None


@dataclass
class CaseScore:
    name: str
    line_precision: float
    line_recall: float
    line_f1: float
    n_mine: int
    n_gold: int
    numeric_exact_rate: float
    numeric_by_field: dict[str, float]
    unit_exact_rate: float
    origin_exact_rate: float
    code_exact_rate: float
    code_level_rate: dict[int, float]
    mean_prefix_len: float
    desc_chrf: float
    desc_token_f1: float
    desc_exact_rate: float
    rubric_rate: dict[str, float | None]
    line_pass_rate: float
    totals_ok: dict[str, bool]
    excused_external: int = 0  # gold field-values absent from the source scan (not our miss)
    lines: list[LineScore] = field(default_factory=list)
    passed: bool = False

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "line_f1": round(self.line_f1, 4),
            "line_precision": round(self.line_precision, 4),
            "line_recall": round(self.line_recall, 4),
            "numeric_exact_rate": round(self.numeric_exact_rate, 4),
            "code_exact_rate": round(self.code_exact_rate, 4),
            "code@6_rate": round(self.code_level_rate.get(6, 0.0), 4),
            "desc_chrf": round(self.desc_chrf, 4),
            "desc_token_f1": round(self.desc_token_f1, 4),
            "rubric_rate": {
                k: (round(v, 4) if v is not None else None) for k, v in self.rubric_rate.items()
            },
            "line_pass_rate": round(self.line_pass_rate, 4),
            "excused_external": self.excused_external,
            "totals_ok": self.totals_ok,
            "passed": self.passed,
        }


def score_case(
    mine: Declaration,
    gold: Declaration,
    name: str = "case",
    atoms: list[dict] | None = None,
    th: Thresholds = DEFAULT,
    alignment: Alignment | None = None,
    source_text: str | None = None,
) -> CaseScore:
    """Align lines, score matched pairs, and aggregate into one scorecard.

    `source_text` (the after-scan invoice/CMR text) excuses gold values it does not
    contain — those are external info the broker adds, not a pipeline miss. Omit it and
    every field is treated as attributable (strict).
    """
    alignment = alignment or align(list(mine.goods), list(gold.goods))
    source = Source(source_text)
    line_scores = [
        score_line(mine.goods[i], gold.goods[j], atoms[j] if atoms else None, th, source)
        for i, j, _ in alignment.pairs
    ]

    numeric_by_field = {
        f: _rate([ls.numeric[f] for ls in line_scores]) for f in NUMERIC_FIELDS
    }
    numeric_exact_rate = _mean(list(numeric_by_field.values()))
    code_level_rate = {
        lvl: _rate([ls.code_levels.get(lvl, False) for ls in line_scores]) for lvl in LEVELS
    }
    rubric_rate = {
        key: _rate_opt([ls.rubric[key] for ls in line_scores if ls.rubric[key] is not None])
        for key in ("brand_retained", "trade_name_present", "material_stated", "no_hallucinated_brand")
    }
    totals_ok = {
        "goods_count": (mine.total_goods or len(mine.goods)) == (gold.total_goods or len(gold.goods)),
        "packages": _num_equal(mine.total_packages, gold.total_packages, th)[0],
        "cost": _num_equal(mine.total_cost, gold.total_cost, th)[0],
        "currency": (mine.currency or "") == (gold.currency or ""),
    }

    case = CaseScore(
        name=name,
        line_precision=alignment.precision(),
        line_recall=alignment.recall(),
        line_f1=alignment.f1(),
        n_mine=len(mine.goods),
        n_gold=len(gold.goods),
        numeric_exact_rate=numeric_exact_rate,
        numeric_by_field=numeric_by_field,
        unit_exact_rate=_rate([ls.unit_exact for ls in line_scores]),
        origin_exact_rate=_rate([ls.origin_exact for ls in line_scores]),
        code_exact_rate=_rate([ls.code_exact for ls in line_scores]),
        code_level_rate=code_level_rate,
        mean_prefix_len=_mean([float(ls.code_prefix_len) for ls in line_scores]),
        desc_chrf=_mean([ls.desc_chrf for ls in line_scores]),
        desc_token_f1=_mean([ls.desc_token_f1 for ls in line_scores]),
        desc_exact_rate=_rate([ls.desc_exact for ls in line_scores]),
        rubric_rate=rubric_rate,
        line_pass_rate=_rate([ls.passed for ls in line_scores]),
        totals_ok=totals_ok,
        excused_external=sum(len(ls.excused) for ls in line_scores),
        lines=line_scores,
    )
    case.passed = (
        case.line_f1 == 1.0
        and all(ls.passed for ls in line_scores)
        and all(totals_ok.values())
    )
    return case


def corpus_summary(cases: list[CaseScore]) -> dict:
    """Aggregate cases into corpus-level headline numbers."""
    if not cases:
        return {"cases": 0, "pass_rate": 1.0}
    return {
        "cases": len(cases),
        "pass_rate": round(_rate([c.passed for c in cases]), 4),
        "mean_line_f1": round(_mean([c.line_f1 for c in cases]), 4),
        "mean_numeric_exact": round(_mean([c.numeric_exact_rate for c in cases]), 4),
        "mean_code_exact": round(_mean([c.code_exact_rate for c in cases]), 4),
        "mean_code@6": round(_mean([c.code_level_rate.get(6, 0.0) for c in cases]), 4),
        "mean_desc_chrf": round(_mean([c.desc_chrf for c in cases]), 4),
    }
