"""The submission gate's four structural rules.

Names and declared roles only — no byte of content is involved anywhere in this file,
which is the same thing the gate itself is limited to.
"""

from __future__ import annotations

import pytest

from deepclare.domain import DocumentRole
from deepclare.intake import (
    IntakeErrorCode,
    SubmissionProblem,
    SubmissionRejected,
    SubmittedFile,
    check_submission,
)


def file(name: str, role: DocumentRole | None = None) -> SubmittedFile:
    """A submitted file with content the gate is not allowed to look at."""
    return SubmittedFile(file_name=name, content=b"not read by the gate", declared_role=role)


def codes_of(excinfo: pytest.ExceptionInfo[SubmissionRejected]) -> list[IntakeErrorCode]:
    return [problem.code for problem in excinfo.value.problems]


def reject(files: list[SubmittedFile]) -> pytest.ExceptionInfo[SubmissionRejected]:
    with pytest.raises(SubmissionRejected) as excinfo:
        check_submission(files)
    return excinfo


def test_a_lone_invoice_passes() -> None:
    assert check_submission([file("invoice.pdf")]) is None


def test_an_invoice_a_note_and_two_catalogues_pass() -> None:
    assert (
        check_submission(
            [
                file("invoice.pdf"),
                file("cmr.pdf"),
                file("catalogue-a.pdf"),
                file("catalogue-b.pdf"),
            ]
        )
        is None
    )


def test_an_empty_submission_is_refused() -> None:
    assert codes_of(reject([])) == [IntakeErrorCode.NO_FILES]


def test_an_unsupported_extension_is_refused_and_names_the_file() -> None:
    problems = reject([file("invoice.pdf"), file("photo.gif")]).value.problems
    unsupported = [p for p in problems if p.code is IntakeErrorCode.UNSUPPORTED_FILE_TYPE]
    assert [p.file_name for p in unsupported] == ["photo.gif"]


def test_a_file_with_no_extension_is_refused() -> None:
    assert IntakeErrorCode.UNSUPPORTED_FILE_TYPE in codes_of(reject([file("invoice")]))


def test_every_offending_file_is_reported_not_just_the_first() -> None:
    problems = reject(
        [file("invoice.pdf"), file("a.gif"), file("b.docx")]
    ).value.problems
    assert sorted(
        p.file_name for p in problems if p.code is IntakeErrorCode.UNSUPPORTED_FILE_TYPE
    ) == ["a.gif", "b.docx"]


def test_extension_matching_ignores_case() -> None:
    assert check_submission([file("INVOICE.PDF")]) is None


def test_a_submission_with_no_invoice_is_refused() -> None:
    assert codes_of(reject([file("cmr.pdf")])) == [IntakeErrorCode.NO_INVOICE]


def test_two_invoices_are_refused_and_both_are_named() -> None:
    excinfo = reject([file("invoice-a.pdf"), file("invoice-b.pdf")])
    assert codes_of(excinfo) == [IntakeErrorCode.MULTIPLE_INVOICES]
    detail = excinfo.value.problems[0].detail
    assert "invoice-a.pdf" in detail and "invoice-b.pdf" in detail


def test_two_consignment_notes_are_refused() -> None:
    excinfo = reject([file("invoice.pdf"), file("cmr-1.pdf"), file("cmr-2.pdf")])
    assert codes_of(excinfo) == [IntakeErrorCode.MULTIPLE_CONSIGNMENT_NOTES]


def test_a_catalogue_never_counts_as_the_invoice() -> None:
    assert codes_of(reject([file("catalogue.pdf"), file("cmr.pdf")])) == [
        IntakeErrorCode.NO_INVOICE
    ]


def test_a_prior_declaration_alone_is_refused_for_having_no_invoice() -> None:
    """Not for being an XML: the XML is a supported upload, it is just not an invoice."""
    assert codes_of(reject([file("prior-declaration.xml")])) == [
        IntakeErrorCode.NO_INVOICE
    ]


def test_a_declared_role_overrides_what_the_name_says() -> None:
    """A file named like a consignment note, declared to be the invoice, is the invoice."""
    assert check_submission([file("cmr.pdf", DocumentRole.INVOICE)]) is None


def test_a_declared_supporting_role_can_leave_a_submission_without_an_invoice() -> None:
    assert codes_of(reject([file("invoice.pdf", DocumentRole.CATALOG_SPEC)])) == [
        IntakeErrorCode.NO_INVOICE
    ]


def test_unrelated_problems_are_reported_together() -> None:
    codes = codes_of(reject([file("a.gif"), file("cmr-1.pdf"), file("cmr-2.pdf")]))
    assert IntakeErrorCode.UNSUPPORTED_FILE_TYPE in codes
    assert IntakeErrorCode.NO_INVOICE in codes
    assert IntakeErrorCode.MULTIPLE_CONSIGNMENT_NOTES in codes


def test_a_refused_file_is_not_also_counted_as_an_invoice() -> None:
    """It would name an innocent file in the count and state something untrue."""
    codes = codes_of(reject([file("invoice.pdf"), file("photo.gif")]))
    assert codes == [IntakeErrorCode.UNSUPPORTED_FILE_TYPE]


def test_a_rejection_must_carry_a_reason() -> None:
    with pytest.raises(ValueError):
        SubmissionRejected([])


def test_the_message_carries_every_code_and_the_file_at_fault() -> None:
    rejection = SubmissionRejected(
        [
            SubmissionProblem(
                code=IntakeErrorCode.UNSUPPORTED_FILE_TYPE,
                detail="nope",
                file_name="photo.gif",
            ),
            SubmissionProblem(code=IntakeErrorCode.NO_INVOICE, detail="none"),
        ]
    )
    assert "photo.gif" in str(rejection)
    assert IntakeErrorCode.UNSUPPORTED_FILE_TYPE in str(rejection)
    assert IntakeErrorCode.NO_INVOICE in str(rejection)
