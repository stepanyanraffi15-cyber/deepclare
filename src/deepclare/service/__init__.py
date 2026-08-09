"""M15 Service Edge — the network boundary around M14.

Dossier file 10 §3 M15: authentication, identity, tenancy, quota, submission
acceptance, the job lifecycle, result retrieval, error translation. **Must not know**
how a declaration is produced, any node's internals, the filing contract, or the
reference data — every value that crosses this package's boundary is a `deepclare.
contracts` type, never an M5–M14 internal one.

This is a v1: one dev-only bearer token (`SERVICE_DEV_TOKEN`), one implicit tenant, an
in-memory job store, no quota, one worker thread bounded by the embedded vector store's
own exclusive lock. The gaps against the dossier's full M15 boundary are named in the
architecture artifact, not hidden here.
"""

from deepclare.service.app import create_app

__all__ = ["create_app"]
