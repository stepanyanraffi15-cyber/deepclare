"""What the orchestration itself can refuse.

Every other error in a run belongs to the stage that raised it — a `ReadingError`, a
`ClassificationError`, a `SubmissionRejected`. These three are the orchestrator's own, and
each exists because the alternative is a lookup failure somewhere later that names a
dictionary instead of a goods line.
"""

from __future__ import annotations


class RunError(RuntimeError):
    """The run cannot continue, and the reason is the run's own rather than a stage's."""


class ContractError(RunError):
    """A stage did not keep the promise the chain joins on.

    The join key is the caller-assigned line id, and every per-line stage promises one
    result per input line keyed by that id. A missing or unexpected id is reported here,
    naming the line, rather than discovered as a `KeyError` during reassembly.
    """


class StateError(RunError):
    """A slot was read before the stage that writes it had run.

    Only reachable by building a chain whose stages are out of order, which is a defect
    in the chain rather than a property of the submission — so it names the slot and the
    stage that fills it.
    """
