"""M2 Interface Contracts — everything that crosses between M15 and a client.

Dossier 10 §3 M2: request/response definitions, job and result payloads, and the error
code vocabulary. **Must not know any component's internals** — nothing here names a
class, a store or a file belonging to M14 or M15; it defines what crosses, not what
performs.

Two kinds of type live here, and the distinction is the module's whole reason to exist:

* **Reused domain vocabulary.** `DocumentRole` and the declarant-profile shapes are
  already M1-level, JSON-safe data with no behaviour — reusing them is not a leak of
  internals, and defining a second, drifting copy would be the opposite of what an
  interface contract is for.
* **Wire-only shapes.** A submitted file's bytes cannot ride JSON, so `SubmittedFileIn`
  carries base64 text instead of `bytes`; a run's result is a lean projection of
  `RunState`, never `RunState` itself, because `RunState` carries objects — an XML
  `Element` tree, rendered page images — that are not a client's concern and are not
  serializable in the first place.

Additive versioning only: a retired field is removed in a new contract version, never
silently repurposed, and a documented operation is verified against M15's routes so a
client can never be handed a path that does not exist.
"""

from __future__ import annotations

from deepclare.contracts.errors import ErrorCode, ErrorResponse
from deepclare.contracts.jobs import JobStatus, JobStatusResponse, SubmitRunResponse
from deepclare.contracts.results import RunResult, RunSummary
from deepclare.contracts.submit import (
    DeclarantProfileIn,
    FillerProfileIn,
    GoodsLocationProfileIn,
    ImporterProfileIn,
    SubmitRunRequest,
    SubmittedFileIn,
)

__all__ = [
    "DeclarantProfileIn",
    "ErrorCode",
    "ErrorResponse",
    "FillerProfileIn",
    "GoodsLocationProfileIn",
    "ImporterProfileIn",
    "JobStatus",
    "JobStatusResponse",
    "RunResult",
    "RunSummary",
    "SubmitRunRequest",
    "SubmitRunResponse",
    "SubmittedFileIn",
]
