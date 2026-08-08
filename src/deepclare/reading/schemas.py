"""The shape the model is asked to answer in.

Everything in this module reaches the provider. A Pydantic class docstring becomes the
schema's `description`, and a `Field(description=...)` becomes the property's — both are
prompt text, and prompt text lives in the prompt files. So nothing here carries either,
and the notes below are `#` comments, which stay in this file. The field rules the model
actually needs are in `read_invoice.md` and `read_consignment_note.md`, which are
reviewed together with this module: the schema and the prompt reach the model as one
artifact, and a contract stated in one and contradicted by the other is how the two
silently drift apart.

These are transcriptions, not records. They carry no provenance object, no line ids, no
document type and no confidence structure — a model is asked only for what it can see.
Everything else is attached by the stage that made the call.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema

# Pydantic renders Decimal as a union of a number and a string constrained by a pattern
# containing a negative lookahead, which is outside the regular-expression dialect a
# provider's schema validator is obliged to support. A figure printed on an invoice
# arrives as a JSON number; saying so plainly is both accurate and portable.
Number = Annotated[Decimal, WithJsonSchema({"type": "number"})]

# The 1-based position of the attached image, never a number printed on the paper. On a
# document read that is the logical page number of the document; on a page-type verdict it
# is the position in the batch that was presented.
Page = Annotated[int, Field(ge=1)]

# The model's own probability that what it transcribed is character-for-character what is
# printed. It grades legibility, never plausibility, and it is a self-report: nothing in
# this system measures it.
ExtractionConfidence = Annotated[float, Field(ge=0.0, le=1.0)]


class ReadText(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    page: Page
    confidence: ExtractionConfidence


class ReadNumber(BaseModel):
    model_config = ConfigDict(frozen=True)

    number: Number
    page: Page
    confidence: ExtractionConfidence


# A party is one printed block, so its three lines share one page and one confidence.
class ReadParty(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = None
    address: str | None = None
    tax_code: str | None = None
    page: Page
    confidence: ExtractionConfidence


# A goods row is printed as one row and read as one, so the whole row shares one page and
# one confidence. Header values do not: an invoice scatters them, and a single page
# number covering the seller block and the total would be wrong for one of them.
class ReadGoodsLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str
    printed_line_number: int | None = None
    quantity: Number | None = None
    unit: str | None = None
    gross_weight: Number | None = None
    net_weight: Number | None = None
    weight_unit: str | None = None
    unit_price: Number | None = None
    total_price: Number | None = None
    package_count: Number | None = None
    package_type: str | None = None
    origin_country: str | None = None
    trade_name: str | None = None
    units_per_package: Number | None = None
    package_weight_kg: Number | None = None
    dimensions: str | None = None
    printed_customs_code: str | None = None
    page: Page
    confidence: ExtractionConfidence


# Freight, transport and every other service row. They are not goods and never become
# goods lines; they are returned so that the gap between the invoice's printed total and
# the declared goods value is auditable rather than silent.
class ReadServiceCharge(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str
    amount: Number | None = None
    page: Page
    confidence: ExtractionConfidence


# Property order is generation order: the header is written first, then the service rows,
# then the goods table, which is the order the pages are read in.
class ReadInvoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    invoice_number: ReadText | None = None
    invoice_date: ReadText | None = None
    currency: ReadText | None = None
    incoterms_code: ReadText | None = None
    incoterms_place: ReadText | None = None
    origin_country: ReadText | None = None
    seller: ReadParty | None = None
    buyer: ReadParty | None = None
    total_amount: ReadNumber | None = None
    service_charges: list[ReadServiceCharge] = []
    goods_lines: list[ReadGoodsLine] = []


# A literal union rather than the domain's PageClass: an enumeration's class docstring
# becomes the schema's description, and what each of these three labels means is stated in
# classify_page_type.md. The values match PageClass so the mapping is total.
PageTypeLabel = Literal["invoice", "consignment_note", "other"]


class ClassifiedPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    page: Page
    page_type: PageTypeLabel


# Required rather than defaulted to an empty list: every batch has pages, so an answer
# that names none of them is a malformed answer and not a batch of unclassified pages.
class ClassifyPageType(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdicts: list[ClassifiedPage]


# --- the spreadsheet path -------------------------------------------------------------
# A workbook is read from an exact, deterministic rendering of its own cells, so the two
# things the vision shapes carry have no referent here. There is no page: a workbook is
# not paginated and a sheet is not a page. And legibility is not in question: the text is
# the cell, character for character. What is genuinely uncertain on this channel is which
# cell holds which field, and that is what `confidence` grades — the same question the
# vision path asks, resting on the one risk this input actually has.


class WorkbookText(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    confidence: ExtractionConfidence


class WorkbookNumber(BaseModel):
    model_config = ConfigDict(frozen=True)

    number: Number
    confidence: ExtractionConfidence


class WorkbookParty(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = None
    address: str | None = None
    tax_code: str | None = None
    confidence: ExtractionConfidence


# The goods lines this call returns are a first guess. They are kept only when the
# structural path — locate the table, label its columns, read the typed cells by index —
# produced nothing, because a model asked to transcribe every numeric value of a table
# reliably drops one of two adjacent similar fields whatever the prompt says.
class WorkbookGoodsLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str
    printed_line_number: int | None = None
    quantity: Number | None = None
    unit: str | None = None
    gross_weight: Number | None = None
    net_weight: Number | None = None
    weight_unit: str | None = None
    unit_price: Number | None = None
    total_price: Number | None = None
    package_count: Number | None = None
    package_type: str | None = None
    origin_country: str | None = None
    trade_name: str | None = None
    units_per_package: Number | None = None
    package_weight_kg: Number | None = None
    dimensions: str | None = None
    printed_customs_code: str | None = None
    confidence: ExtractionConfidence


class WorkbookServiceCharge(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str
    amount: Number | None = None
    confidence: ExtractionConfidence


class ReadWorkbookInvoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    invoice_number: WorkbookText | None = None
    invoice_date: WorkbookText | None = None
    currency: WorkbookText | None = None
    incoterms_code: WorkbookText | None = None
    incoterms_place: WorkbookText | None = None
    origin_country: WorkbookText | None = None
    seller: WorkbookParty | None = None
    buyer: WorkbookParty | None = None
    total_amount: WorkbookNumber | None = None
    service_charges: list[WorkbookServiceCharge] = []
    goods_lines: list[WorkbookGoodsLine] = []


# The label vocabulary, and the only place it is written down. The values are the goods
# line's own field names so that a label cannot drift from the field it binds to: there is
# no translation table between what the model says and what the typed reader writes.
ColumnLabel = Literal[
    "printed_line_number",
    "description",
    "quantity",
    "unit",
    "gross_weight",
    "net_weight",
    "weight_unit",
    "unit_price",
    "total_price",
    "package_count",
    "package_type",
    "origin_country",
    "trade_name",
    "units_per_package",
    "package_weight_kg",
    "dimensions",
    "printed_customs_code",
    "ignore",
]


class LabelledColumn(BaseModel):
    model_config = ConfigDict(frozen=True)

    column: int = Field(ge=0)
    label: ColumnLabel


# One label per column and never a value. This is the whole point of the node: the answer
# space is bounded by the table's own width, so nothing here can lose a figure.
class LabelColumns(BaseModel):
    model_config = ConfigDict(frozen=True)

    columns: list[LabelledColumn]


class ReadConsignmentNote(BaseModel):
    model_config = ConfigDict(frozen=True)

    cmr_number: ReadText | None = None
    sender: ReadParty | None = None
    consignee: ReadParty | None = None
    carrier: ReadParty | None = None
    place_of_loading: ReadText | None = None
    place_of_delivery: ReadText | None = None
    country_of_dispatch: ReadText | None = None
    date: ReadText | None = None
    vehicle_plates: list[ReadText] = []
    goods_description: ReadText | None = None
    package_count: ReadNumber | None = None
    package_type: ReadText | None = None
    gross_weight: ReadNumber | None = None
    weight_unit: ReadText | None = None
    attached_documents: list[ReadText] = []
