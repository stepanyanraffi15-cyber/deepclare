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
measured corpus they invert.

The spreadsheet path is a different job on a different input, and it is the only route
into this system that carries Armenian goods text. It reads a workbook in one streaming
pass and then splits the work three ways: structure locates the goods table without
reading a word of any language, a model labels which column holds which field, and
deterministic code reads the typed cells by index. `read_workbook_invoice` returns the
invoice in the same shape the vision path does, alongside the account of what the
structural path decided — including the cells it could not read, which the specification
records as a silent failure to fix.

One thing here runs *before* a logical document exists: the page-type classifier, which
sorts rendered pages so that intake can group them. It sits in this module because intake
must not know which model reads a page and this is the module that owns vision calls over
page images — the dependency runs M6 → M5, which is the direction the boundaries allow.
It is otherwise an ordinary member: same client, same prompt loader, same one error, and
it knows no more about a declaration than the readers do.
"""

from deepclare.reading.columns import (
    LABELLER_TIER,
    ColumnBinding,
    DuplicateLabel,
    SheetLabelling,
    label_columns,
)
from deepclare.reading.errors import ReadingError
from deepclare.reading.page_types import (
    CLASSIFIER_TIER,
    VisionPageTypeClassifier,
    page_manifest,
    verdicts_from_answer,
)
from deepclare.reading.records import (
    STAGE,
    ConsignmentNoteReading,
    InvoiceReading,
    ServiceCharge,
    consignment_note_from_answer,
    invoice_from_answer,
)
from deepclare.reading.schemas import (
    ClassifyPageType,
    ColumnLabel,
    LabelColumns,
    ReadConsignmentNote,
    ReadInvoice,
    ReadWorkbookInvoice,
)
from deepclare.reading.spreadsheet import (
    WORKBOOK_READER_TIER,
    SheetOutcome,
    UnreadNumbers,
    WorkbookReading,
    read_workbook_invoice,
)
from deepclare.reading.table import TableLocation, locate_goods_table
from deepclare.reading.vision import READER_TIER, DocumentReader
from deepclare.reading.workbook import (
    Cell,
    Sheet,
    SheetRow,
    WorkbookBuffer,
    buffer_workbook,
    render_workbook_text,
)

__all__ = [
    "CLASSIFIER_TIER",
    "LABELLER_TIER",
    "READER_TIER",
    "STAGE",
    "WORKBOOK_READER_TIER",
    "Cell",
    "ClassifyPageType",
    "ColumnBinding",
    "ColumnLabel",
    "ConsignmentNoteReading",
    "DocumentReader",
    "DuplicateLabel",
    "InvoiceReading",
    "LabelColumns",
    "ReadConsignmentNote",
    "ReadInvoice",
    "ReadWorkbookInvoice",
    "ReadingError",
    "ServiceCharge",
    "Sheet",
    "SheetLabelling",
    "SheetOutcome",
    "SheetRow",
    "TableLocation",
    "UnreadNumbers",
    "VisionPageTypeClassifier",
    "WorkbookBuffer",
    "WorkbookReading",
    "buffer_workbook",
    "consignment_note_from_answer",
    "invoice_from_answer",
    "label_columns",
    "locate_goods_table",
    "page_manifest",
    "read_workbook_invoice",
    "render_workbook_text",
    "verdicts_from_answer",
]
