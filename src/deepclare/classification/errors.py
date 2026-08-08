"""The one error this module raises.

There is no retry and no repair anywhere on this path. The first provider failure, the
first malformed answer, the first answer that is the right shape and an unusable thing
becomes this and the line has no code — which is work left for a human rather than a
wrong code filed on a legal document.
"""

from __future__ import annotations


class ClassificationError(RuntimeError):
    """Code assignment could not run to a decision for one goods line."""


class GraphDeclarationError(RuntimeError):
    """The graph itself is mis-declared.

    Never a run-time condition: it means the node and edge declaration cannot be
    traversed, which is a defect in the declaration and not in any goods line.
    """
