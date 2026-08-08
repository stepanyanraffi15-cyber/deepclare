"""What goes into cross-line reconciliation and what comes out of it.

The input is the **fully assembled final** line — the text that will actually be filed,
including the deterministic size and quantity segments some other stage appended to it.
Reconciliation deliberately does not see the naming fragment: a critique of text that is
not the filed text is a critique of something nobody reads, and a rewrite of a fragment
can silently drop a segment that gets appended afterwards.

Those appended segments arrive named, in `deterministic_segments`. Naming them is what
makes "reproduced verbatim, never regenerated" checkable rather than merely instructed:
the rewrite guardrail looks for each of them character for character in whatever comes
back. A segment that is not in the text it claims to be part of is a caller mistake and
is refused at construction.

The output is every input line, changed or not, plus the account of what changed: a
`Transform` per change so the caller can append it to that value's own chain, the
rejected proposals so a discarded rewrite is visible rather than silent, and the review
items a human acts on.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deepclare.classification.existence import CONCEPT as CODE_CONCEPT
from deepclare.domain import ReviewItem, Transform
from deepclare.models import ModelCall

STAGE = "cross-line consistency"
"""What every value produced here names as its producing stage."""

DESCRIPTION_CONCEPT = "goods description"
SUPPLEMENTARY_UNIT_CONCEPT = "supplementary quantity unit"
SHIPMENT_CONCEPT = "cross-line consistency"


class ConsistencyField(StrEnum):
    """The three things this module has authority over, and nothing else.

    Quantities, weights, packages, prices and parties are absent by design: they are
    arithmetic and are resolved elsewhere from the documents' own figures.
    """

    DESCRIPTION = "description"
    CODE = "code"
    SUPPLEMENTARY_UNIT = "supplementary_unit"


CONCEPT_BY_FIELD = {
    ConsistencyField.DESCRIPTION: DESCRIPTION_CONCEPT,
    ConsistencyField.CODE: CODE_CONCEPT,
    ConsistencyField.SUPPLEMENTARY_UNIT: SUPPLEMENTARY_UNIT_CONCEPT,
}
"""Review items are keyed by domain concept. The commodity-code concept is imported from
the module that already names it rather than re-spelled, because two spellings of one
concept split a line's findings across two rows of the review report."""


class PassOutcome(StrEnum):
    """What the pass did, as one machine-readable word.

    Every value but `APPLIED` means the drafted lines came out exactly as they went in.
    """

    NOT_ATTEMPTED = "not_attempted"
    """There was nothing to reconcile — a single line is consistent with itself."""

    CRITIQUE_FAILED = "critique_failed"
    """The whole pass was abandoned: no rewrite, no flags, no changes."""

    NOTHING_TO_DO = "nothing_to_do"
    """The critic ran and found no per-line inconsistency, so no rewrite was requested."""

    REWRITE_FAILED = "rewrite_failed"
    """The rewrite call failed. The critique's flags are kept; nothing is changed."""

    REWRITE_DISCARDED = "rewrite_discarded"
    """The rewrite did not answer for exactly the lines it was given, so all of it was
    thrown away. The critique's flags are kept."""

    APPLIED = "applied"
    """The rewrite was accepted, in whole or in part. Individual proposals may still have
    been refused by a guardrail; `rejected` says which."""


class DraftedLine(BaseModel):
    """One goods line as it stands before reconciliation."""

    model_config = ConfigDict(frozen=True)

    line_id: str = Field(pattern=r"^[1-9][0-9]*$")

    source_name: str = Field(min_length=1)
    """The invoice's own wording, as printed. It is the anchor: it carries the product
    family and this item's own size and colour, and it is what a rewrite is checked
    against for a lost detail."""

    description: str = Field(min_length=1)
    """The fully assembled Armenian text that will be filed, segments included."""

    deterministic_segments: tuple[str, ...] = ()
    """Substrings of `description` that were computed rather than written — the size
    segment, the shipment-quantity phrase. Reproduced verbatim or the rewrite is refused."""

    code: str | None = None
    """The 10-digit leaf, or `None` where classification abstained."""

    supplementary_unit: str | None = None
    """The nomenclature's own unit for `code`. Read off the entry by the module that
    assigned the code; never read or written here."""

    @model_validator(mode="after")
    def _segments_must_be_in_the_text_they_belong_to(self) -> Self:
        for segment in self.deterministic_segments:
            if not segment.strip():
                raise ValueError(
                    f"line {self.line_id}: a deterministic segment is blank. A segment "
                    "that is nothing cannot be checked for and would make the guardrail "
                    "pass on any text at all."
                )
            if segment not in self.description:
                raise ValueError(
                    f"line {self.line_id}: the deterministic segment {segment!r} is not "
                    f"in the description it is declared part of ({self.description!r}). "
                    "The guardrail checks that a rewrite keeps these; one that is not "
                    "there to begin with would refuse every rewrite of this line."
                )
        return self


class ConsistencyIssue(BaseModel):
    """One inconsistency the critic reported, against one field of one line."""

    model_config = ConfigDict(frozen=True)

    line_id: str = Field(pattern=r"^[1-9][0-9]*$")
    field: ConsistencyField
    problem: str = Field(min_length=1)
    suggested_value: str | None = None
    """What the critic would put there instead, when it was confident enough to say.
    Never binding: the rewriter is a separate call and every guardrail still applies."""


class Critique(BaseModel):
    """What the critic saw across the whole draft."""

    model_config = ConfigDict(frozen=True)

    issues: tuple[ConsistencyIssue, ...] = ()
    shipment_notes: tuple[str, ...] = ()
    call: ModelCall


class LineChange(BaseModel):
    """One field of one line, changed, with the record of the change."""

    model_config = ConfigDict(frozen=True)

    line_id: str
    field: ConsistencyField
    transform: Transform
    """Append-only, so the caller can add it to that value's own chain and a filed value
    still walks back to the ink."""


class RejectedRewrite(BaseModel):
    """A proposal a guardrail refused, and why. The original stands."""

    model_config = ConfigDict(frozen=True)

    line_id: str
    field: ConsistencyField
    proposed: str
    reason: str = Field(min_length=1)


class ReconciledLine(BaseModel):
    """One goods line as it stands after reconciliation, changed or not."""

    model_config = ConfigDict(frozen=True)

    line_id: str
    description: str = Field(min_length=1)
    code: str | None = None
    supplementary_unit: str | None = None
    changed_fields: tuple[ConsistencyField, ...] = ()


class ConsistencyOutcome(BaseModel):
    """Everything the pass produced, including the case where it produced nothing."""

    model_config = ConfigDict(frozen=True)

    outcome: PassOutcome
    detail: str = Field(min_length=1)
    """One sentence naming what happened, for the run summary and for a human reading a
    pass that changed nothing."""

    lines: tuple[ReconciledLine, ...]
    """Every input line, in the order it was given. The consumer reads these and does not
    have to know whether the pass ran."""

    changes: tuple[LineChange, ...] = ()
    rejected: tuple[RejectedRewrite, ...] = ()
    review_items: tuple[ReviewItem, ...] = ()
    shipment_notes: tuple[str, ...] = ()
    calls: tuple[ModelCall, ...] = ()

    @property
    def changed_line_ids(self) -> tuple[str, ...]:
        """The set of lines it changed, in input order."""
        return tuple(line.line_id for line in self.lines if line.changed_fields)


def untouched(
    lines: Sequence[DraftedLine],
    *,
    outcome: PassOutcome,
    detail: str,
    review_items: Sequence[ReviewItem] = (),
    shipment_notes: Sequence[str] = (),
    calls: Sequence[ModelCall] = (),
) -> ConsistencyOutcome:
    """The drafted lines, exactly as they arrived, with an account of why."""
    return ConsistencyOutcome(
        outcome=outcome,
        detail=detail,
        lines=tuple(
            ReconciledLine(
                line_id=line.line_id,
                description=line.description,
                code=line.code,
                supplementary_unit=line.supplementary_unit,
            )
            for line in lines
        ),
        review_items=tuple(review_items),
        shipment_notes=tuple(shipment_notes),
        calls=tuple(calls),
    )
