"""Where node records land. Append-only, flushed per record, never truncated.

Dossier 08 §16.2 grounds both properties in a measured precedent: the system this
specification describes deleted its trace file at the beginning of every run, so the
previous run's evidence was gone by the time anyone wanted to compare against it. The
file here is opened for append and there is no mode, flag or helper that opens it any
other way.

Each record is flushed as it is written, because a run that dies mid-pipeline is exactly
the run whose trace is worth having.
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Protocol, Self

from deepclare.trace.records import NodeTrace


class TraceSink(Protocol):
    """Somewhere a node record can be appended."""

    def append(self, record: NodeTrace) -> None: ...

    def close(self) -> None: ...


class MemoryTraceSink:
    """Keeps records in the process. For a run that wants its trace and no file."""

    def __init__(self) -> None:
        self.records: list[NodeTrace] = []

    def append(self, record: NodeTrace) -> None:
        self.records.append(record)

    def close(self) -> None:
        """Nothing to close. The records stay; nothing here clears them."""

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class JsonlTraceSink:
    """One JSON object per line, appended to a file that is never rewritten."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # "a" and only ever "a": the file is opened at its end and the previous run's
        # records are still in front of this one's.
        self._handle = self._path.open("a", encoding="utf-8")

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: NodeTrace) -> None:
        self._handle.write(record.model_dump_json() + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def read_trace_file(path: Path) -> tuple[NodeTrace, ...]:
    """Read back what a JSONL sink wrote. Used by whatever reports on a run."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return tuple(NodeTrace.model_validate_json(line) for line in lines if line.strip())
