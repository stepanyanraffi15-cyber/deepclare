"""Logging bootstrap for the public website — stdout only (Cloud Run -> Cloud Logging).

A scaled-down sibling of the agent's `deepclare_agent.observability` (same `LOG_LEVEL` env
var convention): this service has no tracing and no request-id context, so it only needs
a configured root logger — modules just call `logging.getLogger(__name__)` and log.
"""

import logging
import os

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

_configured = False


def configure_logging() -> None:
    """Idempotent: safe to call every time `create_app()` runs (e.g. once per test)."""
    global _configured
    if _configured:
        return
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=level, format=_FORMAT)
    _configured = True
