"""The document router: three buckets, and the first look at what the bytes really are.

Every file lands in exactly one of invoice / consignment note / supporting evidence, by
its role. The bucket invariants restate the gate's counting rules on purpose: the gate
counts names, the router counts documents, and the second is what the rest of the
pipeline depends on. If the two ever disagree the router is right and the run stops here.

This is also where a name stops being trusted. Each file's format class is decided from
its bytes, and a file nothing recognizes is refused — a file that passes a name check and
then cannot be opened is an intake failure, not a reading failure. The format class is a
container question only (PDF / image / workbook / XML); nothing here forms an opinion
about how readable a document is.

Identity: intake assigns each document a short id and keeps the file name beside it.
Every value the pipeline later extracts names its source document by that id, so the id
has to be unique within a submission whatever the client called its files.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from deepclare.domain import DocumentRole
from deepclare.intake.errors import (
    IntakeErrorCode,
    SubmissionProblem,
    SubmissionRejected,
)
from deepclare.intake.formats import FileFormat, detect_format
from deepclare.intake.roles import role_of
from deepclare.intake.submission import SubmittedFile


class RoutedDocument(BaseModel):
    """One submitted file, identified, roled and format-classed."""

    model_config = ConfigDict(frozen=True)

    document_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    role: DocumentRole
    role_was_declared: bool
    """False when the role came from the file name. Worth keeping: an inferred role is a
    weaker hint than a declared one, and it is the hint that decides where a doubtful
    page lands."""

    file_format: FileFormat
    content: bytes = Field(min_length=1)


class RoutedSubmission(BaseModel):
    """The three buckets. Exactly one invoice, at most one consignment note."""

    model_config = ConfigDict(frozen=True)

    invoice: RoutedDocument
    consignment_note: RoutedDocument | None = None
    supporting_evidence: tuple[RoutedDocument, ...] = ()
    """Catalogues, specifications and prior declarations, in submission order. Each keeps
    its own role; intake does not know what any of them is for."""

    def documents_in_order(self) -> tuple[RoutedDocument, ...]:
        """Every document, invoice first, then the note, then evidence.

        This is the order pages are rendered and presented to the page classifier, and
        page numbers in a classifier verdict count over it. One definition, so the
        rasterizer and whoever reads the verdicts cannot drift apart.
        """
        note = (self.consignment_note,) if self.consignment_note else ()
        return (self.invoice, *note, *self.supporting_evidence)


def route_documents(files: Sequence[SubmittedFile]) -> RoutedSubmission:
    """Split a checked submission into its three buckets, or raise SubmissionRejected."""
    documents = [
        _describe(file, position) for position, file in enumerate(files, start=1)
    ]

    problems = _unreadable(documents)
    invoices = [d for d in documents if d.role is DocumentRole.INVOICE]
    notes = [d for d in documents if d.role is DocumentRole.CONSIGNMENT_NOTE]
    problems.extend(_bucket_problems(invoices, notes))
    if problems:
        raise SubmissionRejected(problems)

    return RoutedSubmission(
        invoice=invoices[0],
        consignment_note=notes[0] if notes else None,
        supporting_evidence=tuple(
            d
            for d in documents
            if d.role
            in (DocumentRole.CATALOG_SPEC, DocumentRole.PRIOR_DECLARATION)
        ),
    )


def _describe(file: SubmittedFile, position: int) -> RoutedDocument:
    return RoutedDocument(
        document_id=f"doc{position}",
        file_name=file.file_name,
        role=role_of(file),
        role_was_declared=file.declared_role is not None,
        file_format=detect_format(file.content),
        content=file.content,
    )


def _unreadable(documents: Sequence[RoutedDocument]) -> list[SubmissionProblem]:
    return [
        SubmissionProblem(
            code=IntakeErrorCode.UNREADABLE_CONTENT,
            detail=(
                "the file's contents match no supported format; the name promised "
                "something the bytes do not deliver"
            ),
            file_name=document.file_name,
        )
        for document in documents
        if document.file_format is FileFormat.UNKNOWN
    ]


def _bucket_problems(
    invoices: Sequence[RoutedDocument], notes: Sequence[RoutedDocument]
) -> list[SubmissionProblem]:
    problems: list[SubmissionProblem] = []
    if not invoices:
        problems.append(
            SubmissionProblem(
                code=IntakeErrorCode.NO_INVOICE,
                detail="no document routed to the invoice bucket",
            )
        )
    elif len(invoices) > 1:
        problems.append(
            SubmissionProblem(
                code=IntakeErrorCode.MULTIPLE_INVOICES,
                detail=(
                    "a second document routed to the invoice bucket: "
                    f"{', '.join(d.file_name for d in invoices)}"
                ),
            )
        )
    if len(notes) > 1:
        problems.append(
            SubmissionProblem(
                code=IntakeErrorCode.MULTIPLE_CONSIGNMENT_NOTES,
                detail=(
                    "a second document routed to the consignment-note bucket: "
                    f"{', '.join(d.file_name for d in notes)}"
                ),
            )
        )
    return problems
