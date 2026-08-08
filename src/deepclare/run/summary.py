"""A24 — the run's account of itself, in the terms an operator asks about it.

Three questions get asked of a finished run before anything else: how many goods lines
came out of it, how many of them carry a code, and what has to be looked at. This renders
those three and nothing more; the review report itself is a separate, longer document and
is written beside the declaration.

Nothing here computes a value. The counts are of objects the chain already produced, and
the tallies are the report's own — a summary that could disagree with the report would be
a second implementation of the report.
"""

from __future__ import annotations

from deepclare.review.ordering import CONSEQUENCE_ORDER
from deepclare.run.state import RunState


def format_summary(state: RunState) -> str:
    """The run in a screenful."""
    report = state.require_report()
    filed = state.require_filed()

    lines = [
        f"goods lines          {state.goods_line_count}",
        f"codes assigned       {state.codes_assigned}",
        f"codes abstained      {state.codes_abstained}",
        f"conforms / filable   {filed.conformance.conforms} / {filed.conformance.filable}",
        "",
        f"review items         {report.total_items}",
    ]
    by_kind = {tally.kind: tally.count for tally in report.tallies}
    for kind in CONSEQUENCE_ORDER:
        lines.append(f"  {kind.value:<14} {by_kind.get(kind, 0)}")

    abstentions = [
        (draft.line_id, draft.classification.rationale)
        for draft in state.drafts
        if draft.classification.code is None
    ]
    if abstentions:
        lines.append("")
        lines.append("abstentions")
        for line_id, rationale in abstentions:
            lines.append(f"  line {line_id}: {_one_line(rationale)}")

    flagged = [
        draft.line_id
        for draft in state.drafts
        if draft.classification.code is not None and draft.classification.needs_review
    ]
    if flagged:
        lines.append("")
        lines.append(f"codes flagged for confirmation   lines {', '.join(flagged)}")

    if report.defects:
        lines.append("")
        lines.append(f"defects in the report itself     {len(report.defects)}")
        for defect in report.defects:
            scope = "shipment" if defect.line_id is None else f"line {defect.line_id}"
            lines.append(f"  {scope}: {defect.concept} — {_one_line(defect.problem)}")

    if state.notes:
        lines.append("")
        lines.append("what the run did")
        for note in state.notes:
            lines.append(f"  {note}")

    return "\n".join(lines)


def _one_line(text: str, limit: int = 160) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[:limit]}…"
