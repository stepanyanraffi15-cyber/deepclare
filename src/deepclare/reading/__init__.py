"""M6 Document Reading — logical documents in, verbatim field records out.

In: logical documents, each an ordered page set with a role.
Out: verbatim, untranslated field records — the invoice header, the invoice goods lines,
the consignment-note fields, and any code-shaped value printed on the documents — every
one of them carrying which uploaded file it came from, what that file was, which page it
was printed on, and how well it could be read.

**Must not know about:** commodity codes and the nomenclature, the filing contract, the
review vocabulary, the declarant profile, or the arithmetic that follows. Nothing in here
may reach any of them.

Three rules govern the module:

1. **It transcribes and does nothing else.** No translation, no transliteration, no unit
   conversion, no rounding, no reformatting of a date, no filling of a gap from a
   neighbouring row or a general knowledge of the product. Every value is in the source
   language, as printed. Armenian is produced downstream, never here. The one exception
   is a vehicle plate, which the domain records with spaces removed and uppercased — and
   that transform is recorded on the value, so the filed form still walks back to the
   ink.

2. **Every value carries its provenance, attached here.** Nothing downstream can
   reconstruct which page a value came from, so a value that arrives without it is a
   defect at its producer, and this module is the producer.

3. **A failure stops the run.** A provider failure or an answer that is not the requested
   shape becomes a `ReadingError` and nothing retries, re-prompts or repairs. On a legal
   document a wrong value is worse than a missing one.

Vision is the primary path, not a fallback: the rendered page image is what is read, on
every document, because raster quality and text-layer quality are uncorrelated and in the
measured corpus they invert. The spreadsheet path is a different job on a different input
and is not built — `read_workbook_invoice` says so and names what it needs.
"""

from deepclare.reading.errors import ReadingError
from deepclare.reading.records import (
    STAGE,
    ConsignmentNoteReading,
    InvoiceReading,
    ServiceCharge,
    consignment_note_from_answer,
    invoice_from_answer,
)
from deepclare.reading.schemas import ReadConsignmentNote, ReadInvoice
from deepclare.reading.spreadsheet import read_workbook_invoice
from deepclare.reading.vision import READER_TIER, DocumentReader

__all__ = [
    "READER_TIER",
    "STAGE",
    "ConsignmentNoteReading",
    "DocumentReader",
    "InvoiceReading",
    "ReadConsignmentNote",
    "ReadInvoice",
    "ReadingError",
    "ServiceCharge",
    "consignment_note_from_answer",
    "invoice_from_answer",
    "read_workbook_invoice",
]
