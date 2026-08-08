"""The one error this package raises."""

from __future__ import annotations


class TraceError(RuntimeError):
    """The observation layer could not record what it was given.

    Raised for a mis-declared trace — a node closed twice, a stage that was never bound,
    an artifact name that would overwrite a retained artifact. Never raised to report
    something about the run itself: this package has no opinion about a declaration.
    """
