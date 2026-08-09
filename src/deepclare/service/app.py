"""M15 Service Edge — the network boundary. Wraps M14; decides nothing about a
declaration.

Dossier file 10 M15: authentication, identity, tenancy, quota, submission acceptance,
the job lifecycle, result retrieval, error translation. **What this v1 actually has**:
one dev-only bearer token, one implicit tenant, an in-memory job store, no quota. Every
gap against the dossier's full boundary is named in the architecture artifact's
delivery-layer section, not silently narrowed here.

**Must not decide anything about a declaration** — that rule binds M16 as much as M15,
and this module holds to it too: it translates, queues and reports; every value in a
`RunResult` was produced by M5 through M13.
"""

from __future__ import annotations

import binascii
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from deepclare.config import Settings, load_settings
from deepclare.contracts import (
    ErrorCode,
    ErrorResponse,
    JobStatus,
    JobStatusResponse,
    RunResult,
    RunSummary,
    SubmitRunRequest,
    SubmitRunResponse,
)
from deepclare.run import open_ports
from deepclare.service.store import JobRecord, JobStore
from deepclare.service.worker import Worker, to_run_input

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False, description="The dev token from SERVICE_DEV_TOKEN.")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. `settings` is a parameter, not a global read — the same rule M14's
    ports follow, so a test can hand this a different `Settings` and get a different,
    isolated service."""
    resolved_settings = settings or load_settings()
    store = JobStore()
    worker_holder: dict[str, Worker] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # The embedded vector store's exclusive lock is the reason this happens exactly
        # once, here, rather than per request — see worker.py's module docstring.
        with open_ports(resolved_settings) as ports:
            worker = Worker(store, ports)
            worker.start()
            worker_holder["worker"] = worker
            yield

    app = FastAPI(title="DeepClare Service Edge", version="0.1.0", lifespan=lifespan)

    def authenticate(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None, Security(_bearer)
        ],
    ) -> None:
        if (
            credentials is None
            or credentials.credentials != resolved_settings.service_dev_token
        ):
            raise _error(401, ErrorCode.UNAUTHENTICATED, "missing or invalid bearer token")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/runs", dependencies=[Depends(authenticate)])
    def submit_run(request: SubmitRunRequest) -> SubmitRunResponse:
        try:
            run_input = to_run_input(request)
        except (binascii.Error, ValueError) as exc:
            raise _error(400, ErrorCode.SUBMISSION_REJECTED, str(exc)) from exc

        job = store.create()
        worker_holder["worker"].submit(job.job_id, run_input)
        return SubmitRunResponse(job_id=job.job_id)

    @app.get("/runs/{job_id}", dependencies=[Depends(authenticate)])
    def get_status(job_id: str) -> JobStatusResponse:
        job = _require_job(store, job_id)
        return JobStatusResponse(
            job_id=job.job_id,
            status=job.status,
            current_stage=job.current_stage,
            error=job.error,
        )

    @app.get("/runs/{job_id}/result", dependencies=[Depends(authenticate)])
    def get_result(job_id: str) -> RunResult:
        job = _require_job(store, job_id)
        if job.status is JobStatus.FAILED:
            raise _error(
                422, ErrorCode.RUN_FAILED, job.error or "the run failed"
            )
        if job.status is not JobStatus.SUCCEEDED or job.state is None:
            raise _error(
                409, ErrorCode.JOB_NOT_FINISHED, f"job is {job.status.value}"
            )

        filed = job.state.require_filed()
        return RunResult(
            declaration_xml=filed.xml,
            review_report=job.state.require_report(),
            summary=RunSummary(
                goods_line_count=job.state.goods_line_count,
                codes_assigned=job.state.codes_assigned,
                codes_abstained=job.state.codes_abstained,
                conforms=filed.conformance.conforms,
                filable=filed.conformance.filable,
                notes=job.state.notes,
            ),
        )

    return app


def _require_job(store: JobStore, job_id: str) -> JobRecord:
    job = store.get(job_id)
    if job is None:
        raise _error(404, ErrorCode.NOT_FOUND, "no such job")
    return job


def _error(status_code: int, code: ErrorCode, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=ErrorResponse(code=code, message=message).model_dump(mode="json"),
    )
