"""The structured records: one per node traversal, grouped per stage, one run.

Dossier 08 §16.2 fixes the contents of a node record and four properties of it:

* **Append-only, never truncated at run start.** The measured precedent deleted its trace
  file at the beginning of every run, destroying the previous run's evidence.
* **Never auto-deleted.** See `retention.py`; nothing in this package removes anything.
* **Superseded values recoverable.** When a later node clears a slot an earlier node set,
  the trace keeps both — the audit trail must survive the loop guard, and in this
  pipeline the loop guard works by clearing exactly the slot the entry branch tests.
* **Abstention semantics explicit.** "No candidates existed" and "candidates existed and
  none was chosen" are different events and are different values here, never merged into
  one empty output.

This module invents no vocabulary the producers already have. A model call is the
`ModelCall` the model adapter already returns; a retrieved candidate is the `Candidate`
the reference store already returns. What is added is the frame around them: which run,
which case, which line, which stage, in what order, how long it took, and what happened.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from deepclare.models import ModelCall
from deepclare.reference.store import Candidate
from deepclare.trace.capture import CapturePolicy
from deepclare.trace.manifest import PromptPin, RunManifest, StageModel
from deepclare.trace.retention import ArtifactRef, RetentionPolicy


class NodeOutcome(StrEnum):
    """How a node traversal ended."""

    COMPLETED = "completed"
    ABSTAINED = "abstained"
    DEGRADED = "degraded"
    """A fallback path was taken. `degradation` says which and why."""

    FAILED = "failed"
    """The node raised. Recorded, because a run that dies mid-pipeline has already spent
    its tokens and success-only accounting undercounts."""


class AbstentionKind(StrEnum):
    """Why nothing was chosen. Two different events, never one empty output."""

    NO_CANDIDATES = "no_candidates"
    NONE_CHOSEN = "none_chosen"


class RetrievedAlternative(BaseModel):
    """One candidate the decision was made among."""

    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    code: str = Field(min_length=1)
    score: float
    chosen: bool = False


class Retrieval(BaseModel):
    """The full candidate list with scores, and the rank of the correct answer if known.

    Retained on an abstention as well: what a model declined is part of the audit trail,
    and a line that retrieved nothing is a different failure from a line that retrieved
    thirty wrong things.
    """

    model_config = ConfigDict(frozen=True)

    query: str
    scope: str | None = None
    alternatives: tuple[RetrievedAlternative, ...] = ()
    known_correct_code: str | None = None
    correct_rank: int | None = None
    """Where the correct answer sat in the list, when a caller knew it. `None` on a
    production run, which knows no correct answer — and `known_correct_code` set with
    `correct_rank` empty means the correct code was not retrieved at all."""

    dropped_unknown_codes: int = Field(default=0, ge=0)
    """Vector hits whose code is absent from the metadata, as the store reported them.
    Non-zero means the two halves of the index disagree and a top-k silently under-returned."""

    @classmethod
    def from_candidates(
        cls,
        *,
        query: str,
        candidates: tuple[Candidate, ...],
        scope: str | None = None,
        chosen_code: str | None = None,
        known_correct_code: str | None = None,
        dropped_unknown_codes: int = 0,
    ) -> Retrieval:
        """Frame what the reference store returned, in retrieved order."""
        alternatives = tuple(
            RetrievedAlternative(
                rank=position,
                code=candidate.code,
                score=candidate.similarity,
                chosen=candidate.code == chosen_code,
            )
            for position, candidate in enumerate(candidates, start=1)
        )
        correct_rank = next(
            (
                alternative.rank
                for alternative in alternatives
                if alternative.code == known_correct_code
            ),
            None,
        )
        return cls(
            query=query,
            scope=scope,
            alternatives=alternatives,
            known_correct_code=known_correct_code,
            correct_rank=correct_rank,
            dropped_unknown_codes=dropped_unknown_codes,
        )


class SupersededValue(BaseModel):
    """A slot a later node cleared or overwrote, and what it held before.

    The one case in this pipeline that makes it necessary: the dead-end reset clears the
    printed commodity-code prefix, which is both the loop guard and the only record that
    the fast path was ever taken.
    """

    model_config = ConfigDict(frozen=True)

    slot: str = Field(min_length=1)
    previous: str
    reason: str = Field(min_length=1)


class CapturedPayload(BaseModel):
    """What the model was actually shown, and what it actually said.

    Present only at the payload capture level, always masked, and truncated at the
    declared cap unless the cap was disabled.
    """

    model_config = ConfigDict(frozen=True)

    prompt: str | None = None
    response: str | None = None
    truncated: bool = False
    redacted: bool = True


class NodeTrace(BaseModel):
    """One durable record of one node traversal."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    line_id: str | None = None
    stage: str = Field(min_length=1)
    node: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    recorded_at: datetime
    wall_clock_ms: float = Field(ge=0.0)

    outcome: NodeOutcome
    decision: str = ""
    """What the node decided, in the node's own words. Masked like everything else."""

    abstention: AbstentionKind | None = None
    degradation: str | None = None
    error: str | None = None
    attempt: int = Field(default=1, ge=1)

    call: ModelCall | None = None
    retrieval: Retrieval | None = None
    superseded: tuple[SupersededValue, ...] = ()

    entry_state: dict[str, Any] | None = None
    exit_state: dict[str, Any] | None = None
    """Captured state, masked and JSON-safe. A dictionary rather than a typed model
    because a node's state is whatever that node holds; this is capture, not a stage
    boundary."""

    payload: CapturedPayload | None = None
    sampled: bool = True
    """Whether the content levels were kept for this node. False means the record is
    complete but its states and payload were sampled away."""


class TokenTotals(BaseModel):
    """What a stage or a run cost, in tokens. Money is computed at report time from a
    pinned price table, never frozen into a record."""

    model_config = ConfigDict(frozen=True)

    calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0


def _totals(calls: tuple[ModelCall, ...]) -> TokenTotals:
    return TokenTotals(
        calls=len(calls),
        prompt_tokens=sum(call.usage.prompt_tokens or 0 for call in calls),
        output_tokens=sum(call.usage.output_tokens or 0 for call in calls),
        reasoning_tokens=sum(call.usage.reasoning_tokens or 0 for call in calls),
        total_tokens=sum(call.usage.total_tokens or 0 for call in calls),
    )


class StageRecord(BaseModel):
    """One stage's node traversals, in the order they ran."""

    model_config = ConfigDict(frozen=True)

    stage: str = Field(min_length=1)
    nodes: tuple[NodeTrace, ...] = ()

    @property
    def wall_clock_ms(self) -> float:
        return sum(node.wall_clock_ms for node in self.nodes)

    @property
    def calls(self) -> tuple[ModelCall, ...]:
        return tuple(node.call for node in self.nodes if node.call is not None)

    @property
    def tokens(self) -> TokenTotals:
        return _totals(self.calls)

    @property
    def abstentions(self) -> int:
        return sum(1 for node in self.nodes if node.outcome is NodeOutcome.ABSTAINED)

    @property
    def degradations(self) -> int:
        return sum(1 for node in self.nodes if node.outcome is NodeOutcome.DEGRADED)

    @property
    def failures(self) -> int:
        return sum(1 for node in self.nodes if node.outcome is NodeOutcome.FAILED)


class RunTrace:
    """One run's whole account of itself: the manifest, the policies, and every node.

    A plain class rather than a model because everything on it is a projection of the
    node list. It is built by the recorder at the end of a run and read afterwards;
    nothing on the run path holds one.
    """

    def __init__(
        self,
        *,
        run_id: str,
        case_id: str,
        started_at: datetime,
        finished_at: datetime | None,
        manifest: RunManifest,
        capture: CapturePolicy,
        retention: RetentionPolicy,
        nodes: tuple[NodeTrace, ...],
        artifacts: tuple[ArtifactRef, ...] = (),
        notes: tuple[str, ...] = (),
    ) -> None:
        self.run_id = run_id
        self.case_id = case_id
        self.started_at = started_at
        self.finished_at = finished_at
        self.manifest = manifest
        self.capture = capture
        self.retention = retention
        self.nodes = nodes
        self.artifacts = artifacts
        self.notes = notes

    # --- projections ---------------------------------------------------------

    @property
    def stages(self) -> tuple[StageRecord, ...]:
        """The stages in the order they were first entered."""
        grouped: dict[str, list[NodeTrace]] = {}
        for node in self.nodes:
            grouped.setdefault(node.stage, []).append(node)
        return tuple(
            StageRecord(stage=stage, nodes=tuple(nodes))
            for stage, nodes in grouped.items()
        )

    def line(self, line_id: str) -> tuple[NodeTrace, ...]:
        """One goods line's whole journey, retrievable by itself."""
        return tuple(node for node in self.nodes if node.line_id == line_id)

    @property
    def calls(self) -> tuple[ModelCall, ...]:
        return tuple(node.call for node in self.nodes if node.call is not None)

    @property
    def tokens(self) -> TokenTotals:
        return _totals(self.calls)

    @property
    def wall_clock_ms(self) -> float:
        return sum(node.wall_clock_ms for node in self.nodes)

    # --- what actually answered, against what was declared -------------------

    def observed_models(self) -> tuple[StageModel, ...]:
        """The model that served each stage, read off the calls that were made."""
        seen: dict[tuple[str, str, str, str | None], StageModel] = {}
        for node in self.nodes:
            if node.call is None:
                continue
            call = node.call
            key = (node.stage, call.tier.value, call.model_id, call.model_version)
            seen.setdefault(
                key,
                StageModel(
                    stage=node.stage,
                    tier=call.tier.value,
                    model_id=call.model_id,
                    model_version=call.model_version,
                    decoding=call.decoding,
                ),
            )
        return tuple(seen.values())

    def observed_prompts(self) -> tuple[PromptPin, ...]:
        """Every prompt that was actually rendered, by name, version and stage."""
        seen: dict[tuple[str, str, str], PromptPin] = {}
        for node in self.nodes:
            if node.call is None:
                continue
            call = node.call
            key = (call.prompt_name, call.prompt_version, node.stage)
            seen.setdefault(
                key,
                PromptPin(
                    name=call.prompt_name,
                    version=call.prompt_version,
                    stage=node.stage,
                ),
            )
        return tuple(seen.values())

    def pin_drift(self) -> tuple[str, ...]:
        """Where what answered disagrees with what the manifest declared.

        A manifest is a claim; the calls are the evidence. A model id pinned in the
        manifest and a different one on the wire is the shape of an unattributable
        accuracy movement, so it is named rather than left to be noticed.
        """
        drift: list[str] = []
        declared_models = {
            (stage.stage, stage.model_id) for stage in self.manifest.models.stages
        }
        declared_stages = {stage.stage for stage in self.manifest.models.stages}
        for observed in self.observed_models():
            if (observed.stage, observed.model_id) in declared_models:
                continue
            if observed.stage in declared_stages:
                drift.append(
                    f"stage {observed.stage!r} ran on {observed.model_id!r}, which the "
                    "manifest does not pin for that stage"
                )
            else:
                drift.append(
                    f"stage {observed.stage!r} made model calls and the manifest pins no "
                    "model for it"
                )

        declared_prompts = {(pin.name, pin.version) for pin in self.manifest.prompts}
        for prompt in self.observed_prompts():
            if (prompt.name, prompt.version) not in declared_prompts:
                drift.append(
                    f"prompt {prompt.name!r} version {prompt.version} was rendered and is "
                    "not pinned in the manifest"
                )
        return tuple(drift)
