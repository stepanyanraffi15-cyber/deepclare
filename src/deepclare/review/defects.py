"""Producer faults, surfaced instead of papered over.

Two contracts hold on everything that reaches the review surface, and this module is
where they are checked. Neither can be repaired here:

1. **Provenance and graded confidence are attached at the point of production.** A value
   whose origin implies an assessment and carries none arrived broken, and the review
   surface cannot reconstruct what its producer knew. Inventing a number would turn a
   producer's bug into a confident-looking line in a report a human trusts, so the report
   names the producer instead and still shows the value.

2. **Items and values are keyed by domain concept, never by an element path.** Only the
   filing adapter knows how a value is written; a concept named `GoodsTNVEDCode` has
   leaked that contract upward into a surface that is supposed to be independent of it.

A defect does not remove anything from the report. The operator still has to act on the
item; the defect says how much the account of it can be trusted.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from deepclare.domain import ReviewItem, ValueOrigin
from deepclare.review.values import ReportedValue

REQUIRED_CONFIDENCE: dict[ValueOrigin, str | None] = {
    # Read off a page: how well it was read is exactly the open question.
    ValueOrigin.EXTRACTED: "extraction",
    # Computed by a rule: whether the inference holds is the open question.
    ValueOrigin.DERIVED: "derivation",
    # Written by a model, which is an inference however fluent the output.
    ValueOrigin.GENERATED: "derivation",
    # No reuse path exists in this product; nothing here judges one.
    ValueOrigin.REUSED: None,
    # The profile said so. There is no reading and no inference to assess.
    ValueOrigin.SUPPLIED: None,
    # Fixed by the jurisdiction or the contract. Never uncertain.
    ValueOrigin.CONSTANT: None,
}
"""Which of the three confidences each origin must carry, or None when the origin makes
none of them meaningful. Every origin is listed: a new one has to be classified here
before a value can carry it."""


class ReportDefect(BaseModel):
    """Something a producer failed to attach, named where it happened."""

    model_config = ConfigDict(frozen=True)

    concept: str = Field(min_length=1)
    line_id: str | None = None
    producing_stage: str | None = Field(
        default=None,
        description="The stage the value's provenance names, when it names one.",
    )
    problem: str = Field(min_length=1)


def defects_in_value(value: ReportedValue) -> tuple[ReportDefect, ...]:
    """Every contract this value breaks, in the value's own terms."""
    found: list[ReportDefect] = []
    leak = _element_name_leak(value.concept, value.line_id)
    if leak is not None:
        found.append(leak)

    required = REQUIRED_CONFIDENCE[value.provenance.origin]
    if required is not None and getattr(value.confidence, required) is None:
        found.append(
            ReportDefect(
                concept=value.concept,
                line_id=value.line_id,
                producing_stage=value.provenance.stage,
                problem=(
                    f"an origin of '{value.provenance.origin.value}' promises "
                    f"{required} confidence and none is attached. Its producer knew how "
                    "far to trust this value and did not say, nothing downstream can "
                    "work it out, and so it is being shown with no idea of how good "
                    "it is."
                ),
            )
        )
    return tuple(found)


def defects_in_item(item: ReviewItem) -> tuple[ReportDefect, ...]:
    """Whether this item's concept has leaked the filing contract upward."""
    leak = _element_name_leak(item.concept, item.line_id)
    return () if leak is None else (leak,)


def _element_name_leak(concept: str, line_id: str | None) -> ReportDefect | None:
    """Recognise an element name or path used where a domain concept belongs.

    A domain concept is written as prose — "line gross weight", "shipment origin
    country" — so any concept containing whitespace is accepted without further
    question. That keeps the check from firing on legitimate wording, at the cost of
    missing a leak spelled with spaces in it, which is the right way round: a false
    accusation in a report a human trusts is worse than a missed one.

    What remains is a single run-together token, and two things mark it as machine-made:
    a case boundary in the middle of it (`GoodsTNVEDCode`), or path, namespace or
    attribute punctuation (`GoodsItem/GoodsTNVEDCode`).
    """
    if any(character.isspace() for character in concept):
        return None
    looks_machine_made = _has_case_boundary(concept) or any(
        character in concept for character in "/:<>@."
    )
    if not looks_machine_made:
        return None
    return ReportDefect(
        concept=concept,
        line_id=line_id,
        problem=(
            f"'{concept}' is an element name, not a domain concept. The review surface "
            "is keyed by what a value means, so that it holds before anything decides "
            "how the value is written; naming the element here has leaked the filing "
            "contract upward, and it will read as gibberish to the operator."
        ),
    )


def _has_case_boundary(text: str) -> bool:
    """An upper-case letter immediately after a lower-case one, as in `GoodsItem`.

    Deliberately not "contains an upper-case letter": an all-capitals concept such as
    `CMR` is a word, not an identifier.
    """
    return any(
        previous.islower() and character.isupper()
        for previous, character in zip(text, text[1:])
    )
