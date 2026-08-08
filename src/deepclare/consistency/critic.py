"""A21 — the consistency critic. One call, over the whole assembled draft.

Every line was named and coded in its own call, so nothing in the run so far has ever
looked at two lines at once. That independence is deliberate and it has one structural
consequence: the same product family comes out described in different words, structured
differently, and sometimes coded differently, with nothing in the per-line path able to
notice. This call is the first and only place that sees the draft as a document.

It reports and it does not change anything. Separating the judgement from the edit is
what lets a rewrite be discarded whole while the findings survive — the specification's
degradation rule, and it only works if the two are different calls.

**It never raises.** A provider failure, a refusal or a malformed answer returns `None`,
and the caller abandons the whole pass with the lines untouched. This stage improves a
declaration; it is never the reason a run fails.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from deepclare.consistency.rendering import draft_lines
from deepclare.consistency.records import (
    ConsistencyField,
    ConsistencyIssue,
    Critique,
    DraftedLine,
)
from deepclare.consistency.schemas import CritiqueIssue, CritiqueLines
from deepclare.models import GenerativeModel, ModelError, ModelTier
from deepclare.prompting import render_prompt

logger = logging.getLogger(__name__)

CRITIC_TIER = ModelTier.STANDARD
"""Reading a whole draft declaration and telling a real inconsistency from a legitimate
difference is a reasoning job over long context. It is not a label-emitting call, and it
is not a material or legal distinction either — those are the code pick's business."""


class ConsistencyCritic:
    """Reports every inconsistency across one shipment's assembled lines."""

    def __init__(self, model: GenerativeModel, prompts_dir: Path) -> None:
        self._model = model
        self._prompts_dir = prompts_dir

    def critique(self, lines: Sequence[DraftedLine]) -> Critique | None:
        """What is inconsistent across these lines, or `None` if the call did not land."""
        prompt = render_prompt(
            self._prompts_dir,
            "critique_lines",
            {"draft_lines": draft_lines(lines)},
        )
        try:
            result = self._model.generate(
                tier=CRITIC_TIER, prompt=prompt, output=CritiqueLines
            )
        except ModelError as exc:
            logger.warning("the consistency critique failed and the pass is abandoned: %s", exc)
            return None

        known = {line.line_id for line in lines}
        return Critique(
            issues=tuple(_issues(result.value.issues, known)),
            shipment_notes=tuple(
                note.strip() for note in result.value.shipment_notes if note.strip()
            ),
            call=result.call,
        )


def _issues(
    reported: Sequence[CritiqueIssue], known: set[str]
) -> list[ConsistencyIssue]:
    """The reported issues that are about lines of this shipment.

    An issue against a line id nobody sent is dropped rather than fixed up. It concerns
    goods that are not in this declaration, so there is nothing it could be re-keyed to,
    and inventing a line to hang it on would put a finding on the wrong goods.
    """
    kept = []
    for issue in reported:
        line_id = issue.line_id.strip()
        problem = issue.problem.strip()
        if line_id not in known:
            logger.warning(
                "the critic reported an issue against line %r, which is not in this "
                "shipment; dropping it",
                issue.line_id,
            )
            continue
        if not problem:
            logger.warning("the critic reported an issue on line %s with no problem "
                           "stated; dropping it", line_id)
            continue
        suggested = issue.suggested_value.strip()
        kept.append(
            ConsistencyIssue(
                line_id=line_id,
                field=ConsistencyField(issue.field),
                problem=problem,
                suggested_value=suggested or None,
            )
        )
    return kept
