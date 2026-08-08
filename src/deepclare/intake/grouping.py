"""The page grouper: turn classified pages into logical documents.

One rule decides everything here, and it is a policy rather than a fallback:

    **Over-inclusion is deliberate.** Only the two positive verdicts — invoice and
    consignment note — move a page off the role of the file it came from. Every other
    outcome, including the classifier's own `other` verdict, leaves the page where its
    file said it was, and a file's role defaults to invoice. No page is ever dropped.

The reason is domain truth, not caution. Dropping a real invoice or consignment-note page
loses goods from a customs declaration; carrying a stray cover sheet into a reader costs
noise. Wrong is worse than missing everywhere else in this system, but here missing *is*
the wrong: goods that never reach the declaration cannot be reviewed, because there is
nothing on the page for a human to disagree with.

A consequence worth stating plainly: the classifier's three-value vocabulary behaves as
two values downstream, and the classifier prompt's own "follow the content over the hint"
instruction is overridden for `other`. That is intended. It is written as one named
function rather than left to emerge from a chain of defaults, so that changing the policy
means changing the policy.

The same rule reaches past the pages. A workbook or an XML has no pages, so it is never
rasterized and nothing about it can be grouped — and a document that grouping does not
mention is a document the run has silently dropped, which is the page-loss failure again
at the whole-document scale. So grouping takes the routed submission itself rather than a
loose list of pages: it checks that the batch it was handed accounts for every
page-bearing document, and it carries the page-less ones through untouched for the reader
that handles their format. Everything that entered intake leaves it exactly once.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deepclare.domain import DocumentRole, PageClass, PageClassification
from deepclare.intake.classifier import PageVerdict
from deepclare.intake.errors import (
    IntakeErrorCode,
    SubmissionProblem,
    SubmissionRejected,
)
from deepclare.intake.formats import is_page_bearing
from deepclare.intake.rasterizer import RenderedPage
from deepclare.intake.router import RoutedDocument, RoutedSubmission


class GroupedPage(BaseModel):
    """One rendered page together with the account of where it was placed."""

    model_config = ConfigDict(frozen=True)

    rendered: RenderedPage
    classification: PageClassification

    @model_validator(mode="after")
    def _must_describe_the_same_page(self) -> Self:
        same_page = (
            self.rendered.source_document_id == self.classification.source_document_id
            and self.rendered.source_page_number
            == self.classification.source_page_number
        )
        if not same_page:
            raise ValueError(
                "the image and the classification describe different pages: "
                f"{self.rendered.source_document_id}"
                f"#{self.rendered.source_page_number} vs "
                f"{self.classification.source_document_id}"
                f"#{self.classification.source_page_number}"
            )
        return self


class LogicalDocument(BaseModel):
    """An ordered set of pages read as one document.

    Its pages may come from several uploaded files, and one uploaded file's pages may end
    up in two of these — a single scan holding an invoice and a consignment note is the
    ordinary case, not the exception.
    """

    model_config = ConfigDict(frozen=True)

    role: DocumentRole
    pages: tuple[GroupedPage, ...] = Field(min_length=1)
    """In presentation order. The i-th entry is logical page i+1, which is what a value's
    provenance region counts."""


class GroupedSubmission(BaseModel):
    """What intake hands on: the invoice, the consignment note if there is one, the
    supporting documents left over, and whatever carried no pages at all."""

    model_config = ConfigDict(frozen=True)

    invoice: LogicalDocument
    consignment_note: LogicalDocument | None = None
    """Present only if at least one page was classified as one."""

    supporting_evidence: tuple[LogicalDocument, ...] = ()
    """One per source file, never pooled: two catalogues are two documents."""

    page_less: tuple[RoutedDocument, ...] = ()
    """The workbooks and XML files of the submission, in submission order, exactly as the
    router described them. They were never rasterized and never classified, so there is
    nothing to group and no page classification to record — they are carried whole,
    bytes and all, for the reader that handles their format. Empty is the ordinary case.
    """


def group_pages(
    routed: RoutedSubmission,
    pages: Sequence[RenderedPage],
    verdicts: Sequence[PageVerdict],
) -> GroupedSubmission:
    """Group a submission's rendered pages into logical documents.

    `pages` is the batch exactly as it was presented to the classifier — every page of
    every page-bearing document of `routed`, in `documents_in_order()` order — and a
    verdict's page number counts over that batch. Raises SubmissionRejected when no page
    reads as an invoice: failing loudly beats filing a declaration with no goods on it.
    """
    _check_the_batch_covers_the_submission(routed, pages)

    usable = _verdicts_by_batch_position(verdicts, len(pages))
    grouped = tuple(
        _place(page, usable.get(position))
        for position, page in enumerate(pages, start=1)
    )

    invoice_pages = _with_role(grouped, DocumentRole.INVOICE)
    if not invoice_pages:
        raise SubmissionRejected(
            [
                SubmissionProblem(
                    code=IntakeErrorCode.NO_INVOICE_PAGE,
                    detail=(
                        f"none of the {len(pages)} pages reads as an invoice page, so "
                        "there is nothing to draft goods from"
                    ),
                )
            ]
        )

    note_pages = _with_role(grouped, DocumentRole.CONSIGNMENT_NOTE)
    return GroupedSubmission(
        invoice=LogicalDocument(role=DocumentRole.INVOICE, pages=invoice_pages),
        consignment_note=(
            LogicalDocument(role=DocumentRole.CONSIGNMENT_NOTE, pages=note_pages)
            if note_pages
            else None
        ),
        supporting_evidence=_evidence_documents(grouped),
        page_less=routed.page_less_documents(),
    )


def _check_the_batch_covers_the_submission(
    routed: RoutedSubmission, pages: Sequence[RenderedPage]
) -> None:
    """Refuse a batch that does not account for exactly the page-bearing documents.

    Both halves are caller mistakes rather than bad submissions, so both raise rather
    than reject. A page-bearing document with no page in the batch would be dropped from
    the output in silence; a page from a document the router never saw means the batch
    and the submission describe different runs. The batch's *order* is not checked
    because grouping cannot see it — the order that matters is the one the classifier was
    shown, and a verdict names a position in that batch and nothing else.
    """
    if not is_page_bearing(routed.invoice.file_format):
        raise ValueError(
            f"{routed.invoice.file_name} is a {routed.invoice.file_format} invoice, "
            "which carries no pages: it is unambiguously the invoice and is read "
            "directly by the reader for its format, never grouped"
        )

    expected = {document.document_id for document in routed.page_bearing_documents()}
    presented = {page.source_document_id for page in pages}
    if presented != expected:
        raise ValueError(
            "the page batch does not match the routed submission: expected pages from "
            f"{sorted(expected)}, got {sorted(presented)}"
        )


def assign_page_role(verdict: PageClass | None, role_hint: DocumentRole) -> DocumentRole:
    """Decide which document a page belongs to. This function never drops a page.

    Over-inclusion is the policy: only the two positive verdicts move a page, and `other`
    — like a verdict that never arrived — leaves it with its source file's role. Losing a
    real goods page is worse than carrying a stray one.
    """
    if verdict is PageClass.INVOICE:
        return DocumentRole.INVOICE
    if verdict is PageClass.CONSIGNMENT_NOTE:
        return DocumentRole.CONSIGNMENT_NOTE
    return role_hint


def _verdicts_by_batch_position(
    verdicts: Sequence[PageVerdict], page_count: int
) -> dict[int, PageClass | None]:
    """Index the verdicts by page, keeping only the ones that mean something.

    A page number outside the batch names no page and is discarded. A page number given
    twice is not two verdicts but a contradiction; both are dropped and the page falls
    back to its hint, which is recorded as no verdict at all.
    """
    by_position: dict[int, PageClass | None] = {}
    for verdict in verdicts:
        if not 1 <= verdict.page <= page_count:
            continue
        by_position[verdict.page] = (
            None if verdict.page in by_position else verdict.page_type
        )
    return by_position


def _place(page: RenderedPage, verdict: PageClass | None) -> GroupedPage:
    return GroupedPage(
        rendered=page,
        classification=PageClassification(
            source_document_id=page.source_document_id,
            source_page_number=page.source_page_number,
            verdict=verdict,
            role_hint=page.role_hint,
            assigned_role=assign_page_role(verdict, page.role_hint),
        ),
    )


def _with_role(
    grouped: Sequence[GroupedPage], role: DocumentRole
) -> tuple[GroupedPage, ...]:
    return tuple(page for page in grouped if page.classification.assigned_role is role)


def _evidence_documents(
    grouped: Sequence[GroupedPage],
) -> tuple[LogicalDocument, ...]:
    """One logical document per source file, in first-appearance order."""
    by_source: dict[str, list[GroupedPage]] = {}
    roles: dict[str, DocumentRole] = {}
    for page in grouped:
        role = page.classification.assigned_role
        if role in (DocumentRole.INVOICE, DocumentRole.CONSIGNMENT_NOTE):
            continue
        source = page.rendered.source_document_id
        by_source.setdefault(source, []).append(page)
        roles[source] = role
    return tuple(
        LogicalDocument(role=roles[source], pages=tuple(pages))
        for source, pages in by_source.items()
    )
