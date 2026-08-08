"""The page grouper, the one policy it exists to hold, and the documents that have no
pages at all.

Only the two positive verdicts move a page off the role of the file it came from. An
`other` verdict, a missing verdict, a verdict numbered outside the batch and a page
verdicted twice all leave the page on its hint, and no page is ever dropped. Losing a
real goods page loses goods from a customs declaration; carrying a stray one costs noise.
The same rule at document scale: a workbook or an XML is never rasterized, so grouping
carries it through whole rather than letting it fall out of the run.
"""

from __future__ import annotations

import pytest

from deepclare.domain import DocumentRole, PageClass
from deepclare.intake import (
    FileFormat,
    IntakeErrorCode,
    PageVerdict,
    RenderedPage,
    RoutedDocument,
    RoutedSubmission,
    SubmissionRejected,
    assign_page_role,
    group_pages,
)


def page(
    document_id: str = "doc1",
    page_number: int = 1,
    hint: DocumentRole = DocumentRole.INVOICE,
) -> RenderedPage:
    return RenderedPage(
        source_document_id=document_id,
        source_page_number=page_number,
        role_hint=hint,
        image=b"\x89PNG\r\n\x1a\n",
        width_px=1654,
        height_px=2339,
        dpi=200,
    )


def document(
    document_id: str = "doc1",
    role: DocumentRole = DocumentRole.INVOICE,
    file_format: FileFormat = FileFormat.PDF,
) -> RoutedDocument:
    return RoutedDocument(
        document_id=document_id,
        file_name=f"{document_id}.{file_format}",
        role=role,
        role_was_declared=False,
        file_format=file_format,
        content=b"%PDF-1.7",
    )


def submission(*documents: RoutedDocument) -> RoutedSubmission:
    """A routed submission covering exactly the documents given, in their roles."""
    notes = [d for d in documents if d.role is DocumentRole.CONSIGNMENT_NOTE]
    routed = RoutedSubmission(
        invoice=next(d for d in documents if d.role is DocumentRole.INVOICE),
        consignment_note=notes[0] if notes else None,
        supporting_evidence=tuple(
            d
            for d in documents
            if d.role
            in (DocumentRole.CATALOG_SPEC, DocumentRole.PRIOR_DECLARATION)
        ),
    )
    # The router's own rule: one invoice, at most one note. A second of either would be
    # silently discarded here and the fixture would be testing a submission nobody built.
    assert len(routed.documents_in_order()) == len(documents)
    return routed


def grouped_from(
    pages: list[RenderedPage],
    verdicts: list[PageVerdict],
    *,
    extra: tuple[RoutedDocument, ...] = (),
):
    """Group `pages`, inventing the routed submission they must have come from.

    Every distinct source id becomes one document, keeping the role its pages were
    hinted with, so the batch and the submission agree by construction.
    """
    seen: dict[str, DocumentRole] = {}
    for rendered in pages:
        seen.setdefault(rendered.source_document_id, rendered.role_hint)
    documents = tuple(
        document(document_id, role) for document_id, role in seen.items()
    ) + extra
    return group_pages(submission(*documents), pages, verdicts)


# --- the policy, stated directly ------------------------------------------------


@pytest.mark.parametrize("hint", list(DocumentRole))
def test_an_invoice_verdict_moves_a_page_whatever_the_hint(hint: DocumentRole) -> None:
    assert assign_page_role(PageClass.INVOICE, hint) is DocumentRole.INVOICE


@pytest.mark.parametrize("hint", list(DocumentRole))
def test_a_note_verdict_moves_a_page_whatever_the_hint(hint: DocumentRole) -> None:
    assert (
        assign_page_role(PageClass.CONSIGNMENT_NOTE, hint)
        is DocumentRole.CONSIGNMENT_NOTE
    )


@pytest.mark.parametrize("hint", list(DocumentRole))
def test_an_other_verdict_never_moves_a_page(hint: DocumentRole) -> None:
    """The classifier's third label is overridden on purpose; it only removes a record."""
    assert assign_page_role(PageClass.OTHER, hint) is hint


@pytest.mark.parametrize("hint", list(DocumentRole))
def test_a_missing_verdict_never_moves_a_page(hint: DocumentRole) -> None:
    assert assign_page_role(None, hint) is hint


# --- the same policy through the grouper ----------------------------------------


def test_an_other_verdict_leaves_an_invoice_page_on_the_invoice() -> None:
    grouped = grouped_from(
        [page(page_number=1), page(page_number=2)],
        [
            PageVerdict(page=1, page_type=PageClass.INVOICE),
            PageVerdict(page=2, page_type=PageClass.OTHER),
        ],
    )
    assert len(grouped.invoice.pages) == 2
    assert grouped.supporting_evidence == ()
    overridden = grouped.invoice.pages[1].classification
    assert overridden.verdict is PageClass.OTHER
    assert overridden.assigned_role is DocumentRole.INVOICE


def test_a_note_verdict_splits_one_uploaded_file_into_two_documents() -> None:
    """One scan holding an invoice and a CMR is the ordinary case, not the exception."""
    grouped = grouped_from(
        [page(page_number=1), page(page_number=2)],
        [
            PageVerdict(page=1, page_type=PageClass.INVOICE),
            PageVerdict(page=2, page_type=PageClass.CONSIGNMENT_NOTE),
        ],
    )
    assert len(grouped.invoice.pages) == 1
    assert grouped.consignment_note is not None
    assert len(grouped.consignment_note.pages) == 1


def test_no_verdicts_at_all_leaves_every_page_on_its_hint() -> None:
    grouped = grouped_from(
        [page(page_number=1), page("doc2", 1, DocumentRole.CONSIGNMENT_NOTE)], []
    )
    assert len(grouped.invoice.pages) == 1
    assert grouped.consignment_note is not None
    assert grouped.invoice.pages[0].classification.verdict is None


def test_a_verdict_numbered_outside_the_batch_is_discarded() -> None:
    grouped = grouped_from(
        [page(), page("doc2", 1, DocumentRole.CONSIGNMENT_NOTE)],
        [PageVerdict(page=9, page_type=PageClass.CONSIGNMENT_NOTE)],
    )
    assert grouped.consignment_note is not None
    assert len(grouped.consignment_note.pages) == 1
    assert grouped.invoice.pages[0].rendered.source_document_id == "doc1"


def test_a_page_verdicted_twice_falls_back_to_its_hint() -> None:
    """Two answers for one page are a contradiction, not two verdicts."""
    grouped = grouped_from(
        [page()],
        [
            PageVerdict(page=1, page_type=PageClass.CONSIGNMENT_NOTE),
            PageVerdict(page=1, page_type=PageClass.OTHER),
        ],
    )
    assert grouped.consignment_note is None
    assert len(grouped.invoice.pages) == 1
    assert grouped.invoice.pages[0].classification.verdict is None


def test_a_page_verdicted_three_times_still_falls_back() -> None:
    grouped = grouped_from(
        [page()],
        [PageVerdict(page=1, page_type=PageClass.CONSIGNMENT_NOTE)] * 3,
    )
    assert grouped.consignment_note is None
    assert grouped.invoice.pages[0].classification.verdict is None


def test_verdicts_count_over_the_batch_not_over_the_source_file() -> None:
    """Batch position 2 is doc2's first page; the verdict must land there."""
    grouped = grouped_from(
        [page("doc1", 1), page("doc2", 1, DocumentRole.CATALOG_SPEC)],
        [
            PageVerdict(page=1, page_type=PageClass.INVOICE),
            PageVerdict(page=2, page_type=PageClass.CONSIGNMENT_NOTE),
        ],
    )
    assert grouped.consignment_note is not None
    assert grouped.consignment_note.pages[0].rendered.source_document_id == "doc2"


# --- what the grouper produces around the two documents -------------------------


def test_no_page_reads_as_an_invoice_is_a_blocking_rejection() -> None:
    """Every page of the invoice file read as the note, so there is nothing to draft."""
    with pytest.raises(SubmissionRejected) as excinfo:
        grouped_from(
            [page()], [PageVerdict(page=1, page_type=PageClass.CONSIGNMENT_NOTE)]
        )
    assert [p.code for p in excinfo.value.problems] == [IntakeErrorCode.NO_INVOICE_PAGE]


def test_evidence_is_one_document_per_source_file_never_pooled() -> None:
    grouped = grouped_from(
        [
            page("doc1", 1),
            page("doc2", 1, DocumentRole.CATALOG_SPEC),
            page("doc2", 2, DocumentRole.CATALOG_SPEC),
            page("doc3", 1, DocumentRole.CATALOG_SPEC),
        ],
        [],
    )
    assert [len(d.pages) for d in grouped.supporting_evidence] == [2, 1]
    assert {d.role for d in grouped.supporting_evidence} == {DocumentRole.CATALOG_SPEC}


def test_page_order_within_a_document_is_presentation_order() -> None:
    grouped = grouped_from([page("doc1", n) for n in (1, 2, 3)], [])
    assert [p.rendered.source_page_number for p in grouped.invoice.pages] == [1, 2, 3]


def test_every_page_is_accounted_for_and_none_is_dropped() -> None:
    pages = [
        page("doc1", 1),
        page("doc1", 2),
        page("doc2", 1, DocumentRole.CONSIGNMENT_NOTE),
        page("doc3", 1, DocumentRole.CATALOG_SPEC),
    ]
    grouped = grouped_from(pages, [PageVerdict(page=2, page_type=PageClass.OTHER)])
    placed = (
        list(grouped.invoice.pages)
        + list(grouped.consignment_note.pages if grouped.consignment_note else [])
        + [p for document in grouped.supporting_evidence for p in document.pages]
    )
    assert len(placed) == len(pages)


def test_grouping_nothing_is_a_caller_error() -> None:
    with pytest.raises(ValueError):
        group_pages(submission(document()), [], [])


# --- the documents that never had pages -----------------------------------------


def test_a_page_less_document_is_carried_through_rather_than_dropped() -> None:
    """A workbook catalogue and an XML prior filing are never rasterized; losing them
    silently is the page-loss failure at document scale."""
    catalogue = document("doc2", DocumentRole.CATALOG_SPEC, FileFormat.WORKBOOK)
    prior = document("doc3", DocumentRole.PRIOR_DECLARATION, FileFormat.XML)
    grouped = grouped_from([page()], [], extra=(catalogue, prior))
    assert [d.document_id for d in grouped.page_less] == ["doc2", "doc3"]
    assert [d.file_format for d in grouped.page_less] == [
        FileFormat.WORKBOOK,
        FileFormat.XML,
    ]
    assert grouped.supporting_evidence == ()


def test_a_page_bearing_submission_has_no_page_less_documents() -> None:
    assert grouped_from([page()], []).page_less == ()


def test_a_page_less_invoice_never_reaches_grouping() -> None:
    """It is unambiguously the invoice and is read directly, so this is a caller's
    mistake — not the 'no page reads as an invoice' rejection it would otherwise become."""
    workbook = document("doc1", DocumentRole.INVOICE, FileFormat.WORKBOOK)
    note = document("doc2", DocumentRole.CONSIGNMENT_NOTE)
    with pytest.raises(ValueError, match="carries no pages"):
        group_pages(
            submission(workbook, note),
            [page("doc2", 1, DocumentRole.CONSIGNMENT_NOTE)],
            [],
        )


def test_a_batch_missing_a_page_bearing_document_is_refused() -> None:
    with pytest.raises(ValueError, match="does not match the routed submission"):
        group_pages(
            submission(document(), document("doc2", DocumentRole.CONSIGNMENT_NOTE)),
            [page("doc1", 1)],
            [],
        )


def test_a_page_from_a_document_the_router_never_saw_is_refused() -> None:
    with pytest.raises(ValueError, match="does not match the routed submission"):
        group_pages(submission(document()), [page("doc1", 1), page("doc9", 1)], [])
