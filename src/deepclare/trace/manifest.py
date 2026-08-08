"""Every version that could explain a result, pinned per run.

Dossier 08 §14.1 lists the axes and §14.2 states the rule they exist for:

    A metric change is attributable only if exactly one manifest axis differs between
    the two runs. If more than one differs, the result is reported as a compound change
    and no single cause is claimed.

That is not bookkeeping. The measured precedents are specific: one experiment shipped
three changes together and could attribute its improvement only by reading a failure
funnel; a later batch records that its comparison is "not a strict A/B"; and one
regression across every metric has no record of what changed at all and is permanently
unattributable. The corollary that bites this product hardest — a data change and a model
change must never ship in the same measured comparison, because without the nomenclature
vintage and the index build pinned, an accuracy movement cannot be assigned to the model
or to the data, which is the exact question the pinning exists to answer.

**A pin that is not known says so.** `UNPINNED` is the declared value for an axis element
nothing in this build publishes yet, and `RunManifest.unpinned()` lists every one of
them. An invented version string would make two different runs look identical, which is
worse than a run that admits what it could not pin.

Nothing here is redacted, and nothing here needs to be: a manifest holds versions,
thresholds and model identifiers. Document content lives in the node records.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from deepclare.models import Decoding
from deepclare.trace.capture import CapturePolicy

UNPINNED = "unknown"
"""What an axis element carries when nothing in this build publishes a version for it."""

AXIS_NAMES = (
    "data",
    "models",
    "prompts",
    "configuration",
    "code",
    "environment",
    "evaluation",
)


class Pin(BaseModel):
    """One named value held constant for a run: a code-list version, a threshold, a seed."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    value: str


class StageModel(BaseModel):
    """Which model served one stage, under which decoding parameters.

    `model_id` is what the stage asked for and `model_version` is what the provider says
    answered; they differ when an id points at a moving alias, and an accuracy movement
    across that boundary is invisible without both.
    """

    model_config = ConfigDict(frozen=True, protected_namespaces=())

    stage: str = Field(min_length=1)
    tier: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_version: str | None = None
    decoding: Decoding | None = None


class PromptPin(BaseModel):
    """One prompt, by name and declared version.

    `content_hash` is dossier 08 §14.1's ask and is optional here because nothing outside
    the prompt loader reads the prompt directory. A caller that computes it supplies it;
    a run that does not is listed by `unpinned()` rather than pretending the version
    string alone identifies the text.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    stage: str | None = None
    content_hash: str | None = None


class DataPins(BaseModel):
    """The data half of the attribution question."""

    model_config = ConfigDict(frozen=True)

    nomenclature_vintage: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    embedding_dimensions: int = Field(gt=0)
    canonical_text_structure_version: str = Field(min_length=1)
    """The version of the text the vectors were built from. The build side and the query
    side must phrase the same shape; change the shape and every vector is invalid."""

    index_build_id: str = UNPINNED
    nomenclature_source: str = UNPINNED
    code_lists: tuple[Pin, ...] = ()
    """Countries, units, packing, incoterms, procedures, portal classifiers."""


class ModelPins(BaseModel):
    """The model half of the attribution question."""

    model_config = ConfigDict(frozen=True)

    stages: tuple[StageModel, ...] = ()
    judge_model: str | None = None
    judge_rubric_version: str | None = None


class ConfigurationPins(BaseModel):
    """Every threshold, candidate count and feature flag in force, plus capture volume.

    Dossier 08 §14.3: a tuning result must be pinned into the configuration it justifies.
    The recorded precedent is one constant with three values — a measured 48%→67% gain at
    candidate count 50, a shipped default of 30, and another default of 15 in the same
    system — so the report prints what was actually in force rather than what was written
    down.
    """

    model_config = ConfigDict(frozen=True)

    settings: tuple[Pin, ...] = ()
    capture_level: str = Field(min_length=1)
    capture_truncation_chars: int | None = None
    capture_sampling_rate: float = Field(ge=0.0, le=1.0)

    @classmethod
    def from_policy(
        cls, policy: CapturePolicy, settings: tuple[Pin, ...] = ()
    ) -> ConfigurationPins:
        """Take the capture axis off the policy object itself, so the two cannot drift."""
        return cls(
            settings=settings,
            capture_level=policy.level.value,
            capture_truncation_chars=policy.truncation_chars,
            capture_sampling_rate=policy.sampling_rate,
        )


class CodePins(BaseModel):
    model_config = ConfigDict(frozen=True)

    build_identifier: str = Field(min_length=1)
    """Required, and deliberately: a run that cannot name its build is a run whose result
    cannot be reproduced. `UNPINNED` is an acceptable value and is reported as such."""


class EnvironmentPins(BaseModel):
    model_config = ConfigDict(frozen=True)

    seeds: tuple[Pin, ...] = ()
    notes: tuple[str, ...] = ()
    """Anything else that can change output and has no field of its own."""


class EvaluationPins(BaseModel):
    """Present only on a measured run. Absent on a production run, and that absence is
    the axis: a production run has no golden set and no label set."""

    model_config = ConfigDict(frozen=True)

    golden_set_version: str = Field(min_length=1)
    golden_set_partition: str = Field(min_length=1)
    label_set_version: str = UNPINNED
    canonicalization_version: str = UNPINNED
    metric_definition_version: str = UNPINNED


class RunManifest(BaseModel):
    """What one run held constant, in seven axes."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    created_at: datetime
    data: DataPins
    models: ModelPins
    configuration: ConfigurationPins
    code: CodePins
    prompts: tuple[PromptPin, ...] = ()
    environment: EnvironmentPins = EnvironmentPins()
    evaluation: EvaluationPins | None = None

    def axes(self) -> dict[str, Any]:
        """The seven axes, without the run's own identity.

        The run identifier and the start time differ on every run by construction, so
        including them would make every comparison a compound change.
        """
        return {
            "data": self.data.model_dump(mode="json"),
            "models": self.models.model_dump(mode="json"),
            "prompts": [pin.model_dump(mode="json") for pin in self.prompts],
            "configuration": self.configuration.model_dump(mode="json"),
            "code": self.code.model_dump(mode="json"),
            "environment": self.environment.model_dump(mode="json"),
            "evaluation": (
                self.evaluation.model_dump(mode="json") if self.evaluation else None
            ),
        }

    def fingerprints(self) -> dict[str, str]:
        """One short digest per axis, for a report header and for the comparison."""
        return {name: _digest(value) for name, value in self.axes().items()}

    def fingerprint(self) -> str:
        """One digest for the whole manifest, stamped on every retained artifact."""
        return _digest(self.axes())

    def unpinned(self) -> tuple[str, ...]:
        """Every axis element this run could not pin, named.

        The list is what a report prints under known limits and what a comparison must be
        read against: two runs that agree on an axis neither of them pinned have not
        established anything about it.
        """
        missing: list[str] = []
        for label, value in (
            ("data.nomenclature_vintage", self.data.nomenclature_vintage),
            ("data.index_build_id", self.data.index_build_id),
            ("data.nomenclature_source", self.data.nomenclature_source),
            (
                "data.canonical_text_structure_version",
                self.data.canonical_text_structure_version,
            ),
            ("code.build_identifier", self.code.build_identifier),
        ):
            if value == UNPINNED:
                missing.append(label)
        if not self.data.code_lists:
            missing.append("data.code_lists (no code-list version recorded)")
        if not self.models.stages:
            missing.append("models.stages (no model recorded for any stage)")
        for stage in self.models.stages:
            if stage.decoding is None:
                missing.append(f"models.stages[{stage.stage}].decoding")
        if not self.prompts:
            missing.append("prompts (no prompt recorded)")
        for prompt in self.prompts:
            if prompt.content_hash is None:
                missing.append(f"prompts[{prompt.name}].content_hash")
        if not self.configuration.settings:
            missing.append("configuration.settings (no threshold or flag recorded)")
        if not self.environment.seeds:
            missing.append("environment.seeds")
        return tuple(missing)


class AttributionVerdict(StrEnum):
    """Whether a difference between two runs can be assigned a cause."""

    IDENTICAL = "identical"
    SINGLE_AXIS = "single-axis"
    COMPOUND = "compound change"


class ManifestComparison(BaseModel):
    """What differs between two runs, and whether that licenses an attribution."""

    model_config = ConfigDict(frozen=True)

    differing_axes: tuple[str, ...]
    verdict: AttributionVerdict
    unpinned_either_side: tuple[str, ...] = ()

    @property
    def attributable_to(self) -> str | None:
        """The single axis a metric movement may be attributed to, or None."""
        if self.verdict is AttributionVerdict.SINGLE_AXIS:
            return self.differing_axes[0]
        return None

    def statement(self) -> str:
        if self.verdict is AttributionVerdict.IDENTICAL:
            head = "manifests are identical on all seven axes"
        elif self.verdict is AttributionVerdict.SINGLE_AXIS:
            head = f"single-axis change: {self.differing_axes[0]}"
        else:
            head = f"COMPOUND CHANGE across {', '.join(self.differing_axes)} — no single cause may be claimed"
        if self.unpinned_either_side:
            head += (
                f"; {len(self.unpinned_either_side)} axis element(s) unpinned on one or "
                "both sides"
            )
        return head


def compare_manifests(before: RunManifest, after: RunManifest) -> ManifestComparison:
    """Apply dossier 08 §14.2 to two runs.

    Read-only, and reachable only from a comparison of two finished manifests — nothing
    on a run path calls it and nothing it returns can change a run.
    """
    before_axes = before.axes()
    after_axes = after.axes()
    differing = tuple(
        name
        for name in AXIS_NAMES
        if _digest(before_axes[name]) != _digest(after_axes[name])
    )
    if not differing:
        verdict = AttributionVerdict.IDENTICAL
    elif len(differing) == 1:
        verdict = AttributionVerdict.SINGLE_AXIS
    else:
        verdict = AttributionVerdict.COMPOUND
    unpinned = tuple(sorted(set(before.unpinned()) | set(after.unpinned())))
    return ManifestComparison(
        differing_axes=differing, verdict=verdict, unpinned_either_side=unpinned
    )


def _digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
