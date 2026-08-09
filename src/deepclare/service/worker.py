"""The single worker: one set of ports, one thread, jobs run one at a time.

**Why one at a time, and not the dossier's four.** The embedded vector store takes an
exclusive lock on its directory — PROGRESS.md's evaluation-corpus entry measured this
directly: a second `open_ports()` call in the same process fails outright rather than
degrading. Dossier file 10's four-concurrent-run assumption does not hold against an
embedded store. This worker is the honest v1 answer: ports opened once at process
startup and held for its life, a queue that admits exactly the concurrency the store
allows, and a submission that arrives while one is running simply waits its turn — which
file 09 §6.3 already treats as ordinary ("a queued job is normal and indistinguishable
from a slow one").
"""

from __future__ import annotations

import base64
import logging
import queue
import threading

from deepclare.assembly.inputs import (
    DeclarantProfile,
    FillerProfile,
    GoodsLocationProfile,
    ImporterProfile,
)
from deepclare.contracts import JobStatus
from deepclare.contracts.submit import SubmitRunRequest
from deepclare.intake.submission import SubmittedFile
from deepclare.run import Ports, RunInput, RunState, execute
from deepclare.service.store import JobStore

logger = logging.getLogger(__name__)


def to_run_input(request: SubmitRunRequest) -> RunInput:
    """The one place a wire request becomes a pipeline input. Everything M2 chose to
    carry as a lean mirror gets rebuilt into the real M11 shape here; everything it
    reused directly (`DocumentRole`) passes through untouched."""
    files = tuple(
        SubmittedFile(
            file_name=f.file_name,
            content=base64.b64decode(f.content_base64, validate=True),
            declared_role=f.declared_role,
        )
        for f in request.files
    )
    profile_in = request.profile
    profile = DeclarantProfile(
        goods_location=(
            GoodsLocationProfile(**profile_in.goods_location.model_dump())
            if profile_in.goods_location is not None
            else None
        ),
        filler=(
            FillerProfile(**profile_in.filler.model_dump())
            if profile_in.filler is not None
            else None
        ),
        importer=(
            ImporterProfile(**profile_in.importer.model_dump())
            if profile_in.importer is not None
            else None
        ),
    )
    return RunInput(files=files, profile=profile)


class Worker:
    """Started once, in the app's lifespan. `submit` is safe to call from any request
    thread; the run itself always happens on the one worker thread."""

    def __init__(self, store: JobStore, ports: Ports) -> None:
        self._store = store
        self._ports = ports
        self._queue: queue.Queue[tuple[str, RunInput]] = queue.Queue()
        self._thread = threading.Thread(
            target=self._loop, name="deepclare-run-worker", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def submit(self, job_id: str, run_input: RunInput) -> None:
        self._queue.put((job_id, run_input))

    def _loop(self) -> None:
        while True:
            job_id, run_input = self._queue.get()
            self._run_one(job_id, run_input)
            self._queue.task_done()

    def _run_one(self, job_id: str, run_input: RunInput) -> None:
        self._store.update(job_id, status=JobStatus.RUNNING)

        def on_stage(name: str, _state: RunState, *, _job_id: str = job_id) -> None:
            self._store.update(_job_id, current_stage=name)

        try:
            final_state = execute(run_input, self._ports, on_stage=on_stage)
        except Exception as exc:  # noqa: BLE001 — the run's own three failure kinds,
            # surfaced to a client rather than crashing the one worker thread every
            # later submission depends on. Never retried: dossier 09 §6.3, and a second
            # attempt at a legal document is a machine talking itself into an answer.
            logger.exception("run %s failed", job_id)
            self._store.update(job_id, status=JobStatus.FAILED, error=str(exc))
        else:
            self._store.update(job_id, status=JobStatus.SUCCEEDED, state=final_state)
