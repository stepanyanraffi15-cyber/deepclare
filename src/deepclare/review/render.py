"""The report as plain text, for a human reading it in a terminal or an email.

This is presentation and only presentation: it prints what the report object already
holds, in the order the report already put it in. Nothing is decided here, and a value
appears exactly as its producer set it down.

Text is one rendering, not the rendering. The structured report is the interface a client
consumes; this exists so that a run can be read by a person without one.
"""

from __future__ import annotations

from textwrap import fill

from deepclare.domain import Confidence, Provenance, ValueOrigin
from deepclare.review.defects import ReportDefect
from deepclare.review.ordering import ORDERING_RULE
from deepclare.review.report import ReviewEntry, ReviewGroup, ReviewReport
from deepclare.review.values import ReportedValue

WIDTH = 88
UNASSESSED = "—"


def render_report(report: ReviewReport) -> str:
    """The whole report, top to bottom, in the order it was assembled in."""
    blocks = [_title(), _headline(report), _wrap(ORDERING_RULE, indent="")]
    if report.defects:
        blocks.append(_defects_block(report.defects))
    blocks.extend(_group_block(group) for group in report.groups)
    if not report.groups:
        blocks.append("Nothing was raised for review and no values were reported.")
    return "\n\n".join(blocks) + "\n"


def _title() -> str:
    return "REVIEW REPORT\n" + "=" * len("REVIEW REPORT")


def _headline(report: ReviewReport) -> str:
    counts = ", ".join(
        f"{tally.count} {_kind_name(tally.kind.value)}" for tally in report.tallies
    )
    scope = f"{report.line_count} goods {'line' if report.line_count == 1 else 'lines'}"
    if any(group.line_id is None for group in report.groups):
        scope = f"the shipment and {scope}"
    sentences = [f"{report.total_items} items over {scope}: {counts}."]
    if report.defects:
        sentences.append(
            f"{len(report.defects)} defects in the account itself — read those first."
        )
    return _wrap(" ".join(sentences), indent="")


def _defects_block(defects: tuple[ReportDefect, ...]) -> str:
    blocks = [
        _heading(f"DEFECTS IN THE ACCOUNT ({len(defects)})"),
        _wrap(
            "These are faults in what the run recorded about the declaration, not in "
            "the declaration. Each names the producer that should have attached "
            "something and did not; nothing downstream can supply it after the fact.",
            indent="",
        ),
    ]
    for defect in defects:
        where = " · ".join(
            part
            for part in (
                _scope_name(defect.line_id),
                defect.concept,
                f"produced by {defect.producing_stage}"
                if defect.producing_stage
                else None,
            )
            if part
        )
        blocks.append("  " + where + "\n" + _wrap(defect.problem, indent="      "))
    return "\n\n".join(blocks)


def _group_block(group: ReviewGroup) -> str:
    blocks = [_heading(_scope_name(group.line_id).upper()), _flags_line(group)]
    blocks.extend(_entry_block(entry) for entry in group.entries)

    # Every value appears once. A value an item already showed is not repeated below it.
    shown = {entry.value.concept for entry in group.entries if entry.value is not None}
    rest = [value for value in group.values if value.concept not in shown]
    if rest:
        blocks.append(
            f"  other values reported ({len(rest)})\n"
            + "\n".join(_value_block(value) for value in rest)
        )
    return "\n\n".join(blocks)


def _flags_line(group: ReviewGroup) -> str:
    flags = group.flags
    parts = [
        "needs review" if flags.needs_review else "nothing raised",
    ]
    if flags.most_consequential is not None:
        parts.append(f"most consequential: {_kind_name(flags.most_consequential.value)}")
    if flags.inferred:
        parts.append("inferred: " + ", ".join(flags.inferred))
    if flags.abstentions:
        parts.append(
            "abstained on: "
            + ", ".join(abstention.concept for abstention in flags.abstentions)
        )
    return _wrap(" · ".join(parts), indent="  ")


def _entry_block(entry: ReviewEntry) -> str:
    item = entry.item
    lines = [f"  [{_kind_name(item.kind.value)}] {item.concept}"]
    lines.append(_wrap(item.detail, indent="      "))
    if item.remedy:
        lines.append(_wrap(f"resolved by: {item.remedy}", indent="      "))
    if entry.value is not None:
        lines.append(f"      value: {entry.value.shown!r}")
        lines.extend(_account_lines(entry.value, indent="      "))
    return "\n".join(lines)


def _value_block(value: ReportedValue) -> str:
    return "\n".join(
        [f"    {value.concept}: {value.shown!r}", *_account_lines(value, "      ")]
    )


def _account_lines(value: ReportedValue, indent: str) -> list[str]:
    """Where the value came from, how far it is trusted, and what was done to it."""
    return [
        _wrap(_provenance_phrase(value.provenance), indent=indent),
        _wrap(_confidence_phrase(value.confidence), indent=indent),
        *(
            _wrap(
                f"printed {transform.before!r} → {transform.after!r} "
                f"({transform.operation})",
                indent=indent,
            )
            for transform in value.provenance.transforms
        ),
    ]


def _provenance_phrase(provenance: Provenance) -> str:
    """Where the value came from, in the terms its own origin implies."""
    parts: list[str] = []
    match provenance.origin:
        case ValueOrigin.EXTRACTED:
            where = f"read from {provenance.source_document_id}"
            if provenance.region is not None:
                where += f" page {provenance.region.page_number}"
            if provenance.source_document_role:
                where += f" ({provenance.source_document_role})"
            parts.append(where)
        case ValueOrigin.DERIVED:
            parts.append(f"derived: {provenance.rule}")
        case ValueOrigin.GENERATED:
            parts.append(f"written by {provenance.prompt_name}")
            if provenance.prompt_version:
                parts.append(f"prompt {provenance.prompt_version}")
        case ValueOrigin.REUSED:
            parts.append(f"copied from filing {provenance.source_filing_id}")
        case ValueOrigin.SUPPLIED:
            parts.append(f"supplied by {provenance.supplied_by}")
        case ValueOrigin.CONSTANT:
            parts.append("fixed by the filing contract")
    if provenance.stage:
        parts.append(f"stage {provenance.stage}")
    return " · ".join(parts)


def _confidence_phrase(confidence: Confidence) -> str:
    """All three, always, including the ones nobody assessed.

    One number cannot answer three questions, so the report never collapses them: a value
    read perfectly, derived soundly and still likely to be refused on filing has to be
    legible as exactly that.
    """
    return " · ".join(
        f"{name} {_score(score)}"
        for name, score in (
            ("extraction", confidence.extraction),
            ("derivation", confidence.derivation),
            ("validity", confidence.validity),
        )
    )


def _score(score: float | None) -> str:
    return UNASSESSED if score is None else f"{score:.2f}"


def _scope_name(line_id: str | None) -> str:
    return "shipment" if line_id is None else f"goods line {line_id}"


def _kind_name(kind: str) -> str:
    return kind.replace("_", " ")


def _heading(text: str) -> str:
    return f"{text}\n{'-' * len(text)}"


def _wrap(text: str, indent: str) -> str:
    return fill(text, width=WIDTH, initial_indent=indent, subsequent_indent=indent)
