"""Printing a report a person can read. The machine-readable form is the report model
itself, dumped as JSON; nothing here decides anything the model has not already decided.

The order is deliberate. The run's identity comes first, before any number, because a
number read without it is the failure this harness was built to stop repeating. Failed
cases come next, because an aggregate over the cases that worked is a different
measurement from the one that was asked for. The caveats come last and are not optional
text: the corpus is synthetic and its labels are a generator's, which is a fact about
every figure above them.
"""

from __future__ import annotations

from deepclare.evaluation.report import (
    CODE_LEVELS,
    NUMERIC_FIELDS,
    RUBRIC_CHECKS,
    CaseOutcome,
    CodeAgreement,
    EvaluationReport,
)

_WIDTH = 84
_LEVEL_NAMES = {2: "chapter", 4: "heading", 6: "subheading", 8: "national", 10: "leaf"}


def render_report(report: EvaluationReport) -> str:
    """The whole report as text."""
    lines: list[str] = []
    lines += _heading("DeepClare evaluation")
    lines += _identity(report)
    lines += _failures(report)
    lines += _headline(report)
    lines += _alignment(report)
    lines += _codes(report)
    lines += _numeric(report)
    lines += _descriptions(report)
    lines += _unresolvable(report)
    lines += _per_case(report)
    lines += _caveats(report)
    return "\n".join(lines) + "\n"


def _heading(title: str) -> list[str]:
    return ["=" * _WIDTH, title, "=" * _WIDTH]


def _section(title: str) -> list[str]:
    return ["", title, "-" * _WIDTH]


def _identity(report: EvaluationReport) -> list[str]:
    manifest = report.manifest
    lines = _section("RUN IDENTITY — what produced these numbers")
    lines.append(f"  scored at            {manifest.scored_at.isoformat(timespec='seconds')}")
    lines.append(f"  code build           {manifest.code_build}")
    lines.append(f"  declarations from    {manifest.producer}")
    if not manifest.attributes_the_output:
        lines.append(
            "  ATTRIBUTION          the declarations scored here were NOT produced by "
            "this run. Everything"
        )
        lines.append(
            "                       below is the configuration in force while scoring, "
            "and it does not"
        )
        lines.append("                       attribute the scored XML to anything.")
    lines.append(f"  corpus               {manifest.corpus_dir}")
    lines.append(
        f"  cases                {len(report.cases) + len(report.failures)} selected of "
        f"{report.cases_available} available"
    )
    lines += _wrap(report.selection_rule, indent=" " * 23)
    lines.append(f"  scorer               {manifest.scorer_dir}")
    lines.append("  models               " + "  ".join(
        f"{tier}={model}" for tier, model in manifest.model_ids.items()
    ))
    lines.append("  decoding             " + "  ".join(
        f"{key}={value}" for key, value in manifest.decoding.items()
    ))
    lines.append(
        f"  nomenclature         vintage {manifest.nomenclature_vintage}   "
        f"{manifest.nomenclature_dir}"
    )
    lines.append(
        f"  embeddings           {manifest.embedding_model} @ "
        f"{manifest.embedding_dimensions}d"
    )
    lines.append(f"  retrieval depth      {manifest.retrieval_depth} candidates to the pick")
    lines.append("  classifier           " + "  ".join(
        f"{key}={value}" for key, value in manifest.classification_features.items()
    ))
    lines.append("  scoring thresholds   " + "  ".join(
        f"{key}={value}" for key, value in manifest.scoring_thresholds.items()
    ))
    lines.append(f"  prompts ({len(manifest.prompts)})")
    for prompt in manifest.prompts:
        lines.append(
            f"    {prompt.name:<28} v{prompt.version:<8} "
            f"sha256:{prompt.content_sha256[:12]}"
        )
    lines.append(f"  wall clock           {report.seconds:.1f}s")
    return lines


def _failures(report: EvaluationReport) -> list[str]:
    if not report.failures:
        return []
    lines = _section(f"CASES THAT PRODUCED NOTHING — {len(report.failures)}")
    lines.append("  Every figure below is computed without these. The run is not complete.")
    for failure in report.failures:
        lines.append(f"  {failure.name}: {failure.error_type}: {failure.error}")
    return lines


def _headline(report: EvaluationReport) -> list[str]:
    totals = report.aggregates
    lines = _section("HEADLINE")
    lines.append(
        f"  cases scored         {totals.cases_scored}"
        f"   passing every check {totals.cases_passed}"
        f"   ({_pct(_rate(totals.cases_passed, totals.cases_scored))})"
    )
    lines.append(
        f"  goods lines          {totals.gold_lines} labelled, "
        f"{totals.produced_lines} produced, {totals.alignment.matched} matched"
    )
    lines.append(
        f"  lines passing all    {totals.lines_passed} / {totals.alignment.matched}"
        f"   ({_pct(_rate(totals.lines_passed, totals.alignment.matched))})"
    )
    lines.append(
        f"  run complete         {'yes' if report.complete else 'NO — see failures above'}"
    )
    return lines


def _alignment(report: EvaluationReport) -> list[str]:
    alignment = report.aggregates.alignment
    lines = _section("GOODS-LINE ALIGNMENT — did we produce the right lines at all")
    lines.append(
        f"  matched {alignment.matched}   invented {alignment.invented}   "
        f"missed {alignment.missed}"
    )
    lines.append(
        f"  precision {_pct(alignment.precision)}   recall {_pct(alignment.recall)}   "
        f"F1 {_pct(alignment.f1)}      (line-weighted, "
        f"n={alignment.matched + alignment.missed} labelled lines)"
    )
    lines.append(
        f"  case-weighted F1 {_pct(report.aggregates.case_weighted_line_f1)}"
        f"      (mean over {report.aggregates.cases_scored} cases)"
    )
    return lines


def _codes(report: EvaluationReport) -> list[str]:
    lines = _section("COMMODITY-CODE AGREEMENT — by digit depth, not pass/fail")
    lines += _code_block(
        "attributable labels (the number to quote)", report.aggregates.code_attributable
    )
    lines.append("")
    lines += _code_block(
        "every label, including the codes that do not exist",
        report.aggregates.code_all_labels,
    )
    return lines


def _code_block(title: str, agreement: CodeAgreement) -> list[str]:
    lines = [f"  {title} — n={agreement.lines} matched lines"]
    lines.append(
        f"    coverage   {_pct(agreement.coverage)}"
        f"   ({agreement.emitted} answered, {agreement.abstained} abstained)"
    )
    lines.append(
        f"    exact      accuracy {_pct(agreement.accuracy)} over all lines"
        f"   ·   precision {_pct(agreement.precision)} over the {agreement.emitted} answered"
    )
    lines.append(f"    mean agreeing prefix {_fmt(agreement.mean_prefix_len)} digits")
    lines.append("    agreement at")
    for level in CODE_LEVELS:
        count = agreement.agree_at.get(level, 0)
        lines.append(
            f"      {level:>2} digits ({_LEVEL_NAMES[level]:<10}) "
            f"{_pct(agreement.agreement_at.get(level))}   {count}/{agreement.lines}"
        )
    return lines


def _numeric(report: EvaluationReport) -> list[str]:
    numeric = report.aggregates.numeric
    lines = _section("NUMERIC FIELD EXACTNESS — within the scorer's tolerance")
    lines.append(f"  n={numeric.lines} matched lines")
    for field in NUMERIC_FIELDS:
        lines.append(
            f"    {field:<16} {_pct(numeric.exact_rate.get(field))}"
            f"   {numeric.exact.get(field, 0)}/{numeric.lines}"
        )
    lines.append(f"    {'all fields':<16} {_pct(numeric.all_fields_rate)}")
    return lines


def _descriptions(report: EvaluationReport) -> list[str]:
    description = report.aggregates.description
    lines = _section("DESCRIPTIONS")
    lines.append(f"  n={description.lines} matched lines")
    lines.append(f"    mean chrF        {_fmt(description.mean_chrf)}")
    lines.append(f"    mean token F1    {_fmt(description.mean_token_f1)}")
    lines.append(
        f"    exact match      {_pct(description.exact_rate)}"
        f"   {description.exact}/{description.lines}"
    )
    lines.append("    attribute rubric, each over the lines where it had something to assert")
    for check in RUBRIC_CHECKS:
        checked = description.rubric_checked.get(check, 0)
        passed = description.rubric_passed.get(check, 0)
        lines.append(
            f"      {check:<22} {_pct(description.rubric_rate.get(check))}   {passed}/{checked}"
        )
    return lines


def _unresolvable(report: EvaluationReport) -> list[str]:
    account = report.aggregates.unresolvable
    lines = _section("LABELS NAMING A CODE THAT DOES NOT EXIST — held out of the above")
    lines.append(f"  codes        {', '.join(account.codes)}")
    lines.append("  provenance")
    lines += _wrap(account.provenance, indent="    ")
    lines.append(
        f"  lines        {account.matched_lines} matched, {account.missed_lines} not "
        f"produced at all"
    )
    lines.append(
        f"  behaviour    abstained {account.abstained}  (correct — no code exists to give)"
    )
    lines.append(
        f"               answered  {account.answered_anyway}  "
        f"(a code was emitted for a label with no code)"
    )
    return lines


def _per_case(report: EvaluationReport) -> list[str]:
    lines = _section("PER CASE — two rows each: the lines, then the codes and the fields")
    for case in report.cases:
        cells = _case_columns(case)
        lines.append(
            f"  {case.name:<22} mine {case.produced_lines:>4}  gold {case.gold_lines:>4}  "
            f"matched {case.matched:>4}   P {_pct(case.precision):>6} R {_pct(case.recall):>6} "
            f"F1 {_pct(case.f1):>6}   {case.seconds:>5.1f}s   "
            f"{'PASS' if case.passed else 'FAIL'}"
        )
        depths = "  ".join(
            f"@{level} {_pct(cells['at'][level]):>6}" for level in CODE_LEVELS
        )
        lines.append(
            f"  {'':<22} code  cov {_pct(cells['coverage']):>6} "
            f"exact {_pct(cells['exact']):>6}  {depths}"
        )
        lines.append(
            f"  {'':<22} field num {_pct(cells['numeric']):>6} "
            f"chrF {_fmt(cells['chrf']):>6}   lines passing "
            f"{cells['lines_passed']}/{case.matched}"
            + (f"   impossible labels {cells['unresolvable']}" if cells["unresolvable"] else "")
        )
    return lines


def _case_columns(case: CaseOutcome) -> dict:
    """The per-case row's cells, computed the way the roll-up computes them.

    Code figures are over the case's attributable lines only — the same exclusion the
    aggregate makes, so a case row and the total answer the same question.
    """
    lines = case.lines
    attributable = [line for line in lines if not line.unresolvable_label]
    emitted = [line for line in attributable if not line.abstained]
    numeric_cells = sum(sum(1 for ok in line.numeric_exact.values() if ok) for line in lines)
    return {
        "coverage": _rate(len(emitted), len(attributable)),
        "exact": _rate(sum(1 for line in attributable if line.code_exact), len(attributable)),
        "at": {
            level: _rate(
                sum(1 for line in attributable if line.agrees_at.get(level, False)),
                len(attributable),
            )
            for level in CODE_LEVELS
        },
        "numeric": _rate(numeric_cells, len(lines) * len(NUMERIC_FIELDS)),
        "chrf": _rate_float(sum(line.desc_chrf for line in lines), len(lines)),
        "lines_passed": sum(1 for line in lines if line.passed),
        "unresolvable": len(lines) - len(attributable),
    }


def _caveats(report: EvaluationReport) -> list[str]:
    lines = _section("WHAT THIS NUMBER IS NOT")
    for caveat in report.caveats:
        lines.append("")
        lines += _wrap(caveat, indent="  ")
    return lines


def _wrap(text: str, indent: str) -> list[str]:
    words = text.split()
    out: list[str] = []
    current = indent
    for word in words:
        if len(current) + len(word) + 1 > _WIDTH:
            out.append(current.rstrip())
            current = indent
        current += word + " "
    if current.strip():
        out.append(current.rstrip())
    return out


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _rate_float(total: float, denominator: int) -> float | None:
    return total / denominator if denominator else None


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"
