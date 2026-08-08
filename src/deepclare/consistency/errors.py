"""The one failure this module raises, and the reason it is not raised for much.

A model failure, a malformed answer or a rewrite that breaks a guardrail is not an error
here: the pass is best-effort by contract and leaves the drafted lines untouched. What
does raise is a caller mistake — a batch that cannot be reconciled because it is
self-contradictory — because that is a defect in the run, not a property of the goods.
"""

from __future__ import annotations


class ConsistencyError(RuntimeError):
    """The batch handed to reconciliation is not a batch of distinct goods lines."""
