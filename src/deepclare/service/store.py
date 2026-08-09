"""The job store. One process, one dict, no persistence.

Dossier file 10 M15 asks for a real job store, tenancy and quota; none of that is here.
This is the v1 the architecture artifact proposed and the user reviewed: single-process,
in-memory, lost on restart — the same fragility file 09's R09 already records for the
predecessor's own job store, not a regression from it.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass

from deepclare.contracts import JobStatus
from deepclare.run import RunState


@dataclass
class JobRecord:
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    current_stage: str | None = None
    state: RunState | None = None
    """Set only once `status` is `succeeded`."""
    error: str | None = None
    """Set only once `status` is `failed`."""


class JobStore:
    """Guarded by one lock. Reads and writes are both small and infrequent enough that a
    single lock costs nothing and a job id can never observe a torn update."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}

    def create(self) -> JobRecord:
        job = JobRecord(job_id=uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **changes: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in changes.items():
                setattr(job, key, value)
