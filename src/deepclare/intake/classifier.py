"""The page-type classifier, as a port.

Intake needs one judgement it cannot make itself: which document each rendered page
belongs to. It states the shape of that call here and never makes it. Which model reads
a page, under which prompt, at which tier and at what cost is not intake's business —
a caller injects an implementation.

The port promises nothing about completeness, and an implementation must not pretend
otherwise. Verdicts may be missing, repeated, or numbered outside the batch; the grouper
is built to survive all three. Padding the list to look complete, or inventing a verdict
for a page the model did not answer for, hides a real signal and changes nothing about
where the page lands.

Intake imposes no page cap and does no batching: it hands over every rendered page of the
submission at once. On a long bundle that is a real scaling hazard, and how to spend it —
one call or several — is the implementation's decision, not intake's.

`PageVerdict` is the port's own type and must not be handed to a provider as an output
schema. Its field notes, and the docstring of the domain enumeration it names, become
`description` entries in a generated JSON schema — that is prompt text, and prompt text
lives in the prompt files. An implementation defines its own prose-free answer shape and
maps it onto this one, as the reading stage does.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from deepclare.domain import PageClass
from deepclare.intake.rasterizer import RenderedPage


class PageVerdict(BaseModel):
    """One classifier answer: a page of the batch, and what it looks like."""

    model_config = ConfigDict(frozen=True)

    page: int = Field(
        ge=1,
        description="1-based position in the batch of pages that was presented, not the "
        "page number inside its source file.",
    )
    page_type: PageClass


@runtime_checkable
class PageTypeClassifier(Protocol):
    """Judges a batch of rendered pages. Implemented outside intake."""

    def classify(self, pages: Sequence[RenderedPage]) -> Sequence[PageVerdict]:
        """Return a verdict per page, in batch order.

        The pages carry their own role hints; whether and how to show them to a model is
        the implementation's decision.
        """
        ...
