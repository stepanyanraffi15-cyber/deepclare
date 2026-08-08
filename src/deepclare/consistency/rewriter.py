"""A22 — the consistency rewriter. One call, applying the critique.

It is given the same draft the critic read plus the critic's findings, and it answers for
**every** line — including the ones it changes nothing about, which it repeats verbatim.
Answering for every line is not politeness: a partial answer cannot be told apart from an
answer that dropped a line it should have conformed, so an answer that does not cover
exactly the lines it was given is thrown away whole.

What comes back is a *proposal*. Nothing here decides that a proposal is filed — the
guardrails and the existence gate do that, in the reconciler. This module's only job is
to obtain the answer and to establish that the answer is about this shipment.

**It never raises**, for the same reason the critic does not: a rewrite failure keeps the
critique's flags and changes nothing.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from deepclare.consistency.records import Critique, DraftedLine
from deepclare.consistency.rendering import draft_lines, findings
from deepclare.consistency.schemas import ConformLines
from deepclare.models import GenerativeModel, ModelCall, ModelError, ModelTier
from deepclare.prompting import render_prompt

logger = logging.getLogger(__name__)

REWRITER_TIER = ModelTier.STANDARD
"""Conforming one line's wording to its siblings' is the same class of work as writing
the line in the first place, and the writer runs at this tier."""


class LineProposal(BaseModel):
    """What the rewriter would file for one line, before any guardrail has looked at it."""

    model_config = ConfigDict(frozen=True)

    line_id: str = Field(pattern=r"^[1-9][0-9]*$")
    description: str
    code: str
    """Empty means "leave the code alone". A code is never blanked, so there is no way to
    express "remove this code" and that is deliberate."""


class RewriteAttempt(BaseModel):
    """The result of asking for a rewrite, in one of three states.

    * the call did not land — no `call`, and `discarded_because` says so;
    * the answer landed and was thrown away — `call` and `discarded_because` both set;
    * the answer landed and is usable — `call` set, `discarded_because` empty.

    In the first two the drafted lines are filed exactly as they were drafted.
    """

    model_config = ConfigDict(frozen=True)

    proposals: tuple[LineProposal, ...] = ()
    call: ModelCall | None = None
    discarded_because: str | None = None

    @property
    def usable(self) -> bool:
        return self.discarded_because is None


class ConsistencyRewriter:
    """Asks for the conformed lines and checks that the answer is about this shipment."""

    def __init__(self, model: GenerativeModel, prompts_dir: Path) -> None:
        self._model = model
        self._prompts_dir = prompts_dir

    def rewrite(
        self, lines: Sequence[DraftedLine], critique: Critique
    ) -> RewriteAttempt:
        """One call. The answer is never partially believed."""
        prompt = render_prompt(
            self._prompts_dir,
            "conform_lines",
            {
                "draft_lines": draft_lines(lines),
                "findings": findings(critique.issues, critique.shipment_notes),
            },
        )
        try:
            result = self._model.generate(
                tier=REWRITER_TIER, prompt=prompt, output=ConformLines
            )
        except ModelError as exc:
            logger.warning(
                "the consistency rewrite failed; the critique's flags are kept and "
                "nothing is changed: %s",
                exc,
            )
            return RewriteAttempt(discarded_because=f"the rewrite call failed: {exc}")

        answered = [line.line_id.strip() for line in result.value.lines]
        complaint = _why_the_answer_is_not_about_these_lines(
            answered, [line.line_id for line in lines]
        )
        if complaint is not None:
            logger.warning("the whole rewrite is discarded: %s", complaint)
            return RewriteAttempt(call=result.call, discarded_because=complaint)

        return RewriteAttempt(
            proposals=tuple(
                LineProposal(
                    line_id=answered[index],
                    description=result.value.lines[index].description,
                    code=result.value.lines[index].code.strip(),
                )
                for index in range(len(answered))
            ),
            call=result.call,
        )


def _why_the_answer_is_not_about_these_lines(
    answered: Sequence[str], asked: Sequence[str]
) -> str | None:
    """The one thing that discards a whole rewrite, or `None`.

    The rule the specification states is the omission: a rewrite that leaves a line out
    is thrown away entirely, because there is no way to tell "this line was already fine"
    from "this line was forgotten". Duplicated and unknown ids are held to the same
    standard rather than repaired — the answer is a mapping from line to text, and a
    mapping that is not one-to-one onto the lines that were sent is not an answer about
    this shipment. Picking one of two answers for a line, or ignoring an id nobody asked
    about, would be this module choosing on the model's behalf.
    """
    missing = [line_id for line_id in asked if line_id not in answered]
    if missing:
        return (
            f"the rewrite did not answer for line(s) {', '.join(missing)}; a rewrite "
            "that omits a line is discarded whole"
        )
    duplicated = sorted({line_id for line_id in answered if answered.count(line_id) > 1})
    if duplicated:
        return (
            f"the rewrite answered twice for line(s) {', '.join(duplicated)}, so there "
            "is no single text for them"
        )
    unknown = sorted(set(answered) - set(asked))
    if unknown:
        return (
            f"the rewrite answered for line(s) {', '.join(unknown)}, which are not in "
            "this shipment"
        )
    return None
