"""Failures the filing adapter raises rather than writing something wrong.

The external system's diagnostics are three opaque signals — a wrong-format rejection
naming no field, a hang at 100% with no message, and a silent value drop — so a fault
this module can see must stop here. A file that leaves with a known defect in it costs a
human a rejected import and no information about why.
"""

from __future__ import annotations


class FilingContractError(Exception):
    """A value cannot be written in a form the contract accepts."""


class UnrepresentableValue(FilingContractError):
    """A value has no valid representation in the filed format.

    Raised rather than coerced. Silently rounding, truncating or reformatting a value the
    contract cannot carry is how a wrong number reaches a legal document.
    """


class MalformedFiledDocument(Exception):
    """A document being read is not a declaration this adapter recognises."""
