"""A produced value as the review surface receives it.

The review surface is handed values that other modules made. It cannot look at one and
work out where it came from: provenance and confidence are attached at the point of
production or they do not exist at all. So the only things done to a value here are
presenting it and checking that its producer attached what its origin implies.

`concept` is the join key between a value and the review items about it. Keying on the
domain concept rather than an element path is what allows that join to exist at all
before anything knows how the value will be written.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from deepclare.domain import Confidence, Provenance, Traced


class ReportedValue(BaseModel):
    """One value that reached the draft, together with the account attached to it.

    `shown` is the value as text. A report is text, and the review surface has no
    business knowing whether a weight was a `Decimal` or a quantity a string — the typed
    value stays in the declaration, and this is its printed form.
    """

    model_config = ConfigDict(frozen=True)

    concept: str = Field(min_length=1)
    """A domain concept name — "line gross weight" — never an XML element name."""

    shown: str
    provenance: Provenance
    confidence: Confidence
    line_id: str | None = None
    """The goods line this value belongs to, or None for shipment-level values."""


def reported(
    concept: str, traced: Traced[Any], line_id: str | None = None
) -> ReportedValue:
    """Present a traced domain value to the review surface.

    Nothing is added on the way: the provenance and the three confidences are the ones
    the producer attached, and a producer that attached nothing produces a value that
    says so.
    """
    return ReportedValue(
        concept=concept,
        shown=str(traced.value),
        provenance=traced.provenance,
        confidence=traced.confidence,
        line_id=line_id,
    )
