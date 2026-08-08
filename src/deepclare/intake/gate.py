"""The submission gate: refuse a structurally impossible submission before anything else
happens.

It sees **file names and declared roles only**. No byte is decoded and no content is
inspected here — that is what makes this check free and instant, and it is why it runs
before the subscription-priced work rather than after it. Content validation exists too,
but it belongs to the router and the rasterizer, which are allowed to open the file.

Four blocking rules, all structural:

  * every file carries a supported extension;
  * exactly one invoice;
  * at most one consignment note;
  * catalogue, specification and prior-declaration files never count as the invoice.

The fourth is not a separate test — it falls out of counting by role — but it is the one
a client trips most often: an upload of nothing but a prior declaration XML has no
invoice in it and is refused for that, not for the XML.

A recorded contradiction is carried here deliberately rather than fixed: `.png`, `.jpg`
and `.jpeg` are supported extensions at this gate while no page reading path for a bare
image is built. An image upload therefore passes here and fails at rasterization, where
it is named. Narrowing the accepted set is a product decision, not this module's.
"""

from __future__ import annotations

from collections.abc import Sequence

from deepclare.domain import DocumentRole
from deepclare.intake.errors import (
    IntakeErrorCode,
    SubmissionProblem,
    SubmissionRejected,
)
from deepclare.intake.roles import role_of
from deepclare.intake.submission import SubmittedFile

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".xml", ".xlsx"})


def check_submission(files: Sequence[SubmittedFile]) -> None:
    """Pass silently, or raise SubmissionRejected carrying every problem found."""
    if not files:
        raise SubmissionRejected(
            [
                SubmissionProblem(
                    code=IntakeErrorCode.NO_FILES,
                    detail="the submission carries no files at all",
                )
            ]
        )

    # Roles are counted only over files that could be used at all. A file already
    # refused for its type is not also a second invoice, and reporting it as one names
    # an innocent file in the count and tells the operator something untrue.
    supported = [
        file
        for file in files
        if _extension_of(file.file_name) in SUPPORTED_EXTENSIONS
    ]
    problems = [*_unsupported_types(files), *_role_counts(supported)]
    if problems:
        raise SubmissionRejected(problems)


def _unsupported_types(files: Sequence[SubmittedFile]) -> list[SubmissionProblem]:
    """One problem per offending file: the operator removes them in one pass."""
    return [
        SubmissionProblem(
            code=IntakeErrorCode.UNSUPPORTED_FILE_TYPE,
            detail=(
                f"extension {_extension_of(file.file_name) or '(none)'!r} is not one of "
                f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
            file_name=file.file_name,
        )
        for file in files
        if _extension_of(file.file_name) not in SUPPORTED_EXTENSIONS
    ]


def _role_counts(files: Sequence[SubmittedFile]) -> list[SubmissionProblem]:
    """Exactly one invoice, at most one consignment note. Supporting roles are not counted."""
    named_by_role: dict[DocumentRole, list[str]] = {}
    for file in files:
        named_by_role.setdefault(role_of(file), []).append(file.file_name)

    invoices = named_by_role.get(DocumentRole.INVOICE, [])
    notes = named_by_role.get(DocumentRole.CONSIGNMENT_NOTE, [])

    problems: list[SubmissionProblem] = []
    if not invoices:
        problems.append(
            SubmissionProblem(
                code=IntakeErrorCode.NO_INVOICE,
                detail=(
                    "no file is an invoice: a declaration is drafted from one, and "
                    "catalogues, specifications and prior declarations never count as it"
                ),
            )
        )
    elif len(invoices) > 1:
        problems.append(
            SubmissionProblem(
                code=IntakeErrorCode.MULTIPLE_INVOICES,
                detail=f"{len(invoices)} files are invoices: {', '.join(invoices)}",
            )
        )

    if len(notes) > 1:
        problems.append(
            SubmissionProblem(
                code=IntakeErrorCode.MULTIPLE_CONSIGNMENT_NOTES,
                detail=f"{len(notes)} files are consignment notes: {', '.join(notes)}",
            )
        )
    return problems


def _extension_of(file_name: str) -> str:
    """The lowercased extension including its dot, or an empty string when there is none."""
    stem, dot, extension = file_name.rpartition(".")
    return f".{extension.casefold()}" if dot and stem else ""
