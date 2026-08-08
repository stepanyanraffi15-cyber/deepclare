"""The vision document reader: a page group in, a validated record out.

One call per logical document. Every page of the group is sent in that one call, with the
images ahead of the instruction, and the answer is bound to a typed schema — nothing here
parses free text and nothing here re-prompts.

Vision is the primary reading path, not a fallback and not an escalation. The measured
corpus inverts the intuitive rule: the sharpest scan in it carried the worst embedded
text layer, and text-layer presence, text-layer length and raster resolution are all
uncorrelated with what can be read off a page. So the rendered image is what is read, on
every document, and the embedded text a page may carry is never consulted here.

Two properties of the call are known hazards and are left visible rather than papered
over. There is no page cap, no batching and no image-size limit, so a long bundle is a
real scaling risk — a filed declaration in the recorded corpus carried 554 goods lines.
And there is no retry: the first provider or parse failure ends the stage. A second
attempt at a legal document is a machine talking itself into an answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from deepclare.domain import DocumentRole
from deepclare.intake import LogicalDocument
from deepclare.models import (
    GenerativeModel,
    ModelError,
    ModelResult,
    ModelTier,
    PageImage,
)
from deepclare.prompting import render_prompt
from deepclare.reading.errors import ReadingError
from deepclare.reading.records import (
    ConsignmentNoteReading,
    InvoiceReading,
    consignment_note_from_answer,
    invoice_from_answer,
)
from deepclare.reading.schemas import ReadConsignmentNote, ReadInvoice

READER_TIER = ModelTier.STANDARD
"""Reading a page is a transcription job, but a dense goods table is a hard one, and a
dropped or transposed row is not recoverable downstream. The tier is named here rather
than chosen per call: one document, one reading standard."""


class DocumentReader:
    """Reads logical documents with a vision model.

    Construct one per run and hand it the same model client the rest of the run uses; it
    holds no state between calls.
    """

    def __init__(self, model: GenerativeModel, prompts_dir: Path) -> None:
        self._model = model
        self._prompts_dir = prompts_dir

    def read_invoice(self, document: LogicalDocument) -> InvoiceReading:
        """Read the invoice page group into an invoice record."""
        _require_role(document, DocumentRole.INVOICE)
        result = self._read(document, "read_invoice", ReadInvoice)
        return invoice_from_answer(result.value, document, result.call)

    def read_consignment_note(
        self, document: LogicalDocument
    ) -> ConsignmentNoteReading:
        """Read the consignment-note page group into a consignment-note record."""
        _require_role(document, DocumentRole.CONSIGNMENT_NOTE)
        result = self._read(document, "read_consignment_note", ReadConsignmentNote)
        return consignment_note_from_answer(result.value, document, result.call)

    def _read[T: (ReadInvoice, ReadConsignmentNote)](
        self, document: LogicalDocument, prompt_name: str, output: type[T]
    ) -> ModelResult[T]:
        prompt = render_prompt(
            self._prompts_dir, prompt_name, {"page_count": str(len(document.pages))}
        )
        try:
            return self._model.generate_from_pages(
                tier=READER_TIER,
                prompt=prompt,
                pages=_page_images(document),
                output=output,
            )
        except ModelError as exc:
            raise ReadingError(
                f"reading the {len(document.pages)}-page {document.role} document "
                f"failed: {exc}"
            ) from exc


def _page_images(document: LogicalDocument) -> Sequence[PageImage]:
    """The group's pages, in order. The i-th image is the document's logical page i+1."""
    return [
        PageImage(media_type=page.rendered.media_type, content=page.rendered.image)
        for page in document.pages
    ]


def _require_role(document: LogicalDocument, expected: DocumentRole) -> None:
    """Each record shape has its own prompt, so the wrong group is a caller's mistake.

    A document's type is never asked of the model — it is a constant of the record the
    caller chose — which means nothing downstream would notice a consignment note read
    against the invoice prompt except by the nonsense it produced.
    """
    if document.role is not expected:
        raise ValueError(
            f"this read takes {expected} pages and was handed a {document.role} document"
        )
