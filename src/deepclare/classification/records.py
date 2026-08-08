"""What code assignment produces for one goods line, and how a traversal becomes it.

One code or an abstention with its rationale; a confidence; the candidate set; the
supplementary unit read off the chosen entry; the legal basis; and the per-step trace of
the traversal that produced it.

**No review item is built here.** This module must not know the review vocabulary — that
boundary is stated in the specification's module decomposition and it is load-bearing: a
classifier that writes review items has an opinion about how a declaration is presented.
What it produces instead is the flag and the rationale a review item is built *from*,
which is what the field semantics ask for. Assembly turns them into items.

The confidence is not a field of its own. It is read off the traced code, so the number
the review gate acted on and the number attached to the value can never drift apart, and
stripping the code takes its confidence with it without anyone having to remember to.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from deepclare.classification.errors import ClassificationError
from deepclare.classification.state import GraphOutcome, StepRecord, TraversalState
from deepclare.domain import Confidence, Provenance, Traced, ValueOrigin
from deepclare.models import ModelCall
from deepclare.reference.store import Candidate

STAGE = "classification"
"""What every value produced here names as its producing stage."""

VENDOR_CATALOGUE_LAYER = "vendor catalogue"
CODE_ASSIGNMENT_LAYER = "code assignment graph"
EXISTENCE_GATE_LAYER = "existence gate"


class LineClassification(BaseModel):
    """One goods line's commodity code, or its absence and the reason for it."""

    model_config = ConfigDict(frozen=True)

    line_id: str = Field(pattern=r"^[1-9][0-9]*$")

    code: Traced[str] | None = None
    """The 10-digit leaf. `None` is an abstention, and the rationale says why. The 11th
    national digit is appended downstream: the filed form is assembly's business."""

    needs_review: bool = True
    """Whether a human must confirm the outcome before it is filed."""

    rationale: str = Field(min_length=1)
    """Why this outcome. Mandatory always, and on an abstention it is the only thing the
    operator gets — so an abstention on a material split names each material branch with
    its code, and `resolving_evidence` says what would settle it."""

    supplementary_unit: str | None = None
    """The nomenclature's own unit for the chosen code, as it states it. Tier one of unit
    resolution downstream; absent for most codes, which is normal."""

    legal_basis: str | None = None
    """The General Interpretation Rule or chapter note the claim rests on, or the layer
    that supplied the code, when one was named."""

    material_decisive: bool = False
    """Whether the candidates separated along a material or composition axis. It must
    survive a verification veto: the flow that asks the operator to state the material
    keys on it, and a veto is exactly when that question still needs asking."""

    material_assumed: str | None = None
    """The material the choice rests on, in the line's own words. Never derived from a
    brand, and never present unless the line stated it."""

    resolving_evidence: str | None = None
    """What a human would have to state for this line to be classifiable. Present on an
    abstention a fact would resolve; absent when nothing would."""

    candidates: tuple[Candidate, ...] = ()
    """The retrieval shortlist, retained on an abstention too — what the model declined
    is part of the audit trail, and a line that retrieved nothing is a different failure
    from a line that retrieved ten wrong things."""

    steps: tuple[StepRecord, ...] = ()
    """The traversal, node by node, in the order it ran."""

    decided_by: str = Field(min_length=1)
    """Which layer produced this outcome."""

    @property
    def confidence(self) -> float:
        """The composite confidence, or zero when there is no code to be confident about."""
        if self.code is None:
            return 0.0
        assessed = self.code.confidence.derivation
        return 0.0 if assessed is None else assessed

    @property
    def abstained(self) -> bool:
        return self.code is None

    @property
    def calls(self) -> tuple[ModelCall, ...]:
        """Every model call the traversal made, in order."""
        return tuple(step.call for step in self.steps if step.call is not None)


def classification_from_traversal(state: TraversalState) -> LineClassification:
    """Turn a finished traversal into the record that leaves this module."""
    outcome = state.result
    if outcome is None:
        raise ClassificationError(
            f"line {state.line.line_id}: the traversal ended without a result. Every "
            "path through the graph writes one, so this is a defect in the graph "
            "declaration rather than a property of the goods line."
        )
    return LineClassification(
        line_id=state.line.line_id,
        code=_traced_code(outcome),
        needs_review=outcome.needs_review,
        rationale=outcome.rationale,
        supplementary_unit=outcome.supplementary_unit,
        legal_basis=outcome.legal_basis,
        material_decisive=outcome.material_decisive,
        material_assumed=outcome.material_assumed,
        resolving_evidence=outcome.resolving_evidence,
        candidates=state.candidates,
        steps=state.steps,
        decided_by=CODE_ASSIGNMENT_LAYER,
    )


def _traced_code(outcome: GraphOutcome) -> Traced[str] | None:
    """The chosen code with the account of the call that chose it.

    A code only ever exists here because a model picked it from a retrieved candidate,
    so the origin is always generated and the prompt is always known.
    """
    if outcome.code is None:
        return None
    if not outcome.prompt_name or not outcome.prompt_version:
        raise ClassificationError(
            f"a code was assigned without recording which prompt assigned it: "
            f"{outcome.code}. A generated value that cannot name its prompt has no "
            "provenance, and the review surface cannot reconstruct one."
        )
    return Traced[str](
        value=outcome.code,
        provenance=Provenance(
            origin=ValueOrigin.GENERATED,
            stage=STAGE,
            prompt_name=outcome.prompt_name,
            prompt_version=outcome.prompt_version,
        ),
        confidence=Confidence(derivation=outcome.confidence),
    )
