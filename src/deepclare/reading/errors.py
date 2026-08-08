"""The one way reading fails.

A provider failure, an answer that is not the requested shape, and an answer that cannot
be turned into a record all end the same way: this error is raised and the run stops.
There is no retry, no re-prompt and no partial record — a declaration drafted from half
an invoice is worse than no draft, because the missing half is invisible on the page a
reviewer is looking at.
"""

from __future__ import annotations


class ReadingError(RuntimeError):
    """A logical document could not be read. The stage failed and the run stops."""
