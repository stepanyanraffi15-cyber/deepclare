"""The seam. What a run holds, and the only thing a run ever calls.

Dossier 10 §3 M17: this layer **must not know how to change behaviour**. It is strictly
read-only with respect to the run, and no production behaviour may vary on whether
tracing is enabled. Two structural facts hold that, rather than a comment asking for it:

* **Every method returns `None`.** `stage()` yields nothing and `node()` yields a draft
  that has setters and no getters. There is no value a run could branch on, so no branch
  can depend on tracing being on — the prohibition is backed by omission and cannot be
  violated by a caller who forgets it.
* **The recorder is handed to the run; it never reaches back.** It holds no port, calls
  no module, and reads nothing the run produced except what the run passes it.

`trace()` is the one method that returns something, and it is for after the run.

Capture volume, redaction and retention are the three policies this object carries; each
is a value, each is recorded in the manifest or the trace, and none of them is a global.
One recorder is one run's worth of observation.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from deepclare.models import ModelCall
from deepclare.trace.capture import CapturePolicy
from deepclare.trace.errors import TraceError
from deepclare.trace.identity import SequenceCounter
from deepclare.trace.manifest import RunManifest
from deepclare.trace.records import (
    AbstentionKind,
    CapturedPayload,
    NodeOutcome,
    NodeTrace,
    Retrieval,
    RunTrace,
    SupersededValue,
)
from deepclare.trace.redaction import IdentityValue, Redactor
from deepclare.trace.retention import ArtifactRef, RetentionPolicy
from deepclare.trace.sink import TraceSink


class NodeDraft:
    """What a node says about itself while it runs. Write-only.

    Nothing on this object reads back. A node can tell the trace what it decided; it
    cannot ask the trace what it decided, which is what keeps the observation layer
    incapable of steering the run.
    """

    def __init__(self) -> None:
        self._decision = ""
        self._abstention: AbstentionKind | None = None
        self._degradation: str | None = None
        self._call: ModelCall | None = None
        self._retrieval: Retrieval | None = None
        self._superseded: list[SupersededValue] = []
        self._exit_state: Mapping[str, object] | None = None
        self._prompt: str | None = None
        self._response: str | None = None

    def decided(self, decision: str) -> None:
        """What this node concluded, in its own words."""
        self._decision = decision

    def abstained(self, kind: AbstentionKind, why: str) -> None:
        """Nothing was chosen, and which of the two abstentions this was.

        "No candidates existed" and "candidates existed and none was chosen" are
        different events; merging them into one empty output loses the distinction that
        says whether retrieval or judgement failed.
        """
        self._abstention = kind
        self._decision = why

    def degraded(self, why: str) -> None:
        """A fallback path was taken, and why."""
        self._degradation = why

    def model_call(self, call: ModelCall) -> None:
        """The account the model adapter already returned for this node's call."""
        self._call = call

    def retrieved(self, retrieval: Retrieval) -> None:
        """The candidate list this node decided among, with scores."""
        self._retrieval = retrieval

    def superseded(self, *, slot: str, previous: str, reason: str) -> None:
        """A slot this node cleared or overwrote, and what it held before."""
        self._superseded.append(
            SupersededValue(slot=slot, previous=previous, reason=reason)
        )

    def exited(self, state: Mapping[str, object]) -> None:
        """The state this node hands on. Captured only at the state level or above."""
        self._exit_state = state

    def captured(self, *, prompt: str | None = None, response: str | None = None) -> None:
        """What the model was shown and what it said. Payload level only, always masked."""
        self._prompt = prompt
        self._response = response

    def _seal(self) -> _DraftContents:
        """Everything the draft was told, for the recorder in this module to write.

        The one way back out, and it is private: the recorder is the only reader, and a
        node holding a draft has no method that returns anything.
        """
        return _DraftContents(
            decision=self._decision,
            abstention=self._abstention,
            degradation=self._degradation,
            call=self._call,
            retrieval=self._retrieval,
            superseded=tuple(self._superseded),
            exit_state=self._exit_state,
            prompt=self._prompt,
            response=self._response,
        )


@dataclass(frozen=True)
class _DraftContents:
    """A sealed draft. Never leaves this module."""

    decision: str
    abstention: AbstentionKind | None
    degradation: str | None
    call: ModelCall | None
    retrieval: Retrieval | None
    superseded: tuple[SupersededValue, ...]
    exit_state: Mapping[str, object] | None
    prompt: str | None
    response: str | None


class TraceRecorder:
    """One run's observation seam."""

    def __init__(
        self,
        *,
        run_id: str,
        case_id: str,
        manifest: RunManifest,
        capture: CapturePolicy,
        retention: RetentionPolicy,
        sink: TraceSink,
        identities: Iterable[IdentityValue] = (),
    ) -> None:
        if manifest.run_id != run_id:
            raise TraceError(
                f"the manifest is for run {manifest.run_id!r} and this recorder is for "
                f"{run_id!r}. A record stamped with another run's pinned versions "
                "explains the wrong run."
            )
        self._run_id = run_id
        self._case_id = case_id
        self._manifest = manifest
        self._capture = capture
        self._retention = retention
        self._sink = sink
        self._identities: list[IdentityValue] = list(identities)
        self._redactor = Redactor(self._identities)
        self._sequence = SequenceCounter()
        self._nodes: list[NodeTrace] = []
        self._artifacts: list[ArtifactRef] = []
        self._notes: list[str] = []
        self._stage: str | None = None
        self._started_at = datetime.now(UTC)
        self._finished_at: datetime | None = None

    # --- what a run calls ----------------------------------------------------

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Bind the current stage so every node inside it is stamped with it.

        Yields nothing. The binding is for the sequential outer chain; a concurrent
        worker names its stage on the node call instead.
        """
        previous = self._stage
        self._stage = name
        try:
            yield None
        finally:
            self._stage = previous

    @contextmanager
    def node(
        self,
        name: str,
        *,
        stage: str | None = None,
        line_id: str | None = None,
        entry_state: Mapping[str, object] | None = None,
        attempt: int = 1,
    ) -> Iterator[NodeDraft]:
        """Observe one node traversal. Records on the way out, including on failure.

        A node that raises still gets a record: it has already spent its tokens, and a
        run that dies mid-pipeline is exactly the run whose trace is worth having.
        """
        draft = NodeDraft()
        # Checked before the capture level is consulted, so a mis-wired call is refused
        # identically whatever the level. A defect that appears only when tracing is
        # turned up is a behaviour that varies on tracing.
        stage_name = stage or self._stage
        if not stage_name:
            raise TraceError(
                f"node {name!r} was recorded outside any stage. Bind one with "
                "`recorder.stage(...)` or name it on the call; an unstamped record "
                "cannot be read as part of a flow."
            )
        if not self._capture.records_nodes:
            yield draft
            return

        sequence = self._sequence.take()
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        try:
            yield draft
        except BaseException as exc:
            self._record(
                draft,
                name=name,
                stage=stage_name,
                line_id=line_id,
                sequence=sequence,
                started_at=started_at,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                entry_state=entry_state,
                attempt=attempt,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        else:
            self._record(
                draft,
                name=name,
                stage=stage_name,
                line_id=line_id,
                sequence=sequence,
                started_at=started_at,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                entry_state=entry_state,
                attempt=attempt,
                error=None,
            )

    def learn_identities(self, identities: Iterable[IdentityValue]) -> None:
        """Tell the redactor which identity strings this run is handling.

        A run learns the parties only once it has read the documents, so the redactor is
        extended rather than constructed complete. Records written **before** this call
        are not revisited: nothing in this package rewrites a record. Call it as soon as
        a document has been read, and before any payload from it is captured.
        """
        self._identities.extend(identities)
        self._redactor = Redactor(self._identities)

    def note(self, text: str) -> None:
        """One sentence about the run that no node record carries."""
        self._notes.append(self._redactor.mask_text(text))

    def artifact(self, reference: ArtifactRef) -> None:
        """Record that an artifact was retained. The store wrote it; this indexes it."""
        self._artifacts.append(reference)

    def finish(self) -> None:
        """Close the run's account of itself. The sink belongs to the caller and is not
        closed here."""
        self._finished_at = datetime.now(UTC)

    # --- what is read afterwards --------------------------------------------

    def trace(self) -> RunTrace:
        """The run's whole account of itself. Read after the run, never during."""
        return RunTrace(
            run_id=self._run_id,
            case_id=self._case_id,
            started_at=self._started_at,
            finished_at=self._finished_at,
            manifest=self._manifest,
            capture=self._capture,
            retention=self._retention,
            nodes=tuple(self._nodes),
            artifacts=tuple(self._artifacts),
            notes=tuple(self._notes),
        )

    # --- internals -----------------------------------------------------------

    def _record(
        self,
        draft: NodeDraft,
        *,
        name: str,
        stage: str,
        line_id: str | None,
        sequence: int,
        started_at: datetime,
        elapsed_ms: float,
        entry_state: Mapping[str, object] | None,
        attempt: int,
        error: str | None,
    ) -> None:
        sealed = draft._seal()
        sampled = self._capture.samples(run_id=self._run_id, sequence=sequence)
        keep_states = self._capture.captures_states and sampled
        keep_payloads = self._capture.captures_payloads and sampled

        record = NodeTrace(
            run_id=self._run_id,
            case_id=self._case_id,
            line_id=line_id,
            stage=stage,
            node=name,
            sequence=sequence,
            recorded_at=started_at,
            wall_clock_ms=elapsed_ms,
            outcome=_outcome(sealed, error),
            decision=self._redactor.mask_text(sealed.decision),
            abstention=sealed.abstention,
            degradation=(
                self._redactor.mask_text(sealed.degradation)
                if sealed.degradation
                else None
            ),
            error=self._redactor.mask_text(error) if error else None,
            attempt=attempt,
            call=sealed.call,
            retrieval=sealed.retrieval,
            superseded=sealed.superseded,
            entry_state=(
                self._redactor.mask(entry_state) if keep_states and entry_state else None
            ),
            exit_state=(
                self._redactor.mask(sealed.exit_state)
                if keep_states and sealed.exit_state
                else None
            ),
            payload=self._payload(sealed) if keep_payloads else None,
            sampled=sampled,
        )
        self._nodes.append(record)
        self._sink.append(record)

    def _payload(self, sealed: _DraftContents) -> CapturedPayload | None:
        if sealed.prompt is None and sealed.response is None:
            return None
        prompt, prompt_cut = self._capture_text(sealed.prompt)
        response, response_cut = self._capture_text(sealed.response)
        return CapturedPayload(
            prompt=prompt,
            response=response,
            truncated=prompt_cut or response_cut,
        )

    def _capture_text(self, text: str | None) -> tuple[str | None, bool]:
        if text is None:
            return None, False
        masked = self._redactor.mask_text(text)
        kept, truncated = self._capture.truncate(masked)
        return kept, truncated


def _outcome(sealed: _DraftContents, error: str | None) -> NodeOutcome:
    """Failure first, then abstention, then degradation.

    A node that abstained *and* fell back is reported as an abstention, because that is
    what happened to the goods line; the fallback is still on the record in its own
    field, which is what a fallback-path count is computed from.
    """
    if error is not None:
        return NodeOutcome.FAILED
    if sealed.abstention is not None:
        return NodeOutcome.ABSTAINED
    if sealed.degradation is not None:
        return NodeOutcome.DEGRADED
    return NodeOutcome.COMPLETED
