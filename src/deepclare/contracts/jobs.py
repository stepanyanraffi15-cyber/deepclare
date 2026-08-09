"""Job identity and status — the submit → poll model dossier file 09 §6.3 specifies.

Two terminal states only, matching M14: `execute()` either returns a state or raises.
There is no `cancelled` state and no cancel operation, because none exists in M14 either
— file 09 §9 leaves whether a queued job is distinguishable from an executing one as an
open question; this contract answers it by naming the current stage, which M14's
`on_stage` callback already reports.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SubmitRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str


class JobStatusResponse(BaseModel):
    """What polling returns. `error` is set only when `status` is `failed`."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    status: JobStatus
    current_stage: str | None = None
    """The most recent stage `on_stage` reported. `None` while still queued."""
    error: str | None = None
