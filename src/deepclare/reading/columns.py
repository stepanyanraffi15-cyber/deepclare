"""A10 — labelling the columns of one located goods table.

The model is asked which column holds which field. It is never asked what is *in* a
column, and it is never shown the table it would need in order to answer that. This is
the single most transferable extraction lesson in the system, and it is structural rather
than a matter of wording: asking one call to transcribe every numeric value across a
goods table reliably dropped one of two adjacent similar fields — gross weight beside net
weight — regardless of how the prompt was written, because the source column order did
not match the schema's field order. Demoting the model to one label per column bounds the
answer space by the table's own width, and deterministic code then reads the typed cells
by index. A figure cannot be lost by a binding that never touches it.

The payload is deliberately small: the header row and three data rows from directly under
it, never the whole table. Sample rows are there so a column with no header at all can
still be judged on what it holds.

Two failures are ordinary here and neither raises. A duplicate label is resolved by column
index — the lowest wins — and logged. A column index the table does not have is dropped
and logged. What does raise is a mistake of ours rather than the model's; a provider
failure is left for the caller, which has a whole-text answer to fall back on.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from deepclare.models import GenerativeModel, ModelCall, ModelTier
from deepclare.prompting import render_prompt
from deepclare.reading.schemas import ColumnLabel, LabelColumns
from deepclare.reading.table import TableLocation, data_rows, header_row
from deepclare.reading.workbook import Sheet, render_row

logger = logging.getLogger(__name__)

PROMPT_NAME = "label_columns"

LABELLER_TIER = ModelTier.CHEAP
"""Labelling emits one word per column out of a closed set of eighteen. No value is
transcribed and no material or legal distinction is drawn."""

SAMPLE_ROW_COUNT = 3
"""How many data rows go into the payload, taken from directly under the header. Enough
to show what a column holds; few enough that the call stays a classification."""

IGNORE = "ignore"
"""The abstention. A column with no textual or numeric support gets this rather than a
guessed field."""


class ColumnBinding(BaseModel):
    """One column index bound to one goods field. `ignore` never becomes a binding."""

    model_config = ConfigDict(frozen=True)

    column: int = Field(ge=0)
    field: ColumnLabel


class DuplicateLabel(BaseModel):
    """Two or more columns claimed the same field. The lowest index won."""

    model_config = ConfigDict(frozen=True)

    sheet_name: str
    field: ColumnLabel
    kept_column: int = Field(ge=0)
    dropped_columns: tuple[int, ...] = Field(min_length=1)


class SheetLabelling(BaseModel):
    """What the labeller decided about one sheet, and what had to be resolved."""

    model_config = ConfigDict(frozen=True)

    bindings: tuple[ColumnBinding, ...]
    duplicates: tuple[DuplicateLabel, ...] = ()
    out_of_range_columns: tuple[int, ...] = ()
    unlabelled_columns: tuple[int, ...] = ()
    """Columns the answer said nothing about. They are not repaired into `ignore`: an
    answer that skipped a column is a different fact from one that dismissed it, and both
    read the same way downstream, so inventing the verdict would only hide the first."""

    call: ModelCall

    def column_of(self, field: ColumnLabel) -> int | None:
        return next((b.column for b in self.bindings if b.field == field), None)


def label_columns(
    model: GenerativeModel, prompts_dir: Path, sheet: Sheet, location: TableLocation
) -> SheetLabelling:
    """Ask which column is which, then resolve the answer against the table's real width.

    Raises ModelError, unchanged, when the provider fails or answers the wrong shape. The
    caller decides what a failed labelling costs, because it is the only thing holding the
    whole-text guess this path falls back to.
    """
    prompt = render_prompt(
        prompts_dir,
        PROMPT_NAME,
        {
            "sheet_name": sheet.name,
            "column_count": str(location.column_count),
            "header_row": render_row(header_row(sheet, location), location.column_count),
            "sample_rows": _sample_rows(sheet, location),
        },
    )
    result = model.generate(tier=LABELLER_TIER, prompt=prompt, output=LabelColumns)
    return _resolve(result.value, sheet, location, result.call)


def _sample_rows(sheet: Sheet, location: TableLocation) -> str:
    rows = data_rows(sheet, location)[:SAMPLE_ROW_COUNT]
    return "\n".join(render_row(row, location.column_count) for row in rows)


def _resolve(
    answer: LabelColumns, sheet: Sheet, location: TableLocation, call: ModelCall
) -> SheetLabelling:
    """Turn the answer into bindings the typed reader can use, saying what it cost."""
    in_range = [
        labelled
        for labelled in answer.columns
        if 0 <= labelled.column < location.column_count
    ]
    out_of_range = tuple(
        sorted(
            {
                labelled.column
                for labelled in answer.columns
                if not 0 <= labelled.column < location.column_count
            }
        )
    )
    if out_of_range:
        logger.warning(
            "sheet %r: the column labeller answered for column(s) %s, which a "
            "%d-column table does not have; dropped",
            sheet.name,
            ", ".join(str(column) for column in out_of_range),
            location.column_count,
        )

    claimed: dict[ColumnLabel, list[int]] = {}
    for labelled in sorted(in_range, key=lambda entry: entry.column):
        if labelled.label == IGNORE:
            continue
        claimed.setdefault(labelled.label, []).append(labelled.column)

    duplicates = tuple(
        DuplicateLabel(
            sheet_name=sheet.name,
            field=field,
            kept_column=columns[0],
            dropped_columns=tuple(columns[1:]),
        )
        for field, columns in claimed.items()
        if len(columns) > 1
    )
    for duplicate in duplicates:
        logger.warning(
            "sheet %r: column(s) %s were labelled %s as well as column %d; the lowest "
            "index wins and the rest are dropped",
            sheet.name,
            ", ".join(str(column) for column in duplicate.dropped_columns),
            duplicate.field,
            duplicate.kept_column,
        )

    answered = Counter(labelled.column for labelled in in_range)
    unlabelled = tuple(
        column for column in range(location.column_count) if not answered[column]
    )
    if unlabelled:
        logger.info(
            "sheet %r: the column labeller said nothing about column(s) %s of %d",
            sheet.name,
            ", ".join(str(column) for column in unlabelled),
            location.column_count,
        )

    return SheetLabelling(
        bindings=tuple(
            ColumnBinding(column=columns[0], field=field)
            for field, columns in sorted(claimed.items(), key=lambda item: item[1][0])
        ),
        duplicates=duplicates,
        out_of_range_columns=out_of_range,
        unlabelled_columns=unlabelled,
        call=call,
    )
