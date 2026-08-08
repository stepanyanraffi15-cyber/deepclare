"""What was read off the source documents, before anything was derived from it.

Extraction is **verbatim and untranslated**: every value here is transcribed in the
source language exactly as printed. Nothing is reformatted on the way in — dates
especially keep their printed form (`12.03.2026` stays `12.03.2026`); the ISO form is a
render-time concern of whatever emits the declaration. Armenian is produced downstream,
never here.

Every extracted field is optional, because documents are incomplete. The single
exception is a goods line's description: a line without one is not a line. The
consequences of every other absence are decided at assembly and emission, not here.

The document's *type* is never an extracted field. It is a constant of the record: an
invoice is read into an `InvoiceRecord`, a consignment note into a `ConsignmentNote`.
Asking a model to name the document type produced tokens nobody consumed.

This module knows nothing about commodity codes or the nomenclature, the filing
contract, the review vocabulary, or any model or prompt. It is what the page said.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deepclare.domain.provenance import Traced


class DocumentRole(StrEnum):
    """What an uploaded file is, among the sources of one submission.

    Declared by the client when it labels the upload; otherwise inferred from the
    filename in this precedence: consignment-note keyword, then catalog/spec keywords,
    then an XML extension or declaration keyword, then invoice. Invoice is the default
    because a missing invoice is the fatal case and a prior declaration is the only XML
    among the sources.
    """

    INVOICE = "invoice"
    CONSIGNMENT_NOTE = "consignment_note"
    CATALOG_SPEC = "catalog_spec"
    """Supporting evidence. Never counts as the invoice."""

    PRIOR_DECLARATION = "prior_declaration"
    """One of the tenant's own filed declarations. Supporting; never the invoice."""


class PageClass(StrEnum):
    """The per-page grouping verdict.

    A different vocabulary from `DocumentRole` and deliberately so: a page is judged
    only on whether it belongs to the invoice, to the consignment note, or to neither.
    """

    INVOICE = "invoice"
    CONSIGNMENT_NOTE = "consignment_note"
    OTHER = "other"
    """Cover sheets, packing lists, certificates."""


class SourceLanguage(StrEnum):
    """The script a goods line is written in, so downstream readers use the right lexicon.

    Detected deterministically by script, in this precedence: Armenian, then Cyrillic
    (Russian), then Farsi/Arabic, then Turkish (by the diacritics İıŞşĞğ, near-unique
    among the sources), then English/Latin as the default. It is never asked of a model.
    """

    ARMENIAN = "armenian"
    RUSSIAN = "russian"
    FARSI_ARABIC = "farsi_arabic"
    TURKISH = "turkish"
    ENGLISH_LATIN = "english_latin"


class PageClassification(BaseModel):
    """Where one source page was judged to belong, and where it actually went.

    An "other" verdict is never honored: over-inclusion is the deliberate choice, because
    dropping a real invoice or consignment-note page loses goods, while a stray page
    costs only noise. An "other", missing or duplicated verdict all fall back to the
    source file's role hint, so `assigned_role` is in practice only ever invoice or
    consignment note and no page is ever dropped.
    """

    model_config = ConfigDict(frozen=True)

    source_document_id: str = Field(min_length=1)
    source_page_number: int = Field(ge=1, description="1-based, within the source file")
    verdict: PageClass | None = Field(
        default=None,
        description="None when the classifier returned nothing for this page, or "
        "returned more than one verdict for it.",
    )
    role_hint: DocumentRole
    assigned_role: DocumentRole


class Party(BaseModel):
    """A company on a document: name, address, tax or registration number, as printed.

    A party whose every field is empty is still a party — the block was there and
    unreadable, which is different from the document not naming a party at all.
    Collapsing the two loses the distinction, so nothing here forbids an empty `Party()`.
    """

    model_config = ConfigDict(frozen=True)

    name: Traced[str] | None = None
    address: Traced[str] | None = None
    tax_code: Traced[str] | None = None


class InvoiceGoodsLine(BaseModel):
    """One physical-goods row of the invoice, as printed.

    Rows describing transport, freight, delivery, shipping, carriage, logistics or any
    other service charge are not goods. They are never lines here and never counted into
    the invoice total, even when the invoice prints them inside the goods table.
    """

    model_config = ConfigDict(frozen=True)

    line_id: str = Field(
        pattern=r"^[1-9][0-9]*$",
        description="1-based positional join key assigned by the caller, outside "
        "extraction. Every stage joins on it, so it carries no provenance of its own.",
    )
    description: Traced[str]
    """Exactly as printed. The only mandatory field on a line."""

    printed_line_number: Traced[int] | None = None
    """The invoice's own row numbering, when it numbers rows. Drives final ordering
    only when every line is numbered."""

    quantity: Traced[Decimal] | None = None
    """Means nothing without the unit: the same magnitude is a count of pieces or a
    weight depending on what the column was labelled."""

    unit: Traced[str] | None = None
    """As printed — `PCS`, `KG`, and the `TONE` spelling that appears on real invoices.
    May be blank when the column carried no label."""

    gross_weight: Traced[Decimal] | None = None
    net_weight: Traced[Decimal] | None = None
    weight_unit: Traced[str] | None = None
    unit_price: Traced[Decimal] | None = None
    total_price: Traced[Decimal] | None = None
    package_count: Traced[Decimal] | None = None
    package_type: Traced[str] | None = None
    """e.g. `BAGS`, `BIGBAGS`."""

    origin_country: Traced[str] | None = None
    """As printed for this line. Takes precedence over the invoice-level origin."""

    trade_name: Traced[str] | None = None
    """Brand or model printed for this line, from a brand column or from inside the
    description. Never guessed."""

    units_per_package: Traced[Decimal] | None = None
    """Items in ONE package, only when printed (`12 PCS/CTN` gives 12). Never derived."""

    package_weight_kg: Traced[Decimal] | None = None
    """Weight of ONE package, only when printed (`25KG BAG` gives 25)."""

    dimensions: Traced[str] | None = None
    """This item's own measurements as printed. Never a shipment total, not CBM."""

    printed_customs_code: Traced[str] | None = None
    """A code printed on the line, under any of the headings HS CODE / HS / GTIP /
    TARIC / CTH / ТН ВЭД. Foreign national codes are expected. Transcribed as printed
    and never inferred, completed or repaired."""

    @field_validator("description")
    @classmethod
    def _description_must_say_something(cls, value: Traced[str]) -> Traced[str]:
        if not value.value.strip():
            raise ValueError("a goods line description cannot be blank")
        return value


class InvoiceRecord(BaseModel):
    """The commercial invoice, as read. Exactly one per submission."""

    model_config = ConfigDict(frozen=True)

    source_document_id: str = Field(min_length=1)
    goods_lines: tuple[InvoiceGoodsLine, ...] = Field(min_length=1)
    """In printed top-to-bottom order. An invoice that yields no goods lines is a
    rejected submission, not an invoice with an empty list."""

    pages: tuple[PageClassification, ...] = ()
    """The pages grouped into this document, in order: the i-th entry is logical page
    i+1, which is what a value's provenance region counts. Empty when the source was not
    paginated, as a spreadsheet is not."""

    invoice_number: Traced[str] | None = None
    invoice_date: Traced[str] | None = None
    """As printed. Not reformatted, not parsed, not reordered."""

    currency: Traced[str] | None = None
    incoterms_code: Traced[str] | None = None
    incoterms_place: Traced[str] | None = None
    """The place printed after the delivery-terms code."""

    origin_country: Traced[str] | None = None
    """The overall origin the invoice states. A line's own origin wins over it."""

    seller: Party | None = None
    """The foreign consignor."""

    buyer: Party | None = None
    """The importer."""

    total_amount: Traced[Decimal] | None = None
    """The value of the goods only. Freight and service charges are excluded even when
    the invoice's own TOTAL row includes them."""


class ConsignmentNote(BaseModel):
    """The road consignment note (CMR), as read. Zero or one per submission.

    Box numbers in the field notes are the CMR form's own.
    """

    model_config = ConfigDict(frozen=True)

    source_document_id: str = Field(min_length=1)
    pages: tuple[PageClassification, ...] = ()
    """As on the invoice: the i-th entry is logical page i+1."""

    cmr_number: Traced[str] | None = None

    # Boxes 1 and 2; the carrier has no numbered box. Always party objects: an empty one
    # says the block was unreadable, which is not the same as the form omitting it.
    sender: Party = Field(default_factory=Party)
    consignee: Party = Field(default_factory=Party)
    carrier: Party = Field(default_factory=Party)

    place_of_loading: Traced[str] | None = None
    """Box 4 — where the goods were taken over."""

    place_of_delivery: Traced[str] | None = None
    """Box 3."""

    country_of_dispatch: Traced[str] | None = None
    date: Traced[str] | None = None
    """As printed."""

    vehicle_plates: tuple[Traced[str], ...] = ()
    """Box 25, one entry per DISTINCT vehicle — a truck and a separate trailer are two,
    but one plate restated in a second format after a slash is one. Plates are recorded
    with spaces removed and uppercased, which is a transform on the traced value. The
    once-per-vehicle rule is held by the extraction instruction alone; nothing here can
    tell two formats of one plate apart, so duplicates remain possible."""

    goods_description: Traced[str] | None = None
    """The note's own goods wording. Only ever used to decide the container indicator —
    never as a goods line."""

    package_count: Traced[Decimal] | None = None
    """Box 7. Routinely a PALLET count, a different packaging level from the invoice's
    cartons; it must never be multiplied against per-carton factors."""

    package_type: Traced[str] | None = None
    """Box 8, e.g. `BIGBAGS`."""

    gross_weight: Traced[Decimal] | None = None
    """Box 11 — the shipment total, the basis for apportioning weight across lines."""

    weight_unit: Traced[str] | None = None
    attached_documents: tuple[Traced[str], ...] = ()
    """Box 5."""


class LineEnrichment(BaseModel):
    """What a catalog or spec document adds to one goods line.

    It fills only the gaps the invoice left: an enrichment value never overwrites a value
    the invoice stated, whatever the catalog says. Facts are different — they are always
    passed on as grounding for the description writer, gap or no gap.
    """

    model_config = ConfigDict(frozen=True)

    line_id: str = Field(pattern=r"^[1-9][0-9]*$")
    grounding_facts: tuple[Traced[str], ...] = ()
    """Free-text bullets about the product, for the description writer."""

    printed_customs_code: Traced[str] | None = None
    """A code printed in the catalog, transcribed as printed."""

    unit: Traced[str] | None = None
    net_weight: Traced[Decimal] | None = None
    gross_weight: Traced[Decimal] | None = None
    material: Traced[str] | None = None
    """Material or composition as the catalog states it."""
