"""How much of a run is captured, stated as a value rather than assumed.

Dossier 08 §16.3, and the reason it is a policy object rather than a debug flag: the
payloads this layer captures are extracted invoice contents — party names, addresses,
tax identifiers, contact details — and they land in durable sinks. Volume is therefore a
declared decision of the run, recorded in the manifest alongside every other pin.

Four levels, ordered by how much document content each admits:

    off       nothing is recorded at all
    records   what happened: node, decision, outcome, model call, tokens, timing,
              retrieval candidates and scores. No document content.
    states    plus each node's entry and exit state
    payloads  plus the full prompt and the full model response

**Redaction is not one of the levels.** Dossier 08 §16.3 requires it at every level and
this module offers no way to turn it off; see `redaction.py`. What the level controls is
how much is captured, not how much of it is masked.

Sampling governs the *content* levels only. A node record is written for every traversal
whatever the sampling rate, because dossier 08 §16.2 asks for one durable record per
node traversal and a sampled-away record is a hole in the run's own account of itself.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_TRUNCATION_CHARS = 4000
"""Where a captured prompt or response is cut when a cap is in force. Set to `None` to
capture untruncated, which dossier 08 §16.3 requires be possible."""


class CaptureLevel(StrEnum):
    """How much of a run reaches the sink."""

    OFF = "off"
    RECORDS = "records"
    STATES = "states"
    PAYLOADS = "payloads"


_VOLUME_ORDER = (
    CaptureLevel.OFF,
    CaptureLevel.RECORDS,
    CaptureLevel.STATES,
    CaptureLevel.PAYLOADS,
)


def _volume(level: CaptureLevel) -> int:
    return _VOLUME_ORDER.index(level)


class CapturePolicy(BaseModel):
    """What one run captures, and how much of it."""

    model_config = ConfigDict(frozen=True)

    level: CaptureLevel = CaptureLevel.RECORDS
    """Records by default: every node accounted for, no document content stored."""

    truncation_chars: int | None = Field(default=DEFAULT_TRUNCATION_CHARS, gt=0)
    """The declared cap on a captured prompt or response. `None` disables truncation."""

    sampling_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    """The share of nodes whose states and payloads are kept. Recorded in the manifest,
    because a metric computed over a sampled trace has a different denominator."""

    @property
    def records_nodes(self) -> bool:
        return _volume(self.level) >= _volume(CaptureLevel.RECORDS)

    @property
    def captures_states(self) -> bool:
        return _volume(self.level) >= _volume(CaptureLevel.STATES)

    @property
    def captures_payloads(self) -> bool:
        return _volume(self.level) >= _volume(CaptureLevel.PAYLOADS)

    def samples(self, *, run_id: str, sequence: int) -> bool:
        """Whether this node's states and payloads are kept.

        Deterministic in the run identifier and the sequence number rather than random,
        so a trace says which nodes were sampled and a second reading of the same trace
        agrees with the first.
        """
        if self.sampling_rate >= 1.0:
            return True
        if self.sampling_rate <= 0.0:
            return False
        digest = hashlib.blake2b(
            f"{run_id}:{sequence}".encode(), digest_size=8
        ).digest()
        return int.from_bytes(digest, "big") / 2**64 < self.sampling_rate

    def truncate(self, text: str) -> tuple[str, bool]:
        """The text as captured, and whether the cap cut it."""
        cap = self.truncation_chars
        if cap is None or len(text) <= cap:
            return text, False
        return text[:cap], True

    @classmethod
    def complete(cls) -> CapturePolicy:
        """Everything, untruncated, unsampled.

        Dossier 08 §16.3: capture must be complete for a run whose numbers will be
        quoted. Nothing in this package decides when that applies — it is a value the
        caller chooses and the manifest records.
        """
        return cls(
            level=CaptureLevel.PAYLOADS, truncation_chars=None, sampling_rate=1.0
        )

    def statement(self) -> str:
        cap = "untruncated" if self.truncation_chars is None else f"cut at {self.truncation_chars} chars"
        return (
            f"capture {self.level.value}, {cap}, sampling {self.sampling_rate:.2f}, "
            "redaction always on"
        )
