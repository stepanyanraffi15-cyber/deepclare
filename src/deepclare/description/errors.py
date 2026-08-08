"""The one error this module raises."""

from __future__ import annotations


class DescriptionError(RuntimeError):
    """A line's description could not be written.

    Raised for a provider failure, an answer that is not the requested shape, and an
    answer that is the right shape but not usable as filed Armenian text. Nothing
    catches this to try again: a second attempt at a legal document is a machine talking
    itself into an answer, and a description this stage cannot stand behind is better
    absent than filed.
    """
