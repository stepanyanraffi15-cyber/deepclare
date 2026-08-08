"""Blocking intake failures, and the stable codes they carry.

A code is an identifier, never a message. The service edge translates it into an
actionable sentence in the operator's language; nothing here writes prose for a human.
Codes are append-only: once a code has reached a client it is never reworded and never
reused for a different condition, because the translation table on the other side is
keyed by it.

**None of these conditions is transient.** Re-uploading the same files produces the same
answer, so no message built from these codes may say "try again later" — that advice
would send an operator into a loop that cannot terminate. What every one of them needs
is a change to the submission.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class IntakeErrorCode(StrEnum):
    """Every way a submission can be refused before any goods are read."""

    NO_FILES = "intake.no_files"
    UNSUPPORTED_FILE_TYPE = "intake.unsupported_file_type"
    NO_INVOICE = "intake.no_invoice"
    MULTIPLE_INVOICES = "intake.multiple_invoices"
    MULTIPLE_CONSIGNMENT_NOTES = "intake.multiple_consignment_notes"

    UNREADABLE_CONTENT = "intake.unreadable_content"
    """The name promised something the bytes do not deliver. A file that passes a
    name-based check and then cannot be opened is an intake failure, not a reading
    failure."""

    NO_INVOICE_PAGE = "intake.no_invoice_page"
    """Nothing in the submission reads as an invoice page. Failing loudly beats filing a
    declaration with no goods on it."""


class SubmissionProblem(BaseModel):
    """One reason a submission was refused.

    `detail` is diagnostic English for a log and for a developer. It is not the text an
    operator sees; that is produced from `code` at the edge.
    """

    model_config = ConfigDict(frozen=True)

    code: IntakeErrorCode
    detail: str = Field(min_length=1)
    file_name: str | None = None
    """Named whenever one file is at fault, because "unsupported file type" without the
    file is not actionable in a submission of six documents."""


class IntakeError(RuntimeError):
    """Base for every intake failure."""


class SubmissionRejected(IntakeError):
    """The submission cannot proceed. Carries every problem found, not just the first.

    All of them are reported together so that an operator fixes the upload once rather
    than discovering the next fault after each correction.
    """

    def __init__(self, problems: Sequence[SubmissionProblem]) -> None:
        if not problems:
            raise ValueError("a rejection must state at least one problem")
        self.problems: tuple[SubmissionProblem, ...] = tuple(problems)
        super().__init__("; ".join(_describe(problem) for problem in self.problems))


def _describe(problem: SubmissionProblem) -> str:
    if problem.file_name:
        return f"{problem.code} [{problem.file_name}]: {problem.detail}"
    return f"{problem.code}: {problem.detail}"
