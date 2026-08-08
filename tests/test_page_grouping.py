"""The page grouper, and the one policy it exists to hold.

Only the two positive verdicts move a page off the role of the file it came from. An
`other` verdict, a missing verdict, a verdict numbered outside the batch and a page
verdicted twice all leave the page on its hint, and no page is ever dropped. Losing a
real goods page loses goods from a customs declaration; carrying a stray one costs noise.
"""

from __future__ import annotations

import pytest

from deepclare.domain import DocumentRole, PageClass
from deepclare.intake import (
    IntakeErrorCode,
    PageVerdict,
    RenderedPage,
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
    grouped = group_pages(
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
    grouped = group_pages(
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
    grouped = group_pages(
        [page(page_number=1), page("doc2", 1, DocumentRole.CONSIGNMENT_NOTE)], []
    )
    assert len(grouped.invoice.pages) == 1
    assert grouped.consignment_note is not None
    assert grouped.invoice.pages[0].classification.verdict is None


def test_a_verdict_numbered_outside_the_batch_is_discarded() -> None:
    grouped = group_pages(
        [page(hint=DocumentRole.CONSIGNMENT_NOTE), page("doc2", 1)],
        [PageVerdict(page=9, page_type=PageClass.INVOICE)],
    )
    assert grouped.consignment_note is not None
    assert len(grouped.consignment_note.pages) == 1
    assert grouped.invoice.pages[0].rendered.source_document_id == "doc2"


def test_a_page_verdicted_twice_falls_back_to_its_hint() -> None:
    """Two answers for one page are a contradiction, not two verdicts."""
    grouped = group_pages(
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
    grouped = group_pages(
        [page()],
        [PageVerdict(page=1, page_type=PageClass.CONSIGNMENT_NOTE)] * 3,
    )
    assert grouped.consignment_note is None
    assert grouped.invoice.pages[0].classification.verdict is None


def test_verdicts_count_over_the_batch_not_over_the_source_file() -> None:
    """Batch position 2 is doc2's first page; the verdict must land there."""
    grouped = group_pages(
        [page("doc1", 1), page("doc2", 1)],
        [
            PageVerdict(page=1, page_type=PageClass.INVOICE),
            PageVerdict(page=2, page_type=PageClass.CONSIGNMENT_NOTE),
        ],
    )
    assert grouped.consignment_note is not None
    assert grouped.consignment_note.pages[0].rendered.source_document_id == "doc2"


# --- what the grouper produces around the two documents -------------------------


def test_no_page_reads_as_an_invoice_is_a_blocking_rejection() -> None:
    with pytest.raises(SubmissionRejected) as excinfo:
        group_pages(
            [page(hint=DocumentRole.CONSIGNMENT_NOTE)],
            [PageVerdict(page=1, page_type=PageClass.OTHER)],
        )
    assert [p.code for p in excinfo.value.problems] == [IntakeErrorCode.NO_INVOICE_PAGE]


def test_evidence_is_one_document_per_source_file_never_pooled() -> None:
    grouped = group_pages(
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
    grouped = group_pages([page("doc1", n) for n in (1, 2, 3)], [])
    assert [p.rendered.source_page_number for p in grouped.invoice.pages] == [1, 2, 3]


def test_every_page_is_accounted_for_and_none_is_dropped() -> None:
    pages = [
        page("doc1", 1),
        page("doc1", 2),
        page("doc2", 1, DocumentRole.CONSIGNMENT_NOTE),
        page("doc3", 1, DocumentRole.CATALOG_SPEC),
    ]
    grouped = group_pages(pages, [PageVerdict(page=2, page_type=PageClass.OTHER)])
    placed = (
        list(grouped.invoice.pages)
        + list(grouped.consignment_note.pages if grouped.consignment_note else [])
        + [p for document in grouped.supporting_evidence for p in document.pages]
    )
    assert len(placed) == len(pages)


def test_grouping_nothing_is_a_caller_error() -> None:
    with pytest.raises(ValueError):
        group_pages([], [])
