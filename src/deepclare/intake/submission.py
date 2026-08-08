"""What arrives from the service edge: one shipment's files, with whatever labels
the client put on them.

The role is optional because the boundary in front of this one makes it optional. That
is a known weakness — a required role with an explicit "unknown" value would be better —
but it is not intake's to change, so intake carries the inference instead and records on
every document which of the two produced its role.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from deepclare.domain import DocumentRole


class SubmittedFile(BaseModel):
    """One uploaded file, exactly as it was received. Nothing here is decoded."""

    model_config = ConfigDict(frozen=True)

    file_name: str = Field(min_length=1)
    """As the client sent it, including the extension. Shown to the operator when a
    structural rule refuses this file, so it is never rewritten."""

    content: bytes = Field(min_length=1)
    declared_role: DocumentRole | None = None
    """What the client labelled this file. None when it labelled nothing, which is
    ordinary: the file name is then read for a role."""
