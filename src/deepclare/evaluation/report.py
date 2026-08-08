"""What a scored run produced: per line, per case, and rolled up.

Every count here carries the denominator it was computed over, and the roll-up is
computed over goods **lines** rather than over per-case rates. That is not a style
choice: this corpus runs from 4 goods lines in a case to 554, so a mean of per-case
accuracies is a mean over cases and says almost nothing about lines. Both are reported —
the line-weighted figure as the number, the case-weighted one beside it — because a
metric that moves in one and not the other is telling you which cases changed.

Commodity-code agreement is reported at every level of the hierarchy rather than as
pass/fail, because where two codes diverge says which stage broke: a wrong chapter is a
narrowing failure, a right chapter and wrong heading is the failure the specification
names as unrecoverable, and agreement to eight digits with a wrong tail is a different
and much cheaper problem.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, computed_field

from deepclare.evaluation.manifest import RunManifest

CODE_LEVELS: tuple[int, ...] = (2, 4, 6, 8, 10)
"""2 chapter, 4 heading, 6 subheading — the international boundary — 8 and 10 national."""

NUMERIC_FIELDS: tuple[str, ...] = (
    "quantity",
    "net_weight",
    "gross_weight",
    "invoiced_cost",
    "package_count",
)

RUBRIC_CHECKS: tuple[str, ...] = (
    "brand_retained",
    "trade_name_present",
    "material_stated",
    "no_hallucinated_brand",
)


def rate(numerator: int, denominator: int) -> float | None:
    """A proportion, or None when there was nothing to compute it over.

    None rather than 0.0 or 1.0: nothing asserted is not the same as everything wrong,
    and it is not the same as everything right either.
    """
    return numerator / denominator if denominator else None


class LineOutcome(BaseModel):
    """One produced goods line matched against one labelled goods line."""

    model_config = ConfigDict(frozen=True)

    case: str
    gold_index: int
    similarity: float

    gold_code: str
    produced_code: str
    code_exact: bool
    code_prefix_len: int
    agrees_at: dict[int, bool]

    numeric_exact: dict[str, bool]
    unit_exact: bool
    origin_exact: bool

    desc_chrf: float
    desc_token_f1: float
    desc_exact: bool
    rubric: dict[str, bool | None]

    unresolvable_label: bool
    """The labelled code exists in no nomenclature, so no correct answer was available."""

    passed: bool

    @computed_field
    @property
    def abstained(self) -> bool:
        return not self.produced_code


class CaseOutcome(BaseModel):
    """One case scored."""

    model_config = ConfigDict(frozen=True)

    name: str
    produced_lines: int
    gold_lines: int
    matched: int
    invented: int
    missed: int
    missed_unresolvable: int
    totals_ok: dict[str, bool]
    passed: bool
    seconds: float
    lines: tuple[LineOutcome, ...]

    @computed_field
    @property
    def precision(self) -> float | None:
        return rate(self.matched, self.matched + self.invented)

    @computed_field
    @property
    def recall(self) -> float | None:
        return rate(self.matched, self.matched + self.missed)

    @computed_field
    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or p + r == 0:
            return None
        return 2 * p * r / (p + r)


class CaseFailure(BaseModel):
    """A case that produced no declaration, and why. Counted, never dropped."""

    model_config = ConfigDict(frozen=True)

    name: str
    error_type: str
    error: str


class AlignmentTotals(BaseModel):
    """Goods lines as a set: did we produce the right lines at all."""

    model_config = ConfigDict(frozen=True)

    matched: int
    invented: int
    missed: int

    @computed_field
    @property
    def precision(self) -> float | None:
        return rate(self.matched, self.matched + self.invented)

    @computed_field
    @property
    def recall(self) -> float | None:
        return rate(self.matched, self.matched + self.missed)

    @computed_field
    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or p + r == 0:
            return None
        return 2 * p * r / (p + r)


class CodeAgreement(BaseModel):
    """Commodity-code agreement over a set of matched lines, at each digit depth."""

    model_config = ConfigDict(frozen=True)

    lines: int
    emitted: int
    abstained: int
    exact: int
    agree_at: dict[int, int]
    prefix_digits_total: int

    @computed_field
    @property
    def coverage(self) -> float | None:
        """Share of lines the system was willing to answer on."""
        return rate(self.emitted, self.lines)

    @computed_field
    @property
    def accuracy(self) -> float | None:
        """Exact agreement over every line, counting an abstention as a miss."""
        return rate(self.exact, self.lines)

    @computed_field
    @property
    def precision(self) -> float | None:
        """Exact agreement over the lines it answered. Meaningless without coverage."""
        return rate(self.exact, self.emitted)

    @computed_field
    @property
    def mean_prefix_len(self) -> float | None:
        return rate(self.prefix_digits_total, self.lines)

    @computed_field
    @property
    def agreement_at(self) -> dict[int, float | None]:
        """Agreement at 2, 4, 6, 8 and 10 digits, over every line in the bucket."""
        return {level: rate(self.agree_at.get(level, 0), self.lines) for level in CODE_LEVELS}


class NumericExactness(BaseModel):
    """Exactness per numeric field, within the scorer's tolerance."""

    model_config = ConfigDict(frozen=True)

    lines: int
    exact: dict[str, int]

    @computed_field
    @property
    def exact_rate(self) -> dict[str, float | None]:
        return {field: rate(self.exact.get(field, 0), self.lines) for field in NUMERIC_FIELDS}

    @computed_field
    @property
    def all_fields_rate(self) -> float | None:
        """Every numeric field of every line, as one figure. The per-field rates matter
        more: a system that is exact on four fields and blind on the fifth reads as 0.8
        here and as a specific defect there."""
        return rate(sum(self.exact.values()), self.lines * len(NUMERIC_FIELDS))


class DescriptionScores(BaseModel):
    """Surface similarity and the attribute rubric, over matched lines."""

    model_config = ConfigDict(frozen=True)

    lines: int
    chrf_total: float
    token_f1_total: float
    exact: int
    rubric_checked: dict[str, int]
    rubric_passed: dict[str, int]

    @computed_field
    @property
    def mean_chrf(self) -> float | None:
        return self.chrf_total / self.lines if self.lines else None

    @computed_field
    @property
    def mean_token_f1(self) -> float | None:
        return self.token_f1_total / self.lines if self.lines else None

    @computed_field
    @property
    def exact_rate(self) -> float | None:
        return rate(self.exact, self.lines)

    @computed_field
    @property
    def rubric_rate(self) -> dict[str, float | None]:
        """Each check over the lines where it had something to assert, never over all."""
        return {
            check: rate(self.rubric_passed.get(check, 0), self.rubric_checked.get(check, 0))
            for check in RUBRIC_CHECKS
        }


class UnresolvableAccount(BaseModel):
    """The lines whose label names a code that does not exist.

    Abstaining on these is the correct behaviour and the corpus scores it as a miss, so
    they are held out of the attributable figures and reported here instead.
    """

    model_config = ConfigDict(frozen=True)

    codes: tuple[str, ...]
    provenance: str
    matched_lines: int
    missed_lines: int
    abstained: int
    answered_anyway: int


class Aggregates(BaseModel):
    """The roll-up. Line-weighted unless the name says otherwise."""

    model_config = ConfigDict(frozen=True)

    cases_scored: int
    cases_passed: int
    gold_lines: int
    produced_lines: int
    alignment: AlignmentTotals
    case_weighted_line_f1: float | None
    lines_passed: int
    code_all_labels: CodeAgreement
    code_attributable: CodeAgreement
    numeric: NumericExactness
    description: DescriptionScores
    unresolvable: UnresolvableAccount


class EvaluationReport(BaseModel):
    """One evaluation run, complete with the identity of what produced it."""

    model_config = ConfigDict(frozen=True)

    manifest: RunManifest
    selection_rule: str
    cases_available: int
    aggregates: Aggregates
    cases: tuple[CaseOutcome, ...]
    failures: tuple[CaseFailure, ...]
    caveats: tuple[str, ...]
    seconds: float

    @computed_field
    @property
    def complete(self) -> bool:
        """Every selected case produced a declaration and was scored."""
        return not self.failures


def aggregate(
    cases: list[CaseOutcome], unresolvable_codes: frozenset[str], provenance: str
) -> Aggregates:
    """Roll per-case outcomes up, holding the unresolvable-label lines out of the codes."""
    lines = [line for case in cases for line in case.lines]
    attributable = [line for line in lines if not line.unresolvable_label]
    unresolvable_lines = [line for line in lines if line.unresolvable_label]

    case_f1s = [case.f1 for case in cases if case.f1 is not None]

    return Aggregates(
        cases_scored=len(cases),
        cases_passed=sum(1 for case in cases if case.passed),
        gold_lines=sum(case.gold_lines for case in cases),
        produced_lines=sum(case.produced_lines for case in cases),
        alignment=AlignmentTotals(
            matched=sum(case.matched for case in cases),
            invented=sum(case.invented for case in cases),
            missed=sum(case.missed for case in cases),
        ),
        case_weighted_line_f1=(sum(case_f1s) / len(case_f1s) if case_f1s else None),
        lines_passed=sum(1 for line in lines if line.passed),
        code_all_labels=_code_agreement(lines),
        code_attributable=_code_agreement(attributable),
        numeric=_numeric(lines),
        description=_description(lines),
        unresolvable=UnresolvableAccount(
            codes=tuple(sorted(unresolvable_codes)),
            provenance=provenance,
            matched_lines=len(unresolvable_lines),
            missed_lines=sum(case.missed_unresolvable for case in cases),
            abstained=sum(1 for line in unresolvable_lines if line.abstained),
            answered_anyway=sum(1 for line in unresolvable_lines if not line.abstained),
        ),
    )


def _code_agreement(lines: list[LineOutcome]) -> CodeAgreement:
    emitted = [line for line in lines if not line.abstained]
    return CodeAgreement(
        lines=len(lines),
        emitted=len(emitted),
        abstained=len(lines) - len(emitted),
        exact=sum(1 for line in lines if line.code_exact),
        agree_at={
            level: sum(1 for line in lines if line.agrees_at.get(level, False))
            for level in CODE_LEVELS
        },
        prefix_digits_total=sum(line.code_prefix_len for line in lines),
    )


def _numeric(lines: list[LineOutcome]) -> NumericExactness:
    return NumericExactness(
        lines=len(lines),
        exact={
            field: sum(1 for line in lines if line.numeric_exact.get(field, False))
            for field in NUMERIC_FIELDS
        },
    )


def _description(lines: list[LineOutcome]) -> DescriptionScores:
    return DescriptionScores(
        lines=len(lines),
        chrf_total=sum(line.desc_chrf for line in lines),
        token_f1_total=sum(line.desc_token_f1 for line in lines),
        exact=sum(1 for line in lines if line.desc_exact),
        rubric_checked={
            check: sum(1 for line in lines if line.rubric.get(check) is not None)
            for check in RUBRIC_CHECKS
        },
        rubric_passed={
            check: sum(1 for line in lines if line.rubric.get(check) is True)
            for check in RUBRIC_CHECKS
        },
    )
