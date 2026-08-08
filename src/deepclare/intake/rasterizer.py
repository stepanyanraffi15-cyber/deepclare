"""The page rasterizer: every page of every document, rendered to an image.

One image per page, at a fixed 200 DPI, in document order. There is no conditional path
and no cheap route: the page is rendered whether or not the file carries an embedded text
layer, whether that layer is 400 characters or 400,000, and whatever the resolution of
the rasters inside it. Those three signals are uncorrelated with what can actually be
read off a page — in the measured corpus the sharpest scan carried the worst text layer —
so none of them may become a branch. Intake renders; deciding what a page can yield
belongs to the stage that can compare routes.

Rendering rather than reading the embedded images also fixes two recorded hazards for
free: a raster stored rotated 90° relative to display orientation comes out upright, and
a scanner page stored as two layers that are illegible alone comes out composited.

Everything this module produces — the image and the embedded text alike — is *unverified
candidate evidence*. Nothing has been validated against anything.
"""

from __future__ import annotations

import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import pypdfium2 as pdfium
from pydantic import BaseModel, ConfigDict, Field

from deepclare.domain import DocumentRole
from deepclare.intake.errors import (
    IntakeErrorCode,
    SubmissionProblem,
    SubmissionRejected,
)
from deepclare.intake.formats import FileFormat, is_page_bearing
from deepclare.intake.router import RoutedDocument

RENDER_DPI = 200
PAGE_MEDIA_TYPE = "image/png"

_POINTS_PER_INCH = 72
"""A PDF canvas unit. The render scale is a multiple of it, not a DPI setting."""

_LINE_TOLERANCE_PT = 3.0
"""How far two characters' baselines may differ and still count as one line."""

_WORD_GAP_RATIO = 0.15
"""A gap wider than this fraction of the preceding character's line height is a word
break. Relative rather than absolute because the same absolute gap is a word break in
8-point body text and letter spacing in a 20-point heading. The boxes are the font's
advance boxes, which tile a word without gaps, so the margin against a space — roughly a
quarter of the line height in the faces trade documents use — is wide."""


class RenderedPage(BaseModel):
    """One page of one source file, as an image plus whatever text was embedded in it.

    Both are unverified candidate evidence. In particular `embedded_text` is a
    diagnostic: it is never a routing input, never a reason to skip the image, and never
    evidence that a page is readable. Presence of text is not evidence of usable text.
    """

    model_config = ConfigDict(frozen=True)

    source_document_id: str = Field(min_length=1)
    source_page_number: int = Field(ge=1, description="1-based, within the source file")
    role_hint: DocumentRole
    """The role of the file this page came from. It decides where the page lands when
    the page classifier does not place it."""

    media_type: str = PAGE_MEDIA_TYPE
    image: bytes = Field(min_length=1)
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    dpi: int = Field(gt=0)
    embedded_text: str = ""
    """Position-sorted, because storage order scrambles a tabular invoice. Empty is
    ordinary and says nothing about the page."""


def rasterize_documents(
    documents: Iterable[RoutedDocument],
) -> tuple[RenderedPage, ...]:
    """Render every page of every page-bearing document, in the order given.

    A workbook and an XML carry no pages and are skipped rather than refused: a
    submission holding a spreadsheet or a prior declaration beside a PDF invoice is
    ordinary, and each of those goes to its own reader. Handing one to
    `rasterize_document` directly is still a caller's mistake and still raises.
    """
    pages: list[RenderedPage] = []
    for document in documents:
        if not is_page_bearing(document.file_format):
            continue
        pages.extend(rasterize_document(document))
    return tuple(pages)


def rasterize_document(document: RoutedDocument) -> tuple[RenderedPage, ...]:
    """Render one document's pages, in page order."""
    if document.file_format is FileFormat.PDF:
        return _rasterize_pdf(document)
    if document.file_format in (FileFormat.PNG, FileFormat.JPEG):
        raise NotImplementedError(
            f"{document.file_name}: rendering a bare image upload as a page is not "
            "built. The submission gate accepts .png, .jpg and .jpeg and nothing "
            "downstream can consume one; closing this needs either an image page path "
            "or a narrower accepted-extension set."
        )
    raise ValueError(
        f"{document.file_name}: format {document.file_format} carries no pages and must "
        "never reach the rasterizer"
    )


def _rasterize_pdf(document: RoutedDocument) -> tuple[RenderedPage, ...]:
    try:
        pdf = pdfium.PdfDocument(document.content)
    except pdfium.PdfiumError as exc:
        raise _unreadable(document, f"the PDF could not be opened: {exc}") from exc

    try:
        return _render_every_page(pdf, document)
    finally:
        pdf.close()


def _render_every_page(
    pdf: pdfium.PdfDocument, document: RoutedDocument
) -> tuple[RenderedPage, ...]:
    if len(pdf) == 0:
        raise _unreadable(document, "the PDF carries no pages")
    try:
        return tuple(
            _render_page(pdf[index], document, index + 1) for index in range(len(pdf))
        )
    except pdfium.PdfiumError as exc:
        raise _unreadable(document, f"a page could not be rendered: {exc}") from exc


def _render_page(
    page: pdfium.PdfPage, document: RoutedDocument, page_number: int
) -> RenderedPage:
    # Annotations are drawn: a customs or carrier stamp is routinely an annotation, and
    # what the reader sees has to be what a human sees on the same page.
    bitmap = page.render(scale=RENDER_DPI / _POINTS_PER_INCH, draw_annots=True)
    image = bitmap.to_pil()
    width, height = image.size
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    bitmap.close()

    text_page = page.get_textpage()
    try:
        embedded_text = _position_sorted_text(text_page)
    finally:
        text_page.close()

    return RenderedPage(
        source_document_id=document.document_id,
        source_page_number=page_number,
        role_hint=document.role,
        media_type=PAGE_MEDIA_TYPE,
        image=encoded.getvalue(),
        width_px=width,
        height_px=height,
        dpi=RENDER_DPI,
        embedded_text=embedded_text,
    )


@dataclass(frozen=True)
class _PlacedCharacter:
    """One character with the box it occupies, in PDF canvas units."""

    character: str
    left: float
    right: float
    bottom: float
    top: float

    @property
    def height(self) -> float:
        return self.top - self.bottom


def _position_sorted_text(text_page: pdfium.PdfTextPage) -> str:
    """The page's embedded text, ordered by where the characters sit on the page.

    Storage order is the order the producer happened to write the characters in, which
    interleaves columns and scrambles any table. Word gaps are reconstructed from the
    spacing rather than taken from the stored space characters, whose boxes are often
    degenerate.
    """
    characters = _placed_characters(text_page)
    if not characters:
        return ""
    return "\n".join(_render_line(line) for line in _group_into_lines(characters))


def _placed_characters(text_page: pdfium.PdfTextPage) -> list[_PlacedCharacter]:
    placed: list[_PlacedCharacter] = []
    for index in range(text_page.count_chars()):
        character = text_page.get_text_range(index, 1)
        if not character.strip():
            continue
        # The advance box, not the tight glyph box: consecutive letters of one word then
        # touch, so any real gap is spacing rather than the side bearing of a narrow
        # glyph. Tight boxes put a space in the middle of "1 00".
        left, bottom, right, top = text_page.get_charbox(index, loose=True)
        placed.append(
            _PlacedCharacter(
                character=character, left=left, right=right, bottom=bottom, top=top
            )
        )
    return placed


def _group_into_lines(
    characters: Sequence[_PlacedCharacter],
) -> list[list[_PlacedCharacter]]:
    """Cluster characters into visual lines, top of the page first. y grows upward."""
    lines: list[list[_PlacedCharacter]] = []
    for character in sorted(characters, key=lambda c: -c.bottom):
        if lines and abs(lines[-1][0].bottom - character.bottom) <= _LINE_TOLERANCE_PT:
            lines[-1].append(character)
        else:
            lines.append([character])
    return lines


def _render_line(line: Sequence[_PlacedCharacter]) -> str:
    ordered = sorted(line, key=lambda c: c.left)
    written = [ordered[0].character]
    previous = ordered[0]
    previous_right = ordered[0].right
    for character in ordered[1:]:
        gap = character.left - previous_right
        if gap > _WORD_GAP_RATIO * max(previous.height, 1.0):
            written.append(" ")
        written.append(character.character)
        previous = character
        previous_right = max(previous_right, character.right)
    return "".join(written)


def _unreadable(document: RoutedDocument, detail: str) -> SubmissionRejected:
    """A file that passed the name check and cannot be opened is an intake failure."""
    return SubmissionRejected(
        [
            SubmissionProblem(
                code=IntakeErrorCode.UNREADABLE_CONTENT,
                detail=detail,
                file_name=document.file_name,
            )
        ]
    )
