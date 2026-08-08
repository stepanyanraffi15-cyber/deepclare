"""Run, case and line identity, and the sequence number that survives concurrency.

Dossier 08 §16.1. Three identifiers, nested: a **run** is one execution of the pipeline,
a **case** is one declaration inside it, and a **line** is one goods line inside that.
A production run has exactly one case; a measured run over a corpus has many, and the
nesting is what lets one goods line's whole journey be pulled out of a shared trace.

The sequence number is minted per run under a lock, because model calls may be issued
concurrently and wall-clock timestamps at millisecond resolution do not order them.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from uuid import uuid4


def new_run_id(*, now: datetime | None = None) -> str:
    """Mint a run identifier at the entry point.

    Timestamp first so identifiers sort chronologically as strings, and a random tail so
    two runs starting in the same second are still distinct.
    """
    moment = now or datetime.now(UTC)
    return f"run-{moment.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"


def new_case_id() -> str:
    """Mint a case identifier — one declaration inside a run."""
    return f"case-{uuid4().hex[:12]}"


class SequenceCounter:
    """A monotonic counter, one per run. First value is 1.

    Locked rather than a bare integer: the outer chain is sequential, but nothing in the
    trace's contract promises that, and a duplicated sequence number silently reorders a
    run's record.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next = 1

    def take(self) -> int:
        with self._lock:
            value = self._next
            self._next += 1
        return value
