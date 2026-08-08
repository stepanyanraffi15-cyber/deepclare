"""A9 — finding the goods table in a sheet, by structure and never by language.

This node reads no word of any language, and that is the design rather than an economy.
The workbook channel is the only input route in this system that carries Armenian goods
text, and a locator keyed on header words would have to be taught every language an
invoice can arrive in before it could find a single row.

The primary signal is the invoice's own row numbering: a run of two or more consecutive
buffered rows whose first cell counts 1, 2, 3… That run is the data span, and the row
directly above it is the header. Two things fall out of the shape for free — a free-form
preamble is skipped, because no preamble row begins the count, and a totals row is
excluded, because it does not continue it.

The fallback, when nothing counts, is the most header-like row: a row scores by how many
of its cells are strings of stripped length in (0, 40), and must have at least three such
cells to score at all. Everything below the winner is data. That is a weaker read and it
says so — a totals row inside a fallback span is not excluded by anything here, and the
typed reader will file it as a goods line if it carries a description.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from deepclare.reading.workbook import Sheet, SheetRow, parse_number

MINIMUM_NUMBERED_RUN = 2
"""How many consecutive counted rows make a numbering. One row reading `1` is a clause
number, a quantity, or a coincidence."""

MINIMUM_HEADER_CELLS = 3
"""How many short strings a row needs before it is header-like at all. Below this, the
best-scoring row of a sheet full of prose would be an arbitrary sentence."""

LocationMethod = Literal["numbered_run", "header_score"]


class TableLocation(BaseModel):
    """Where one sheet's goods table sits, in indexes into that sheet's buffered rows."""

    model_config = ConfigDict(frozen=True)

    header_index: int | None = Field(default=None, ge=0)
    """None when the numbered run starts at the first buffered row and there is no row
    above it to read as a header. The labeller then judges on values alone."""

    first_data_index: int = Field(ge=0)
    last_data_index: int = Field(ge=0)
    column_count: int = Field(ge=1)
    """The widest the table gets across its header and every one of its data rows. A
    column that is blank in the first rows still has to be offered to the labeller."""

    located_by: LocationMethod

    @property
    def data_row_count(self) -> int:
        return self.last_data_index - self.first_data_index + 1


def locate_goods_table(sheet: Sheet) -> TableLocation | None:
    """Find the header row and the data span, or return None.

    None is an ordinary answer, not a failure: a cover sheet, a terms-and-conditions tab
    or a summary sheet contributes no goods lines and stops the run for nobody.
    """
    return _numbered_run(sheet) or _best_header_row(sheet)


def header_row(sheet: Sheet, location: TableLocation) -> SheetRow | None:
    """The located header row, or None when the table starts at the top of the sheet."""
    if location.header_index is None:
        return None
    return sheet.rows[location.header_index]


def data_rows(sheet: Sheet, location: TableLocation) -> tuple[SheetRow, ...]:
    """The located data span, in printed order."""
    return sheet.rows[location.first_data_index : location.last_data_index + 1]


def _numbered_run(sheet: Sheet) -> TableLocation | None:
    """The first run of rows whose first cell counts 1, 2, 3…"""
    for start in range(len(sheet.rows)):
        if _counter(sheet.rows[start]) != 1:
            continue
        end = start
        while (
            end + 1 < len(sheet.rows)
            and _counter(sheet.rows[end + 1]) == _counter(sheet.rows[end]) + 1
        ):
            end += 1
        if end - start + 1 < MINIMUM_NUMBERED_RUN:
            continue
        return _location(
            sheet,
            header_index=start - 1 if start > 0 else None,
            first_data_index=start,
            last_data_index=end,
            located_by="numbered_run",
        )
    return None


def _best_header_row(sheet: Sheet) -> TableLocation | None:
    """The highest-scoring header-like row with at least one row of data under it.

    Ties go to the earliest row: a header sits above its data, so when two rows look
    equally like headers the upper one is the one that can be.
    """
    best_index: int | None = None
    best_score = 0
    for index, row in enumerate(sheet.rows[:-1]):
        score = sum(1 for cell in row.cells if cell.is_short_text)
        if score >= MINIMUM_HEADER_CELLS and score > best_score:
            best_index, best_score = index, score
    if best_index is None:
        return None
    return _location(
        sheet,
        header_index=best_index,
        first_data_index=best_index + 1,
        last_data_index=len(sheet.rows) - 1,
        located_by="header_score",
    )


def _location(
    sheet: Sheet,
    *,
    header_index: int | None,
    first_data_index: int,
    last_data_index: int,
    located_by: LocationMethod,
) -> TableLocation:
    spanned = sheet.rows[first_data_index : last_data_index + 1]
    if header_index is not None:
        spanned = (sheet.rows[header_index], *spanned)
    return TableLocation(
        header_index=header_index,
        first_data_index=first_data_index,
        last_data_index=last_data_index,
        column_count=max(len(row.cells) for row in spanned),
        located_by=located_by,
    )


def _counter(row: SheetRow) -> int | None:
    """The row's own printed number, when its first cell holds a positive whole one.

    A row number typed as text counts too. Whether the workbook stored `1` as a number or
    as a string is a property of how the file was authored and says nothing about whether
    the invoice numbers its rows.
    """
    cell = row.first_cell
    number = cell.number if cell.number is not None else parse_number(cell.text)
    if number is None or number != number.to_integral_value():
        return None
    counted = int(number)
    return counted if counted >= 1 else None
