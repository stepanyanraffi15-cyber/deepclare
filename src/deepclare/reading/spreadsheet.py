"""The spreadsheet reading path — not built.

A workbook has no pages, so it never reaches the rasterizer, never reaches page grouping
and is never read by the vision path. It is structured data already, and reading it is a
different job with a different failure mode.

The shape that job has to take is settled and is the single most transferable extraction
lesson in the specification: asking one model to transcribe every numeric value of a
goods table reliably drops one of two adjacent similar fields — gross weight beside net
weight — whatever the prompt says, because the source column order does not match the
schema's field order. So a model labels *which column holds which field*, one label per
column and never a value, and typed cells are read by index in ordinary code.
"""

from __future__ import annotations

from deepclare.intake import RoutedDocument
from deepclare.reading.records import InvoiceReading


def read_workbook_invoice(document: RoutedDocument) -> InvoiceReading:
    """Read a spreadsheet invoice. Not implemented."""
    raise NotImplementedError(
        f"{document.file_name}: the spreadsheet reading path is not built. It needs, in "
        "order: a streaming workbook loader (a declared used range is routinely stale "
        "and materializing it costs seconds per sheet), a whole-text header read, "
        "structural language-blind location of the goods table's header row and data "
        "span, a column labeller that emits one label per column and never a value, and "
        "a deterministic typed-cell reader that takes the values by column index."
    )
