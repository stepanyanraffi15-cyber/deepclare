"""The spreadsheet reading path — A8 and A11, and the chain A7 → A11 as a whole.

A workbook has no pages. It never reaches the rasterizer, never reaches page grouping and
is never read by vision, because rasterizing a spreadsheet throws away exactly the
structure that makes it reliable. It is structured data already, and reading it is a
different job with a different failure mode.

Two reads happen, and only one of them is a transcription:

* **A8, the whole-text read**, fills the header — invoice number, date, currency, terms,
  parties, total, and the service rows that are not goods. It runs on every workbook,
  including the ones where the structural path succeeds, because header fields are
  free-form prose scattered around a sheet with no recorded transcription fragility. Its
  goods list is a first guess and is normally thrown away.
* **A9 → A10 → A11, the structural path**, produces the goods lines that are actually
  filed. Structure finds the table, a model labels which column is which, and this module
  reads the typed cells by index. The division is the fix for a reproduced bug that no
  prompt could reach: one model transcribing a whole table reliably dropped one of two
  adjacent similar fields when the column order did not match the schema's field order.

Degradation is specified, not improvised. A sheet with no detectable table contributes no
goods lines and is not an error. A failed labelling call costs the whole structural path
and the run falls back to A8's guess. A row with no description is skipped rather than
filed as a garbage line. And the one path the specification names as a silent failure to
fix — a cell that will not parse as a number quietly becoming empty — is counted, logged
and returned here, per column, because per column is how it fails.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from deepclare.domain import (
    Confidence,
    DocumentRole,
    InvoiceGoodsLine,
    InvoiceRecord,
    Party,
    Provenance,
    Traced,
    ValueOrigin,
)
from deepclare.intake import RoutedDocument
from deepclare.intake.formats import FileFormat
from deepclare.models import GenerativeModel, ModelCall, ModelError, ModelTier
from deepclare.prompting import render_prompt
from deepclare.reading.columns import (
    ColumnBinding,
    SheetLabelling,
    label_columns,
)
from deepclare.reading.errors import ReadingError
from deepclare.reading.records import (
    STAGE,
    InvoiceReading,
    ServiceCharge,
    build_record,
)
from deepclare.reading.schemas import (
    ColumnLabel,
    ReadWorkbookInvoice,
    WorkbookGoodsLine,
    WorkbookNumber,
    WorkbookParty,
    WorkbookServiceCharge,
    WorkbookText,
)
from deepclare.reading.table import TableLocation, data_rows, locate_goods_table
from deepclare.reading.workbook import (
    Sheet,
    SheetRow,
    WorkbookBuffer,
    buffer_workbook,
    parse_number,
    render_workbook_text,
)

logger = logging.getLogger(__name__)

PROMPT_NAME = "read_workbook_invoice"

WORKBOOK_READER_TIER = ModelTier.CHEAP
"""The whole-text read copies prose out of an exact text rendering. Nothing is being
deciphered, and the goods table — the part that would need care — is read by the
structural path instead."""

TYPED_CELL_EXTRACTION_CONFIDENCE = 1.0
"""What a value read straight out of a typed cell claims. Extraction confidence asks
whether the value was read correctly off the source, and here the value *is* the cell,
copied by index with nothing in between. The separate risk — that the column was bound to
the wrong field — belongs to A10 and is reported by this module's own notes rather than
smuggled into a number that means something else."""

MAX_UNREAD_EXAMPLES = 3
"""How many distinct unreadable cell texts a column reports. Enough to recognise what the
column really holds; a full list would be the column."""

GoodsSource = Literal["typed_cells", "whole_text_guess"]


class UnreadNumbers(BaseModel):
    """Cells bound to a numeric field whose text would not read as a number.

    The specification records this exact path as a silent failure to fix: unparseable cell
    text became an empty field with no error, no warning and no log, so a text column bound
    to a numeric field lost every one of its values without trace. Reported per column
    because that is the shape of the failure — one bad binding empties a whole column, and
    a count beside the field name says so at a glance.
    """

    model_config = ConfigDict(frozen=True)

    sheet_name: str
    column: int = Field(ge=0)
    field_name: ColumnLabel
    rows: tuple[int, ...] = Field(min_length=1)
    """1-based sheet rows, so a reviewer can open the file and look at the cell."""

    examples: tuple[str, ...] = Field(min_length=1)


class SheetOutcome(BaseModel):
    """What one sheet contributed, and what was decided about it on the way."""

    model_config = ConfigDict(frozen=True)

    sheet_name: str
    buffered_rows: int = Field(ge=1)
    table: TableLocation | None = None
    """None when nothing in the sheet reads as a goods table. Ordinary, not a failure."""

    labelling: SheetLabelling | None = None
    goods_rows: int = Field(default=0, ge=0)
    rows_without_description: tuple[int, ...] = ()
    """1-based sheet rows inside the data span that carried no description and were
    skipped. A row with no description is not a goods line with a blank name."""

    service_rows: tuple[int, ...] = ()
    """1-based sheet rows the whole-text read named as service charges rather than goods.
    They are inside the table's own numbering and the typed reader cannot tell them apart
    from goods — a freight row is a row like any other to a structural pass — so they are
    excluded on A8's word, and listed here because that is a judgement and not a
    measurement."""


class WorkbookReading(BaseModel):
    """One workbook invoice, read, with the account of everything the reading decided.

    `reading` is the same shape the vision path returns, so nothing downstream has to know
    which route the invoice came in by. Everything beside it is what only this route can
    say, and what the specification asks to stop being silent.
    """

    model_config = ConfigDict(frozen=True)

    reading: InvoiceReading
    goods_source: GoodsSource
    sheets: tuple[SheetOutcome, ...] = Field(min_length=1)
    unread_numbers: tuple[UnreadNumbers, ...] = ()
    labelling_failure: str | None = None
    """Why the structural path was abandoned, when it was. The goods on the record are
    then A8's guess, which is a weaker read of the same table."""

    @property
    def model_calls(self) -> tuple[ModelCall, ...]:
        """Every call the read made: the whole-text read, then one per labelled sheet."""
        return (
            self.reading.call,
            *(
                sheet.labelling.call
                for sheet in self.sheets
                if sheet.labelling is not None
            ),
        )


def read_workbook_invoice(
    document: RoutedDocument, model: GenerativeModel, prompts_dir: Path
) -> WorkbookReading:
    """Read a spreadsheet invoice: A7 buffers it, A8 reads the header, A9–A11 the goods."""
    _require_workbook_invoice(document)
    buffer = buffer_workbook(document)

    answer, call = _read_whole_text(model, prompts_dir, buffer)
    outcomes, typed_lines, unread, failure = _read_goods_by_column(
        model, prompts_dir, document, buffer, _service_row_texts(answer)
    )

    if typed_lines:
        goods_source: GoodsSource = "typed_cells"
        goods_lines = typed_lines
    else:
        goods_source = "whole_text_guess"
        goods_lines = _guessed_lines(answer, document, call)
        if failure is None and any(sheet.table is not None for sheet in outcomes):
            logger.warning(
                "%s: the typed cell reader produced no goods lines from %d located "
                "table(s); the whole-text guess stands instead",
                document.file_name,
                sum(1 for sheet in outcomes if sheet.table is not None),
            )

    if not goods_lines:
        raise ReadingError(
            f"{document.file_name}: neither the goods table nor the whole-text read "
            f"yielded a goods line from {len(buffer.sheets)} sheet(s). There is nothing "
            "to declare, and a declaration with no goods is not a lesser draft but a "
            "different document."
        )

    invoice = build_record(
        InvoiceRecord,
        source_document_id=document.document_id,
        # A workbook is not paginated, so there are no page classifications to carry.
        pages=(),
        goods_lines=goods_lines,
        invoice_number=_text(answer.invoice_number, document, call),
        invoice_date=_text(answer.invoice_date, document, call),
        currency=_text(answer.currency, document, call),
        incoterms_code=_text(answer.incoterms_code, document, call),
        incoterms_place=_text(answer.incoterms_place, document, call),
        origin_country=_text(answer.origin_country, document, call),
        seller=_party(answer.seller, document, call),
        buyer=_party(answer.buyer, document, call),
        total_amount=_number(answer.total_amount, document, call),
    )
    return WorkbookReading(
        reading=InvoiceReading(
            invoice=invoice,
            service_charges=_service_charges(answer.service_charges, document, call),
            call=call,
        ),
        goods_source=goods_source,
        sheets=outcomes,
        unread_numbers=unread,
        labelling_failure=failure,
    )


# --- A8: the whole-text read ----------------------------------------------------------


def _read_whole_text(
    model: GenerativeModel, prompts_dir: Path, buffer: WorkbookBuffer
) -> tuple[ReadWorkbookInvoice, ModelCall]:
    """Fill the header fields from a tab-separated rendering of the whole workbook."""
    prompt = render_prompt(
        prompts_dir,
        PROMPT_NAME,
        {
            "sheet_count": str(len(buffer.sheets)),
            "workbook_text": render_workbook_text(buffer),
        },
    )
    try:
        result = model.generate(
            tier=WORKBOOK_READER_TIER, prompt=prompt, output=ReadWorkbookInvoice
        )
    except ModelError as exc:
        raise ReadingError(
            f"reading the {len(buffer.sheets)}-sheet workbook invoice failed: {exc}"
        ) from exc
    return result.value, result.call


# --- A9 → A10 → A11: the structural path ----------------------------------------------


def _read_goods_by_column(
    model: GenerativeModel,
    prompts_dir: Path,
    document: RoutedDocument,
    buffer: WorkbookBuffer,
    service_rows: frozenset[str],
) -> tuple[tuple[SheetOutcome, ...], tuple[InvoiceGoodsLine, ...], tuple[UnreadNumbers, ...], str | None]:
    """Locate, label and read every sheet that has a goods table in it.

    A labelling failure abandons the structural path for the whole workbook rather than
    for the one sheet: a run whose lines came half from typed cells and half from a
    whole-text guess would be two readings of one invoice joined by position.
    """
    outcomes: list[SheetOutcome] = []
    lines: list[InvoiceGoodsLine] = []
    unread: list[UnreadNumbers] = []

    for sheet in buffer.sheets:
        location = locate_goods_table(sheet)
        if location is None:
            logger.info(
                "%s: sheet %r has no detectable goods table; it contributes no lines",
                document.file_name,
                sheet.name,
            )
            outcomes.append(
                SheetOutcome(sheet_name=sheet.name, buffered_rows=len(sheet.rows))
            )
            continue

        try:
            labelling = label_columns(model, prompts_dir, sheet, location)
        except ModelError as exc:
            failure = f"labelling the columns of sheet {sheet.name!r} failed: {exc}"
            logger.warning(
                "%s: %s. The whole spreadsheet goods path falls back to the whole-text "
                "read.",
                document.file_name,
                failure,
            )
            return _unlabelled_outcomes(buffer), (), (), failure

        harvest = _read_typed_cells(
            sheet, location, labelling, document, len(lines) + 1, service_rows
        )
        lines.extend(harvest.lines)
        unread.extend(harvest.unread)
        outcomes.append(
            SheetOutcome(
                sheet_name=sheet.name,
                buffered_rows=len(sheet.rows),
                table=location,
                labelling=labelling,
                goods_rows=len(harvest.lines),
                rows_without_description=harvest.rows_without_description,
                service_rows=harvest.service_rows,
            )
        )
        if harvest.service_rows:
            logger.info(
                "%s: sheet %r row(s) %s sit inside the goods table and were read as "
                "service charges rather than goods",
                document.file_name,
                sheet.name,
                ", ".join(str(row) for row in harvest.service_rows),
            )

    for column in unread:
        logger.warning(
            "%s: sheet %r column %d is bound to %s and %d of its cells do not read as "
            "numbers (e.g. %s); those values are empty on the record",
            document.file_name,
            column.sheet_name,
            column.column,
            column.field_name,
            len(column.rows),
            ", ".join(repr(example) for example in column.examples),
        )

    return tuple(outcomes), tuple(lines), tuple(unread), None


@dataclass
class _Harvest:
    """What reading one sheet's typed cells produced, and what it could not use."""

    lines: list[InvoiceGoodsLine] = field(default_factory=list)
    unread: list[UnreadNumbers] = field(default_factory=list)
    rows_without_description: tuple[int, ...] = ()
    service_rows: tuple[int, ...] = ()


def _read_typed_cells(
    sheet: Sheet,
    location: TableLocation,
    labelling: SheetLabelling,
    document: RoutedDocument,
    first_line_id: int,
    service_rows: frozenset[str],
) -> _Harvest:
    """A11. Read the cells of the data span by column index, in printed order."""
    description_column = labelling.column_of("description")
    if description_column is None:
        logger.warning(
            "%s: sheet %r has a goods table but no column was labelled a description; "
            "it yields nothing",
            document.file_name,
            sheet.name,
        )
        return _Harvest()

    provenance = _provenance(document, labelling.call)
    confidence = Confidence(extraction=TYPED_CELL_EXTRACTION_CONFIDENCE)
    losses: dict[int, _ColumnLoss] = {}
    harvest = _Harvest()
    skipped: list[int] = []
    services: list[int] = []

    for row in data_rows(sheet, location):
        description = row.at(description_column)
        if description is None or description.is_blank:
            skipped.append(row.number)
            continue
        if _match_key(description.text) in service_rows:
            services.append(row.number)
            continue
        harvest.lines.append(
            _typed_line(
                row=row,
                bindings=labelling.bindings,
                line_id=str(first_line_id + len(harvest.lines)),
                description=description.text,
                provenance=provenance,
                confidence=confidence,
                losses=losses,
            )
        )

    harvest.rows_without_description = tuple(skipped)
    harvest.service_rows = tuple(services)
    harvest.unread = [
        UnreadNumbers(
            sheet_name=sheet.name,
            column=column,
            field_name=loss.field_name,
            rows=tuple(loss.rows),
            examples=tuple(loss.examples[:MAX_UNREAD_EXAMPLES]),
        )
        for column, loss in sorted(losses.items())
    ]
    return harvest


@dataclass
class _ColumnLoss:
    """Cells of one column that would not read as numbers."""

    field_name: ColumnLabel
    rows: list[int] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)

    def record(self, row: int, text: str) -> None:
        self.rows.append(row)
        if text not in self.examples:
            self.examples.append(text)


def _typed_line(
    *,
    row: SheetRow,
    bindings: tuple[ColumnBinding, ...],
    line_id: str,
    description: str,
    provenance: Provenance,
    confidence: Confidence,
    losses: dict[int, _ColumnLoss],
) -> InvoiceGoodsLine:
    """One goods row, field by bound column. Nothing is read from an unbound column."""
    fields: dict[str, object] = {}
    for binding in bindings:
        cell = row.at(binding.column)
        if cell is None or cell.is_blank or binding.field == "description":
            continue
        if binding.field in _TEXT_FIELDS:
            fields[binding.field] = Traced[str](
                value=cell.text, provenance=provenance, confidence=confidence
            )
            continue

        number = cell.number if cell.number is not None else parse_number(cell.text)
        if number is None:
            losses.setdefault(
                binding.column, _ColumnLoss(field_name=binding.field)
            ).record(row.number, cell.text)
            continue
        if binding.field == "printed_line_number":
            if number == number.to_integral_value():
                fields[binding.field] = Traced[int](
                    value=int(number), provenance=provenance, confidence=confidence
                )
            else:
                losses.setdefault(
                    binding.column, _ColumnLoss(field_name=binding.field)
                ).record(row.number, cell.text)
            continue
        fields[binding.field] = Traced[Decimal](
            value=number, provenance=provenance, confidence=confidence
        )

    return build_record(
        InvoiceGoodsLine,
        line_id=line_id,
        description=Traced[str](
            value=description, provenance=provenance, confidence=confidence
        ),
        **fields,
    )


def _service_row_texts(answer: ReadWorkbookInvoice) -> frozenset[str]:
    """The descriptions the whole-text read named as service rows rather than goods.

    The typed reader cannot make this distinction and must not try: a freight row inside
    the goods table is numbered like a goods row, priced like one and shaped like one, and
    a structural pass reading cells by index sees no difference. The whole-text read does
    make the distinction, and its service rows are kept on the record whatever happens to
    its goods, so this is the one judgement of A8's that the typed path defers to. Without
    it the same row is filed twice — once as goods and once as the charge that was meant
    to explain the gap between the invoice's total and the declared goods value.

    Matching is on the description text, whitespace-collapsed and case-folded, and nothing
    else. A row A8 paraphrased rather than copied does not match and stays as goods, which
    is the direction that loses no goods.
    """
    return frozenset(
        _match_key(charge.description)
        for charge in answer.service_charges
        if charge.description.strip()
    )


def _match_key(text: str) -> str:
    return " ".join(text.split()).casefold()


def _unlabelled_outcomes(buffer: WorkbookBuffer) -> tuple[SheetOutcome, ...]:
    """What each sheet is once the structural path has been abandoned: located or not."""
    return tuple(
        SheetOutcome(
            sheet_name=sheet.name,
            buffered_rows=len(sheet.rows),
            table=locate_goods_table(sheet),
        )
        for sheet in buffer.sheets
    )


# --- A8's goods, kept only when the structural path produced none ----------------------


def _guessed_lines(
    answer: ReadWorkbookInvoice, document: RoutedDocument, call: ModelCall
) -> tuple[InvoiceGoodsLine, ...]:
    provenance = _provenance(document, call)
    return tuple(
        _guessed_line(line, str(position), provenance)
        for position, line in enumerate(answer.goods_lines, start=1)
    )


def _guessed_line(
    line: WorkbookGoodsLine, line_id: str, provenance: Provenance
) -> InvoiceGoodsLine:
    confidence = Confidence(extraction=line.confidence)

    def traced_text(value: str | None) -> Traced[str] | None:
        if value is None or not value.strip():
            return None
        return Traced[str](value=value, provenance=provenance, confidence=confidence)

    def traced_number(value: Decimal | None) -> Traced[Decimal] | None:
        if value is None:
            return None
        return Traced[Decimal](
            value=value, provenance=provenance, confidence=confidence
        )

    return build_record(
        InvoiceGoodsLine,
        line_id=line_id,
        description=Traced[str](
            value=line.description, provenance=provenance, confidence=confidence
        ),
        printed_line_number=(
            None
            if line.printed_line_number is None
            else Traced[int](
                value=line.printed_line_number,
                provenance=provenance,
                confidence=confidence,
            )
        ),
        quantity=traced_number(line.quantity),
        unit=traced_text(line.unit),
        gross_weight=traced_number(line.gross_weight),
        net_weight=traced_number(line.net_weight),
        weight_unit=traced_text(line.weight_unit),
        unit_price=traced_number(line.unit_price),
        total_price=traced_number(line.total_price),
        package_count=traced_number(line.package_count),
        package_type=traced_text(line.package_type),
        origin_country=traced_text(line.origin_country),
        trade_name=traced_text(line.trade_name),
        units_per_package=traced_number(line.units_per_package),
        package_weight_kg=traced_number(line.package_weight_kg),
        dimensions=traced_text(line.dimensions),
        printed_customs_code=traced_text(line.printed_customs_code),
    )


# --- header values --------------------------------------------------------------------


def _text(
    value: WorkbookText | None, document: RoutedDocument, call: ModelCall
) -> Traced[str] | None:
    if value is None or not value.text.strip():
        return None
    return Traced[str](
        value=value.text,
        provenance=_provenance(document, call),
        confidence=Confidence(extraction=value.confidence),
    )


def _number(
    value: WorkbookNumber | None, document: RoutedDocument, call: ModelCall
) -> Traced[Decimal] | None:
    if value is None:
        return None
    return Traced[Decimal](
        value=value.number,
        provenance=_provenance(document, call),
        confidence=Confidence(extraction=value.confidence),
    )


def _party(
    value: WorkbookParty | None, document: RoutedDocument, call: ModelCall
) -> Party | None:
    if value is None:
        return None
    provenance = _provenance(document, call)
    confidence = Confidence(extraction=value.confidence)

    def line(text: str | None) -> Traced[str] | None:
        if text is None or not text.strip():
            return None
        return Traced[str](value=text, provenance=provenance, confidence=confidence)

    return Party(
        name=line(value.name), address=line(value.address), tax_code=line(value.tax_code)
    )


def _service_charges(
    charges: list[WorkbookServiceCharge], document: RoutedDocument, call: ModelCall
) -> tuple[ServiceCharge, ...]:
    provenance = _provenance(document, call)
    built: list[ServiceCharge] = []
    for position, charge in enumerate(charges, start=1):
        if not charge.description.strip():
            raise ReadingError(
                f"service charge {position} was returned with no description; a charge "
                "nobody can name cannot be reconciled against the invoice total."
            )
        confidence = Confidence(extraction=charge.confidence)
        built.append(
            ServiceCharge(
                description=Traced[str](
                    value=charge.description,
                    provenance=provenance,
                    confidence=confidence,
                ),
                amount=None
                if charge.amount is None
                else Traced[Decimal](
                    value=charge.amount, provenance=provenance, confidence=confidence
                ),
            )
        )
    return tuple(built)


def _provenance(document: RoutedDocument, call: ModelCall) -> Provenance:
    """Where a workbook value came from.

    No region: a document region counts pages and a workbook has none. That is a real
    loss — a workbook value cannot say which sheet and cell it was read from, where a
    scanned value can say which page — and it is why the cells this module could *not*
    read carry their sheet and row explicitly.
    """
    return Provenance(
        origin=ValueOrigin.EXTRACTED,
        source_document_id=document.document_id,
        source_document_role=document.role.value,
        stage=STAGE,
        prompt_name=call.prompt_name,
        prompt_version=call.prompt_version,
    )


def _require_workbook_invoice(document: RoutedDocument) -> None:
    """This path reads one thing, and being handed anything else is a caller's mistake."""
    if document.role is not DocumentRole.INVOICE:
        raise ValueError(
            f"the workbook path reads the invoice and was handed a {document.role} "
            "document"
        )
    if document.file_format is not FileFormat.WORKBOOK:
        raise ValueError(
            f"the workbook path reads a workbook and was handed a "
            f"{document.file_format} document"
        )


_TEXT_FIELDS: frozenset[str] = frozenset(
    {
        "description",
        "unit",
        "weight_unit",
        "package_type",
        "origin_country",
        "trade_name",
        "dimensions",
        "printed_customs_code",
    }
)
"""Which labels name a field the goods line holds as text. Everything else the labeller
can return is a number, and `printed_line_number` is the one that must be a whole one."""
