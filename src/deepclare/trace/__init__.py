"""M17 Trace and Evaluation — the observation layer.

Dossier 10 §3 M17. In: an observation stream from every module through one defined seam
per module, including the model-call seam and the reference-data query seam. Out: run
identifiers, per-node input/output capture, retained artifacts, structured per-stage
records, and the pinned versions that explain a result.

**Must not know: how to change behaviour.** It is strictly read-only with respect to the
run. No production behaviour may vary on whether tracing is enabled, and no evaluation
path may be reachable from a production run. The seam is `TraceRecorder`, and every
method on it returns `None`: there is no value a run could branch on, so the prohibition
is backed by omission rather than by instruction.

**It depends on no producing module.** Dossier 10 §5: M17 requires M1, the seam
definitions, and M4 for version pinning, and nothing else — each module carries its own
seam, so the trace never reaches into one. Concretely, this package imports the domain
vocabulary, the model-call account the model adapter already returns, and the candidate
shape the reference store already returns. It imports no stage, and it wires nothing:
what to record is the orchestrator's decision.

Four invariants, each with a mechanism rather than a rule:

* **Every version that could explain a result is pinned per run.** `RunManifest`, seven
  axes, and `compare_manifests` applying the attribution rule to two of them. An axis
  nothing publishes is `UNPINNED` and is listed, never invented.
* **Capture volume is explicitly controllable.** `CapturePolicy` — four levels, a
  truncation cap that can be disabled, and a sampling rate — because captured payloads
  contain customer document content and land in durable sinks.
* **Redaction is mandatory at every level.** `Redactor`, keyed off the domain's own
  field names, with no way to switch it off.
* **Retention is explicit and never automatic.** No function in this package deletes a
  trace or an artifact, and overwriting a retained artifact is refused.

**What is not here.** Golden sets, metric definitions, the judge harness and the
published report of dossier 08 §§9-13 and §17 are not built. This package is the
observation layer they would be computed from; nothing here scores anything, and nothing
here has a stub that looks as though it does.
"""

from deepclare.trace.capture import (
    DEFAULT_TRUNCATION_CHARS,
    CaptureLevel,
    CapturePolicy,
)
from deepclare.trace.errors import TraceError
from deepclare.trace.identity import SequenceCounter, new_case_id, new_run_id
from deepclare.trace.manifest import (
    AXIS_NAMES,
    UNPINNED,
    AttributionVerdict,
    CodePins,
    ConfigurationPins,
    DataPins,
    EnvironmentPins,
    EvaluationPins,
    ManifestComparison,
    ModelPins,
    Pin,
    PromptPin,
    RunManifest,
    StageModel,
    compare_manifests,
)
from deepclare.trace.recorder import NodeDraft, TraceRecorder
from deepclare.trace.records import (
    AbstentionKind,
    CapturedPayload,
    NodeOutcome,
    NodeTrace,
    RetrievedAlternative,
    Retrieval,
    RunTrace,
    StageRecord,
    SupersededValue,
    TokenTotals,
)
from deepclare.trace.redaction import (
    IDENTITY_FIELDS,
    IdentityClass,
    IdentityValue,
    Redactor,
    identities_in,
    identity_leaks,
)
from deepclare.trace.rendering import render_trace
from deepclare.trace.retention import (
    ArtifactKind,
    ArtifactRef,
    ArtifactStore,
    RetentionPolicy,
)
from deepclare.trace.sink import (
    JsonlTraceSink,
    MemoryTraceSink,
    TraceSink,
    read_trace_file,
)

__all__ = [
    "AXIS_NAMES",
    "AbstentionKind",
    "ArtifactKind",
    "ArtifactRef",
    "ArtifactStore",
    "AttributionVerdict",
    "CaptureLevel",
    "CapturePolicy",
    "CapturedPayload",
    "CodePins",
    "ConfigurationPins",
    "DEFAULT_TRUNCATION_CHARS",
    "DataPins",
    "EnvironmentPins",
    "EvaluationPins",
    "IDENTITY_FIELDS",
    "IdentityClass",
    "IdentityValue",
    "JsonlTraceSink",
    "ManifestComparison",
    "MemoryTraceSink",
    "ModelPins",
    "NodeDraft",
    "NodeOutcome",
    "NodeTrace",
    "Pin",
    "PromptPin",
    "Redactor",
    "RetentionPolicy",
    "Retrieval",
    "RetrievedAlternative",
    "RunManifest",
    "RunTrace",
    "SequenceCounter",
    "StageModel",
    "StageRecord",
    "SupersededValue",
    "TokenTotals",
    "TraceError",
    "TraceRecorder",
    "TraceSink",
    "UNPINNED",
    "compare_manifests",
    "identities_in",
    "identity_leaks",
    "new_case_id",
    "new_run_id",
    "read_trace_file",
    "render_trace",
]
