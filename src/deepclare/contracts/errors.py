"""The error vocabulary. One shape, every failure — file 09 §6.1: the client normalizes
a string-or-array detail from an inconsistent transport; this contract does not repeat
that inconsistency by having more than one error shape to begin with.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "unauthenticated"
    """No bearer token, or one the service does not recognize."""

    SUBMISSION_REJECTED = "submission_rejected"
    """Structurally invalid: wrong file count, unreadable role, decode failure. Refused
    before a job is queued — file 09 §6.4's rule, not a job that could never succeed."""

    NOT_FOUND = "not_found"
    """No job with this id, or it belongs to another tenant. The two are indistinguishable
    on purpose, matching M15's boundary invariant that a job id must not be probeable."""

    JOB_NOT_FINISHED = "job_not_finished"
    """The result was asked for before the job reached a terminal state."""

    RUN_FAILED = "run_failed"
    """The job reached the `failed` terminal state. `ErrorResponse.message` carries what
    M14 raised — a structural, contract, or model-call failure; never retried."""

    INTERNAL = "internal"
    """Anything this vocabulary does not name. Never the raw exception text."""


class ErrorResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: str
