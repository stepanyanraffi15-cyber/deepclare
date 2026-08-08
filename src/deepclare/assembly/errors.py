"""Failures assembly raises rather than papers over."""

from __future__ import annotations


class AssemblyError(RuntimeError):
    """A declaration could not be assembled from what arrived.

    Raised only where continuing would put an invented value on a legal document — a
    goods line with no draft, a reference table that will not load. Everything an
    operator could fix is a review item instead, not an exception.
    """
