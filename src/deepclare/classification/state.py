"""The traversal state: one object, one goods line, every slot explicit.

It lives for exactly one traversal. Nodes take it and return a new one — nothing is
mutated, so a step's inputs are still readable after it ran and the trace is the states
themselves rather than a commentary on them.

**The step log is the only slot that merges.** Its reducer is concatenation and every
node appends to it; everything else is last-write-wins. That single fact is why the
traversal needs no join semantics: nothing fans out, so no other slot can be written
twice in one step.

**Total-optional by design.** A node writes only the slots it owns, and a slot nobody
reached keeps its empty value. That is what lets the graph skip two model calls on the
printed-code path without any node knowing that the path was taken.
"""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict

from deepclare.classification.line import ClassificationLine
from deepclare.models import ModelCall
from deepclare.reference.store import Candidate


class StepRecord(BaseModel):
    """What one node did, in the words of the node that did it.

    Append-only and never read back as a decision — with one exception the specification
    names: after the dead-end reset has cleared the printed prefix, the log is the only
    place the attempted prefix survives.
    """

    model_config = ConfigDict(frozen=True)

    node: str
    detail: str
    call: ModelCall | None = None
    """The account of the model call this node made, when it made one. A node that
    decided without a model leaves it empty, which is how a trace shows what a run
    cost."""


class GraphOutcome(BaseModel):
    """The traversal's decision about the line, before it becomes a domain record.

    Internal to the graph. It carries the prompt identity alongside the code because the
    provenance of a generated value is attached where the value is produced, and by the
    time this reaches the record the call is out of scope.
    """

    model_config = ConfigDict(frozen=True)

    code: str | None = None
    confidence: float = 0.0
    rationale: str
    needs_review: bool = True
    supplementary_unit: str | None = None
    legal_basis: str | None = None
    material_decisive: bool = False
    material_assumed: str | None = None
    resolving_evidence: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None


class TraversalState(BaseModel):
    """Everything one traversal knows, at one moment."""

    model_config = ConfigDict(frozen=True)

    line: ClassificationLine
    """Written by the initial state only. Read by every node."""

    primary_chapter: str | None = None
    """The first-choice chapter. Retained for the trace; nothing branches on it."""

    chapters: tuple[str, ...] = ()
    """One or two 2-digit chapters. Two, not one, because a chapter mis-pick filters the
    correct code out of retrieval entirely and nothing downstream recovers it."""

    headings: tuple[str, ...] = ()
    subheadings: tuple[str, ...] = ()
    """A soft preference, marked on matching candidates and never used to filter them."""

    printed_prefix: str | None = None
    """The 6-digit harmonized prefix of a code printed on the invoice. Set by the fast
    path, cleared by the dead-end reset — and clearing it is the loop guard, because it
    is the slot the entry branch tests."""

    query: str = ""
    candidates: tuple[Candidate, ...] = ()
    retrieval_scope: str | None = None
    """Which scope actually produced the candidates, and which were tried before it."""

    result: GraphOutcome | None = None
    verification_rejected: bool = False
    steps: tuple[StepRecord, ...] = ()

    def advance(self, node: str, detail: str, call: ModelCall | None = None, **slots: Any) -> Self:
        """The next state: the slots this node owns, plus its entry in the step log.

        Every node returns through here, so the log cannot be forgotten and cannot be
        overwritten.
        """
        return self.model_copy(
            update={
                **slots,
                "steps": self.steps + (StepRecord(node=node, detail=detail, call=call),),
            }
        )
