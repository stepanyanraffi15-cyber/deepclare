"""What the run used, pinned, so the number it produced is attributable to something.

The rule this file exists to enforce: a metric change is attributable only if exactly one
axis below differs between two runs. That is not pedantry — the specification records one
experiment that shipped three changes together and could attribute its gain only by
reading a failure funnel, one comparison whose own record says it is "not a strict A/B",
and one across-the-board regression with no record of what changed at all, permanently
unattributable. It also records the largest single measured gain in the system sitting in
prose while three different values of the constant it justified shipped in the same
build.

The manifest is filled from the configuration in force and from the reference artifact's
own metadata. It is never filled from a default written here.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from deepclare.classification.features import ClassificationFeatures
from deepclare.config import Settings
from deepclare.models import Decoding
from deepclare.prompting import PromptIdentity, prompt_identities
from deepclare.reference.store import artifact_vintage


class Production(StrEnum):
    """How the scored declarations came to exist. It decides what the manifest means."""

    PIPELINE = "pipeline"
    """This run produced them. Every axis below describes what produced them."""

    PRE_EMITTED = "pre-emitted"
    """They were read from files. Every axis below describes the configuration present
    while scoring, which is not necessarily the configuration that wrote the files."""


class RunManifest(BaseModel):
    """The identity of one evaluation run."""

    model_config = ConfigDict(frozen=True)

    scored_at: datetime
    code_build: str
    production: Production
    producer: str
    """One line saying how each case became XML."""

    corpus_dir: str
    scorer_dir: str

    model_ids: dict[str, str]
    decoding: dict[str, float | int]
    prompts: tuple[PromptIdentity, ...]

    nomenclature_vintage: str
    nomenclature_dir: str
    embedding_model: str
    embedding_dimensions: int

    retrieval_depth: int
    classification_features: dict[str, bool | float | int]

    scoring_thresholds: dict[str, float | bool]

    @property
    def attributes_the_output(self) -> bool:
        """Whether the axes below actually describe what wrote the scored XML."""
        return self.production is Production.PIPELINE


def build_manifest(
    *,
    settings: Settings,
    production: Production,
    producer: str,
    corpus_dir: Path,
    scorer_dir: Path,
    features: ClassificationFeatures,
    decoding: Decoding,
    scoring_thresholds: dict[str, float | bool],
) -> RunManifest:
    """Read every axis from the configuration and the artifacts, once."""
    return RunManifest(
        scored_at=datetime.now(UTC),
        code_build=code_build_identifier(),
        production=production,
        producer=producer,
        corpus_dir=str(Path(corpus_dir).resolve()),
        scorer_dir=str(Path(scorer_dir).resolve()),
        model_ids={
            "cheap": settings.genai_model_cheap,
            "standard": settings.genai_model_standard,
            "strong": settings.genai_model_strong,
        },
        decoding={
            "temperature": decoding.temperature,
            "top_p": decoding.top_p,
            "top_k": decoding.top_k,
            "candidate_count": decoding.candidate_count,
            "max_output_tokens": decoding.max_output_tokens,
            "seed": decoding.seed,
        },
        prompts=prompt_identities(settings.prompts_dir),
        nomenclature_vintage=artifact_vintage(settings.reference_dir),
        nomenclature_dir=str(Path(settings.reference_dir).resolve()),
        embedding_model=settings.classify_embedding_model,
        embedding_dimensions=settings.classify_embedding_dim,
        retrieval_depth=features.candidate_limit,
        classification_features={
            "printed_code_fast_path": features.printed_code_fast_path,
            "subheading_preference": features.subheading_preference,
            "verification": features.verification,
            "candidate_limit": features.candidate_limit,
            "review_below_confidence": features.review_below_confidence,
            "review_below_heading_agreement": features.review_below_heading_agreement,
        },
        scoring_thresholds=scoring_thresholds,
    )


def code_build_identifier() -> str:
    """The commit this ran from, and whether the tree was dirty when it did.

    A dirty tree is reported rather than refused: the harness has to be runnable while
    the thing it measures is being changed. It does mean the build identifier alone does
    not reproduce the run, which is what the marker says.
    """
    revision = _git("rev-parse", "--short", "HEAD")
    if revision is None:
        return "unknown (not a git checkout, or git is unavailable)"
    dirty = _git("status", "--porcelain")
    if dirty is None:
        return revision
    return revision if not dirty else f"{revision}+dirty"


def _git(*arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()
