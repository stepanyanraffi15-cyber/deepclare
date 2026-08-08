"""The composite confidence, and the gate that decides a line needs a human.

**The confidence is computed here, never asked of a model.** A model asked how sure it is
answers about the text in front of it; the number that matters also depends on how well
retrieval found the code and on whether the rest of the candidate list agrees. Three
different signals, blended in fixed proportions:

    0.4 x normalized similarity
  + 0.3 x candidate agreement at the 6-digit subheading
  + 0.3 x the model's own self-report

Cosine similarity runs from -1 to 1 and a confidence runs from 0 to 1, so the similarity
is mapped before it is blended: a cosine of 0 is not zero confidence, it is the middle of
the range. The result is rounded to four places, which is more precision than the inputs
justify and exactly enough that a stored value round-trips.

These weights are the specification's, carried unchanged. Nothing in this build has
calibrated them and they are not probabilities.
"""

from __future__ import annotations

from collections.abc import Sequence

from deepclare.reference.store import Candidate

SIMILARITY_WEIGHT = 0.4
AGREEMENT_WEIGHT = 0.3
SELF_REPORT_WEIGHT = 0.3

SUBHEADING_DIGITS = 6
"""Where agreement is measured for the blend. The 6-digit subheading is the harmonized
legal level: candidates that agree there are variants of one product, and candidates that
do not are different products that merely retrieved together."""

HEADING_DIGITS = 4
"""Where agreement is measured for the review gate. A pick that its own candidate list
does not corroborate at the heading is the shape a confident wrong code takes."""

PLACES = 4


def normalized_similarity(cosine: float) -> float:
    """Map a cosine from [-1, 1] onto [0, 1]."""
    return (cosine + 1.0) / 2.0


def agreement(candidates: Sequence[Candidate], code: str, digits: int) -> float:
    """The share of the candidate list sharing the chosen code's first `digits` digits.

    Zero for an empty list: nothing agreed with the pick because nothing was there.
    """
    if not candidates:
        return 0.0
    prefix = code[:digits]
    return sum(1 for c in candidates if c.code[:digits] == prefix) / len(candidates)


def composite_confidence(
    *, similarity: float, candidates: Sequence[Candidate], code: str, self_report: float
) -> float:
    """Blend the three signals into the number the review gate reads."""
    blended = (
        SIMILARITY_WEIGHT * normalized_similarity(similarity)
        + AGREEMENT_WEIGHT * agreement(candidates, code, SUBHEADING_DIGITS)
        + SELF_REPORT_WEIGHT * self_report
    )
    return round(blended, PLACES)


def below_review_gate(
    *,
    confidence: float,
    heading_agreement: float,
    confidence_floor: float,
    heading_agreement_floor: float,
) -> bool:
    """Whether the pick needs a human to confirm it.

    Either half is sufficient. The gate is shipped enabled here; the system the
    specification describes retains it disabled with its threshold inert, which leaves
    the vendor-catalogue short-circuit as the only producer of the flag inside these
    layers and makes two of the specification's own files disagree about what sets it.
    """
    return confidence < confidence_floor or heading_agreement < heading_agreement_floor
