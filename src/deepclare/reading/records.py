"""From what the model answered to domain records, with provenance on every value.

This is where reading earns its name. The model returns transcriptions; a record needs to
say, of each value, which uploaded file it came from, what that file was, which page it
was printed on and how well it could be read. None of that is recoverable later — a
reviewer looking at a value cannot reconstruct which page produced it — so it is attached
here, at the producer, or it does not exist at all.

The unit of provenance is the printed block a value was read from: a header value is its
own block, a party is one block of three lines, and a goods row is one block of many
fields. That is why a goods line carries one page and one confidence for the whole row
while the header carries them per field.

Regions are page-level: a page number and no bounding box. Asking a vision model for
coordinates on a dense goods table is a second job with its own failure mode, and what a
reviewer needs in order to find a value is the page it is printed on.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, ValidationError

from deepclare.domain import (
    Confidence,
    ConsignmentNote,
    DocumentRegion,
    InvoiceGoodsLine,
    InvoiceRecord,
    Party,
    Provenance,
    Traced,
    Transform,
    ValueOrigin,
)
from deepclare.intake import LogicalDocument
from deepclare.models import ModelCall
from deepclare.reading.errors import ReadingError
from deepclare.reading.schemas import (
    ReadConsignmentNote,
    ReadGoodsLine,
    ReadInvoice,
    ReadNumber,
    ReadParty,
    ReadServiceCharge,
    ReadText,
)

STAGE = "reading"
"""What every value produced here names as its producing stage."""


class ServiceCharge(BaseModel):
    """A freight, transport or other service row printed on the invoice.

    It is not a goods line and never becomes one, and it is not counted into the goods
    total. It is kept because the difference between the invoice's own printed total and
    the value declared for the goods has to be explainable by something an operator can
    point at.
    """

    model_config = ConfigDict(frozen=True)

    description: Traced[str]
    amount: Traced[Decimal] | None = None


class InvoiceReading(BaseModel):
    """One invoice, as read, and the account of the call that read it."""

    model_config = ConfigDict(frozen=True)

    invoice: InvoiceRecord
    service_charges: tuple[ServiceCharge, ...] = ()
    call: ModelCall


class ConsignmentNoteReading(BaseModel):
    """One consignment note, as read, and the account of the call that read it."""

    model_config = ConfigDict(frozen=True)

    consignment_note: ConsignmentNote
    call: ModelCall


def invoice_from_answer(
    answer: ReadInvoice, document: LogicalDocument, call: ModelCall
) -> InvoiceReading:
    """Build the invoice record from what the model returned."""
    context = _ReadContext(document=document, call=call)
    if not answer.goods_lines:
        raise ReadingError(
            f"the {len(document.pages)}-page invoice yielded no goods lines. There is "
            "nothing to declare, and a declaration with no goods is not a lesser draft "
            "but a different document."
        )

    lines = tuple(
        _goods_line(line, str(position), context)
        for position, line in enumerate(answer.goods_lines, start=1)
    )
    charges = tuple(
        _service_charge(charge, position, context)
        for position, charge in enumerate(answer.service_charges, start=1)
    )

    invoice = _build(
        InvoiceRecord,
        source_document_id=context.first_source_document_id,
        pages=tuple(page.classification for page in document.pages),
        goods_lines=lines,
        invoice_number=_text(answer.invoice_number, context, "invoice_number"),
        invoice_date=_text(answer.invoice_date, context, "invoice_date"),
        currency=_text(answer.currency, context, "currency"),
        incoterms_code=_text(answer.incoterms_code, context, "incoterms_code"),
        incoterms_place=_text(answer.incoterms_place, context, "incoterms_place"),
        origin_country=_text(answer.origin_country, context, "origin_country"),
        seller=_party(answer.seller, context, "seller"),
        buyer=_party(answer.buyer, context, "buyer"),
        total_amount=_number(answer.total_amount, context, "total_amount"),
    )
    return InvoiceReading(invoice=invoice, service_charges=charges, call=call)


def consignment_note_from_answer(
    answer: ReadConsignmentNote, document: LogicalDocument, call: ModelCall
) -> ConsignmentNoteReading:
    """Build the consignment-note record from what the model returned."""
    context = _ReadContext(document=document, call=call)
    note = _build(
        ConsignmentNote,
        source_document_id=context.first_source_document_id,
        pages=tuple(page.classification for page in document.pages),
        cmr_number=_text(answer.cmr_number, context, "cmr_number"),
        # A party is always present on the record: an empty one says the box was there
        # and unreadable, which is not the same as the form omitting it.
        sender=_party(answer.sender, context, "sender") or Party(),
        consignee=_party(answer.consignee, context, "consignee") or Party(),
        carrier=_party(answer.carrier, context, "carrier") or Party(),
        place_of_loading=_text(answer.place_of_loading, context, "place_of_loading"),
        place_of_delivery=_text(answer.place_of_delivery, context, "place_of_delivery"),
        country_of_dispatch=_text(
            answer.country_of_dispatch, context, "country_of_dispatch"
        ),
        date=_text(answer.date, context, "date"),
        vehicle_plates=_plates(answer.vehicle_plates, context),
        goods_description=_text(answer.goods_description, context, "goods_description"),
        package_count=_number(answer.package_count, context, "package_count"),
        package_type=_text(answer.package_type, context, "package_type"),
        gross_weight=_number(answer.gross_weight, context, "gross_weight"),
        weight_unit=_text(answer.weight_unit, context, "weight_unit"),
        attached_documents=tuple(
            traced
            for position, entry in enumerate(answer.attached_documents, start=1)
            if (traced := _text(entry, context, f"attached_documents[{position}]"))
        ),
    )
    return ConsignmentNoteReading(consignment_note=note, call=call)


@dataclass(frozen=True)
class _ReadContext:
    """What every value of one read needs in order to say where it came from."""

    document: LogicalDocument
    call: ModelCall

    @property
    def first_source_document_id(self) -> str:
        """The uploaded file the document starts in.

        A logical document's pages may come from several uploads — an invoice and a
        consignment note scanned into one file is ordinary — so this identifies the
        record, while each value names the file its own page came from.
        """
        return self.document.pages[0].rendered.source_document_id

    def provenance(self, page: int, field: str) -> Provenance:
        """Where the value on this logical page was read from.

        A page outside the group is not a value with a doubtful provenance; it is a value
        whose provenance is false. The run stops rather than record it.
        """
        pages = self.document.pages
        if not 1 <= page <= len(pages):
            raise ReadingError(
                f"{field}: the reader placed the value on page {page} of a "
                f"{len(pages)}-page {self.document.role} document. A value cannot carry "
                "a page the document does not have."
            )
        return Provenance(
            origin=ValueOrigin.EXTRACTED,
            source_document_id=pages[page - 1].rendered.source_document_id,
            source_document_role=self.document.role.value,
            region=DocumentRegion(page_number=page),
            stage=STAGE,
            prompt_name=self.call.prompt_name,
            prompt_version=self.call.prompt_version,
        )


def _text(
    value: ReadText | None, context: _ReadContext, field: str
) -> Traced[str] | None:
    if value is None:
        return None
    return _traced_str(
        value.text, context.provenance(value.page, field), _confidence(value.confidence)
    )


def _number(
    value: ReadNumber | None, context: _ReadContext, field: str
) -> Traced[Decimal] | None:
    if value is None:
        return None
    return _traced_decimal(
        value.number,
        context.provenance(value.page, field),
        _confidence(value.confidence),
    )


def _party(
    value: ReadParty | None, context: _ReadContext, field: str
) -> Party | None:
    if value is None:
        return None
    provenance = context.provenance(value.page, field)
    confidence = _confidence(value.confidence)
    return Party(
        name=_traced_str(value.name, provenance, confidence),
        address=_traced_str(value.address, provenance, confidence),
        tax_code=_traced_str(value.tax_code, provenance, confidence),
    )


def _goods_line(
    line: ReadGoodsLine, line_id: str, context: _ReadContext
) -> InvoiceGoodsLine:
    """One goods row. Every field on it shares the row's page and the row's confidence."""
    provenance = context.provenance(line.page, f"goods line {line_id}")
    confidence = _confidence(line.confidence)

    def text(value: str | None) -> Traced[str] | None:
        return _traced_str(value, provenance, confidence)

    def number(value: Decimal | None) -> Traced[Decimal] | None:
        return _traced_decimal(value, provenance, confidence)

    return _build(
        InvoiceGoodsLine,
        # The join key is positional and assigned here, not asked of the model: the
        # caller knows it, and a field the caller knows is one more thing to mislabel.
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
        quantity=number(line.quantity),
        unit=text(line.unit),
        gross_weight=number(line.gross_weight),
        net_weight=number(line.net_weight),
        weight_unit=text(line.weight_unit),
        unit_price=number(line.unit_price),
        total_price=number(line.total_price),
        package_count=number(line.package_count),
        package_type=text(line.package_type),
        origin_country=text(line.origin_country),
        trade_name=text(line.trade_name),
        units_per_package=number(line.units_per_package),
        package_weight_kg=number(line.package_weight_kg),
        dimensions=text(line.dimensions),
        printed_customs_code=text(line.printed_customs_code),
    )


def _service_charge(
    charge: ReadServiceCharge, position: int, context: _ReadContext
) -> ServiceCharge:
    provenance = context.provenance(charge.page, f"service charge {position}")
    confidence = _confidence(charge.confidence)
    description = _traced_str(charge.description, provenance, confidence)
    if description is None:
        raise ReadingError(
            f"service charge {position} was returned with no description; a charge "
            "nobody can name cannot be reconciled against the invoice total."
        )
    return ServiceCharge(
        description=description,
        amount=_traced_decimal(charge.amount, provenance, confidence),
    )


def _plates(
    plates: list[ReadText], context: _ReadContext
) -> tuple[Traced[str], ...]:
    """Vehicle plates, spaces removed and uppercased, blanks dropped.

    The transform is recorded on each value, because the filed plate and the printed one
    then differ and the difference has to be walkable back to the ink. Nothing here can
    tell one plate restated in two formats apart from two vehicles; that rule lives in
    the extraction instruction alone, so duplicates remain possible.
    """
    kept: list[Traced[str]] = []
    for position, plate in enumerate(plates, start=1):
        traced = _text(plate, context, f"vehicle_plates[{position}]")
        if traced is None:
            continue
        normalized = traced.value.replace(" ", "").upper()
        if not normalized:
            continue
        if normalized == traced.value:
            kept.append(traced)
            continue
        kept.append(
            traced.with_transform(
                Transform(
                    operation="strip-spaces-uppercase",
                    before=traced.value,
                    after=normalized,
                    reason="one plate must have one written form, or the same vehicle "
                    "counts twice",
                ),
                normalized,
            )
        )
    return tuple(kept)


def _traced_str(
    value: str | None, provenance: Provenance, confidence: Confidence
) -> Traced[str] | None:
    """A printed string. Whitespace-only is nothing printed, not an empty value."""
    if value is None or not value.strip():
        return None
    return Traced[str](value=value, provenance=provenance, confidence=confidence)


def _traced_decimal(
    value: Decimal | None, provenance: Provenance, confidence: Confidence
) -> Traced[Decimal] | None:
    if value is None:
        return None
    return Traced[Decimal](value=value, provenance=provenance, confidence=confidence)


def _confidence(extraction: float) -> Confidence:
    """Extraction only. Nothing has been derived yet and nothing has been filed yet."""
    return Confidence(extraction=extraction)


def _build[T: BaseModel](record: type[T], **fields: object) -> T:
    """Construct a domain record, or fail as a reading failure.

    The domain's own rules — a line needs a description, an invoice needs a line — are
    enforced at construction. A model answer that breaks one is a failed read, not a
    record to repair: repairing it would mean deciding what the page said.
    """
    try:
        return record(**fields)
    except ValidationError as exc:
        raise ReadingError(
            f"what the model returned is not a valid {record.__name__}: {exc}"
        ) from exc
