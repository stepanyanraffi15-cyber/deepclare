"""What the rasterizer does with the documents that have no pages.

No PDF is rendered here: these are the paths that must not reach the renderer at all.
"""

from __future__ import annotations

import pytest

from deepclare.domain import DocumentRole
from deepclare.intake import (
    FileFormat,
    RoutedDocument,
    rasterize_document,
    rasterize_documents,
)


def document(file_format: FileFormat, name: str = "f") -> RoutedDocument:
    return RoutedDocument(
        document_id="doc1",
        file_name=name,
        role=DocumentRole.PRIOR_DECLARATION,
        role_was_declared=False,
        file_format=file_format,
        content=b"irrelevant",
    )


@pytest.mark.parametrize("file_format", [FileFormat.XML, FileFormat.WORKBOOK])
def test_a_page_less_document_is_skipped_not_refused(file_format: FileFormat) -> None:
    """A prior declaration or a spreadsheet beside a PDF invoice is an ordinary
    submission, and each goes to its own reader."""
    assert rasterize_documents([document(file_format)]) == ()


def test_handing_a_page_less_document_to_the_single_form_is_still_an_error() -> None:
    with pytest.raises(ValueError, match="carries no pages"):
        rasterize_document(document(FileFormat.XML))


def test_a_bare_image_upload_says_what_is_missing() -> None:
    """The gate accepts .png/.jpg and nothing downstream can consume one."""
    with pytest.raises(NotImplementedError, match="image"):
        rasterize_document(document(FileFormat.PNG, "scan.png"))
