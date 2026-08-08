"""Retained artifacts, and a retention policy that only a human can act on.

Dossier 08 §16.4 lists what a run keeps, addressable by run identifier: the input
documents as received; the extracted text and structured extraction per document, each
stamped with the manifest that produced it; the intermediate state at each stage
boundary; the emitted document; the review report; every judge input and output; and the
manifest itself.

**Nothing in this module deletes anything, and nothing in this package does either.**
Dossier 10 §3 M17 states it as an invariant — retention is explicit and never automatic,
no lifecycle rule and no code path deletes a trace or an artifact — and the way to hold
an invariant like that is to write no function that could violate it. There is no
`delete`, no `prune`, no `expire`, no window that anything enforces. `RetentionPolicy` is
a **declaration** that gets recorded and printed; it is not a mechanism, and a run whose
declared window has passed keeps its artifacts until a person removes them.

Overwriting is refused for the same reason. Writing over a retained artifact is a
deletion with a different name.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from deepclare.trace.errors import TraceError
from deepclare.trace.manifest import RunManifest

INDEX_FILE = "artifacts.jsonl"
MANIFEST_FILE = "manifest.json"


class ArtifactKind(StrEnum):
    """What a retained file is. The list is dossier 08 §16.4's, not a general vocabulary."""

    INPUT_DOCUMENT = "input_document"
    EXTRACTED_TEXT = "extracted_text"
    STRUCTURED_EXTRACTION = "structured_extraction"
    STAGE_STATE = "stage_state"
    EMITTED_DOCUMENT = "emitted_document"
    REVIEW_REPORT = "review_report"
    JUDGE_INPUT = "judge_input"
    JUDGE_OUTPUT = "judge_output"
    MANIFEST = "manifest"


class RetentionPolicy(BaseModel):
    """A declared intent about how long artifacts are kept, and by whom they are removed.

    Recorded in the trace and printed in the report. It enforces nothing: `window_days`
    is what a person was told, not what a machine will do.
    """

    model_config = ConfigDict(frozen=True)

    declared_by: str = Field(min_length=1)
    window_days: int | None = Field(default=None, gt=0)
    """`None` is indefinite retention, which is this build's default."""

    def statement(self) -> str:
        window = (
            "indefinite" if self.window_days is None else f"{self.window_days} days"
        )
        return (
            f"retention {window}, declared by {self.declared_by}; "
            "deletion is by explicit human action only — no code path here removes an "
            "artifact or a trace"
        )


class ArtifactRef(BaseModel):
    """One retained file, addressable by run identifier and stamped with its manifest."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    kind: ArtifactKind
    name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    byte_count: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    manifest_fingerprint: str = Field(min_length=1)
    """Which manifest produced it. An extraction without one cannot be compared against
    another run's extraction, because nothing says what differed."""

    retained_at: datetime


class ArtifactStore:
    """Writes a run's artifacts under one directory named for the run.

    Construction writes the manifest, so an artifact directory that exists at all can say
    what produced its contents.
    """

    def __init__(
        self,
        *,
        root: Path,
        manifest: RunManifest,
        retention: RetentionPolicy,
    ) -> None:
        self._manifest = manifest
        self._retention = retention
        self._fingerprint = manifest.fingerprint()
        self._directory = Path(root) / manifest.run_id
        self._directory.mkdir(parents=True, exist_ok=True)
        self._index = self._directory / INDEX_FILE
        self._write_manifest()

    @property
    def directory(self) -> Path:
        return self._directory

    def retain_bytes(self, kind: ArtifactKind, name: str, content: bytes) -> ArtifactRef:
        """Write one artifact and return its reference. Refuses to overwrite."""
        destination = self._directory / kind.value / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise TraceError(
                f"{destination} already exists. Overwriting a retained artifact is a "
                "deletion under another name; choose a different artifact name."
            )
        destination.write_bytes(content)
        reference = ArtifactRef(
            run_id=self._manifest.run_id,
            kind=kind,
            name=name,
            path=str(destination),
            byte_count=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            manifest_fingerprint=self._fingerprint,
            retained_at=datetime.now(UTC),
        )
        with self._index.open("a", encoding="utf-8") as handle:
            handle.write(reference.model_dump_json() + "\n")
        return reference

    def retain_text(self, kind: ArtifactKind, name: str, content: str) -> ArtifactRef:
        return self.retain_bytes(kind, name, content.encode("utf-8"))

    def _write_manifest(self) -> None:
        path = self._directory / MANIFEST_FILE
        if path.exists():
            return
        payload = {
            "manifest": self._manifest.model_dump(mode="json"),
            "fingerprints": self._manifest.fingerprints(),
            "fingerprint": self._fingerprint,
            "unpinned": list(self._manifest.unpinned()),
            "retention": self._retention.model_dump(mode="json"),
            "retention_statement": self._retention.statement(),
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
