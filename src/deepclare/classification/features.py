"""The behaviour switches of code assignment, as an explicit argument.

No module here reads ambient process configuration. A switch reaches a run as an input,
so two runs of the same build can differ and each can say how it was configured.

Every default below is a decision with a reason, and the reasons are recorded because
three of them contradict something in the specification.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClassificationFeatures(BaseModel):
    """What is on, what is off, and how wide retrieval runs."""

    model_config = ConfigDict(frozen=True)

    printed_code_fast_path: bool = True
    """Take the chapter and heading from a commodity code printed on the invoice line.
    Measured on a nine-line live run: taken 9/9, correct at both 6 and 10 digits 9/9,
    with both narrowing calls skipped. A misread code would strand the line in the wrong
    subtree forever, which is what the dead-end reset exists for."""

    subheading_preference: bool = False
    """Ask for 1-2 likely 6-digit subheadings and mark the candidates that match. Off,
    which is the specification's shipped default. It cannot remove a candidate, so it is
    safe to enable; nothing in this build has measured whether it helps."""

    verification: bool = False
    """A second, veto-only opinion on the chosen code. Off, which is the specification's
    shipped default, and the measured record is why: on the widest recorded configuration
    the verifier was right once and costly four times, and its usefulness degrades
    monotonically as the candidate list widens. It is implemented and switchable so that
    re-measuring it is a flag rather than a build."""

    candidate_limit: int = Field(default=30, gt=0)
    """How many candidates the final pick sees.

    Thirty, because ten was measured to be a ceiling. Retrieval recall was measured on
    60 goods lines from the evaluation corpus, scoped to the correct heading, asking only
    whether the expected code appears at all:

        k=5   58.3%      k=20   80.0%
        k=10  68.3%      k=30   86.7%
        k=15  76.7%      k=50   96.7%

    At ten, **one correct code in three is never shown to the model**, and no amount of
    model quality recovers a candidate that was truncated before the pick. The ranks
    beyond ten run 11, 12, 14, 15, 17, 20, 22, 23, 27, 28, 31 … 76, which is the same
    shape the specification describes for its own recorded accuracy jump.

    Thirty rather than fifty because a longer list costs prompt budget and the
    specification warns that too deep a list degrades the pick. Fifty buys another ten
    points of ceiling and is the obvious next thing to measure once end-to-end scoring
    runs against the corpus."""

    review_below_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    """Flag the line for review when the composite confidence falls below this. Enabled,
    unlike the system this specification describes, where the gate is present, disabled,
    and its threshold inert — which is why two of the specification's own files disagree
    about when the flag is set. Enabling it makes them agree."""

    review_below_heading_agreement: float = Field(default=0.5, ge=0.0, le=1.0)
    """The second half of the same gate: flag when fewer than this share of the retrieved
    candidates agree with the pick at the 4-digit heading. A pick that its own candidate
    list does not corroborate at the heading is the confident-wrong-code shape."""
