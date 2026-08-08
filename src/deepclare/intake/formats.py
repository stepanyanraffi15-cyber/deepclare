"""What an uploaded file actually is, decided from its bytes.

The submission gate judges names because that is all it is allowed to see. Everything
after it judges content: a file whose name says `.pdf` and whose bytes say otherwise is
refused here rather than three stages later.

This is a **format-class** decision — PDF, image, workbook, XML — and nothing more. It
is emphatically not a judgment about how well a document can be read. In particular
nothing in intake may look at whether a PDF carries an embedded text layer, how long
that layer is, or what resolution its rasters are: those three signals are uncorrelated
with what can actually be extracted, and in the measured corpus they invert, so a router
that prefers embedded text takes the corrupt path on the densest document in the pile.
Route on format class; never on text quality.
"""

from __future__ import annotations

from enum import StrEnum

_SNIFF_WINDOW = 1024
"""How far in to look for a leading signature. A PDF is allowed junk before its header
and real ones have it, so the marker is searched for rather than required at byte 0."""

_PDF_MARKER = b"%PDF-"
_PNG_MARKER = b"\x89PNG\r\n\x1a\n"
_JPEG_MARKER = b"\xff\xd8\xff"
_ZIP_MARKER = b"PK\x03\x04"
_WORKBOOK_ENTRY = b"xl/workbook.xml"
"""A workbook is a ZIP container; this entry name is what tells it apart from the other
office formats that share the container. Entry names are stored uncompressed, so the
literal appears in the archive."""

_XML_MARKERS = (b"<?xml", b"<")
_BYTE_ORDER_MARK = b"\xef\xbb\xbf"


class FileFormat(StrEnum):
    """The format class of an uploaded file, as its bytes report it."""

    PDF = "pdf"
    PNG = "png"
    JPEG = "jpeg"
    WORKBOOK = "workbook"
    """A spreadsheet. The one input with no pages: there is nothing for vision to read
    because it already is structured data."""

    XML = "xml"
    UNKNOWN = "unknown"
    """Nothing recognized it. Blocking — see the unreadable-content code."""


def detect_format(content: bytes) -> FileFormat:
    """Classify a file by its leading bytes. The file name is deliberately not an input."""
    head = content[:_SNIFF_WINDOW]

    if _PDF_MARKER in head:
        return FileFormat.PDF
    if head.startswith(_PNG_MARKER):
        return FileFormat.PNG
    if head.startswith(_JPEG_MARKER):
        return FileFormat.JPEG
    if head.startswith(_ZIP_MARKER):
        return FileFormat.WORKBOOK if _WORKBOOK_ENTRY in content else FileFormat.UNKNOWN
    if _looks_like_xml(head):
        return FileFormat.XML
    return FileFormat.UNKNOWN


def _looks_like_xml(head: bytes) -> bool:
    stripped = head.removeprefix(_BYTE_ORDER_MARK).lstrip()
    return any(stripped.startswith(marker) for marker in _XML_MARKERS)


def is_page_bearing(file_format: FileFormat) -> bool:
    """Whether the format is made of pages. An image counts: it is one page.

    A workbook and an XML are not, so they never reach the rasterizer and never reach
    page grouping — a workbook invoice is unambiguously the invoice and is read directly.
    """
    return file_format in (FileFormat.PDF, FileFormat.PNG, FileFormat.JPEG)
