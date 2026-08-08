"""Reading a role out of a file name, and the precedence between the keyword classes."""

from __future__ import annotations

import pytest

from deepclare.domain import DocumentRole
from deepclare.intake import SubmittedFile, infer_role_from_filename, role_of


@pytest.mark.parametrize(
    "file_name",
    [
        "cmr.pdf",
        "CMR12345.pdf",
        "scan-CMR-2026.pdf",
        "consignment note.pdf",
        "waybill.pdf",
        "накладная.pdf",
        "բեռնագիր.pdf",
    ],
)
def test_a_consignment_note_is_recognised(file_name: str) -> None:
    assert infer_role_from_filename(file_name) is DocumentRole.CONSIGNMENT_NOTE


@pytest.mark.parametrize(
    "file_name",
    [
        "catalog.pdf",
        "catalogue.pdf",
        "SPEC-sheet.pdf",
        "datasheet.pdf",
        "brochure.pdf",
        "каталог.pdf",
        "կատալոգ.pdf",
    ],
)
def test_supporting_evidence_is_recognised(file_name: str) -> None:
    assert infer_role_from_filename(file_name) is DocumentRole.CATALOG_SPEC


@pytest.mark.parametrize(
    "file_name",
    ["export.xml", "EXPORT.XML", "declaration.pdf", "декларация.pdf", "հայտարարագիր.pdf"],
)
def test_a_prior_declaration_is_recognised(file_name: str) -> None:
    assert infer_role_from_filename(file_name) is DocumentRole.PRIOR_DECLARATION


@pytest.mark.parametrize(
    "file_name", ["invoice.pdf", "FACTURA-2026.pdf", "scan_003.pdf", "1.pdf", ""]
)
def test_everything_unrecognised_defaults_to_the_invoice(file_name: str) -> None:
    """A missing invoice is the fatal case, so the leftover guess is the cheap one."""
    assert infer_role_from_filename(file_name) is DocumentRole.INVOICE


def test_the_word_invoice_needs_no_keyword_of_its_own() -> None:
    assert infer_role_from_filename("invoice.pdf") is DocumentRole.INVOICE


def test_matching_is_a_substring_test_not_a_word_test() -> None:
    """Real names run words together, so token splitting would miss them."""
    assert infer_role_from_filename("CMR12345.pdf") is DocumentRole.CONSIGNMENT_NOTE
    assert infer_role_from_filename("productcatalogue2026.pdf") is DocumentRole.CATALOG_SPEC


def test_matching_ignores_case() -> None:
    assert infer_role_from_filename("Cmr.PDF") is DocumentRole.CONSIGNMENT_NOTE
    assert infer_role_from_filename("КАТАЛОГ.pdf") is DocumentRole.CATALOG_SPEC


def test_a_consignment_note_keyword_beats_a_catalogue_keyword() -> None:
    assert infer_role_from_filename("cmr-catalogue.pdf") is DocumentRole.CONSIGNMENT_NOTE


def test_a_catalogue_keyword_beats_the_xml_extension() -> None:
    assert infer_role_from_filename("catalogue.xml") is DocumentRole.CATALOG_SPEC


def test_a_consignment_note_keyword_beats_the_xml_extension() -> None:
    assert infer_role_from_filename("cmr.xml") is DocumentRole.CONSIGNMENT_NOTE


def test_the_xml_extension_alone_settles_a_prior_declaration() -> None:
    assert infer_role_from_filename("2026-03-11.xml") is DocumentRole.PRIOR_DECLARATION


def test_an_xml_named_like_an_invoice_is_still_a_prior_declaration() -> None:
    """Nothing else among the sources is an XML, so the extension is the stronger signal."""
    assert infer_role_from_filename("invoice.xml") is DocumentRole.PRIOR_DECLARATION


def test_a_declared_role_wins_over_the_name() -> None:
    file = SubmittedFile(
        file_name="cmr.pdf", content=b"x", declared_role=DocumentRole.INVOICE
    )
    assert role_of(file) is DocumentRole.INVOICE


def test_an_undeclared_role_falls_to_the_name() -> None:
    file = SubmittedFile(file_name="cmr.pdf", content=b"x")
    assert role_of(file) is DocumentRole.CONSIGNMENT_NOTE
