"""Turning the draft and the critique into the strings the prompt files name.

Values only. Every label and every explanation of what an absence means lives in the
prompt file; nothing here reads as English prose to a model that is not data.

One shape decision worth stating: the lines are rendered as one block per line rather
than as JSON. Both calls have to reason about a *set* of lines side by side, and the one
thing they must never touch — the computed segments — is easier to see as its own labelled
row than as one more key in an object.
"""

from __future__ import annotations

from collections.abc import Sequence

from deepclare.consistency.records import ConsistencyIssue, DraftedLine

NOTHING = "(none)"
"""An absent scalar or an empty block. Absence is stated to a model, never omitted: an
absent key and an empty one are different signals and only one of them is a fact."""

NO_CODE = "(none — classification abstained)"
"""A line with no code. Named rather than blank, because "no code yet" and "no code is
right" are different situations and only the first invites a suggestion."""


def draft_lines(lines: Sequence[DraftedLine]) -> str:
    """Every drafted line, one labelled block each, in the order they will be filed."""
    return "\n\n".join(_line_block(line) for line in lines)


def findings(issues: Sequence[ConsistencyIssue], notes: Sequence[str]) -> str:
    """The critique, as the rewriter reads it."""
    rows = [_issue_row(issue) for issue in issues]
    rows.extend(f"shipment · {note}" for note in notes if note.strip())
    return "\n".join(rows) if rows else NOTHING


def _line_block(line: DraftedLine) -> str:
    rows = [
        f"line {line.line_id}",
        f"  invoice name        : {line.source_name}",
        f"  filed text          : {line.description}",
        f"  commodity code      : {line.code or NO_CODE}",
        f"  tariff unit         : {line.supplementary_unit or NOTHING}",
        f"  must appear verbatim: {_segments(line.deterministic_segments)}",
    ]
    return "\n".join(rows)


def _segments(segments: Sequence[str]) -> str:
    return "  |  ".join(segments) if segments else NOTHING


def _issue_row(issue: ConsistencyIssue) -> str:
    row = f"line {issue.line_id} · {issue.field.value} — {issue.problem}"
    if issue.suggested_value:
        row += f"\n    suggested: {issue.suggested_value}"
    return row
