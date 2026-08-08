"""What assembly is given, and what it hands back.

Dossier 10 §3 M11: the extracted records, the per-line drafts, the declarant-side profile
and the reference tables. Everything arrives as explicit input — nothing here reaches for
a provider, a database or the environment, so one run is a pure function of this object.

The declarant profile is separate from the documents on purpose. Where an importer clears
their goods and who fills the form in are properties of the importer, not of the shipment,
and no document states either.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from deepclare.classification.records import LineClassification
from deepclare.description.records import LineDescription
from deepclare.domain import (
    ConsignmentNote,
    Declaration,
    InvoiceGoodsLine,
    InvoiceRecord,
    LineEnrichment,
    ReviewItem,
)


class LineDraft(BaseModel):
    """One goods line with everything the earlier stages produced for it."""

    model_config = ConfigDict(frozen=True)

    line: InvoiceGoodsLine
    description: LineDescription
    classification: LineClassification
    enrichment: LineEnrichment | None = None
    """What a catalogue or spec sheet added. It fills gaps the invoice left and never
    overwrites an invoice value."""

    @property
    def line_id(self) -> str:
        return self.line.line_id


class GoodsLocationProfile(BaseModel):
    """Box 30 — where this importer's goods sit while they clear.

    The two defaults are the corpus mode, not a design choice: a temporary-storage
    warehouse at the central office. An unconfirmed profile files them as a guess,
    because a wrong customs office is a real-world error the operator must catch.
    """

    model_config = ConfigDict(frozen=True)

    information_type_code: str = "11"
    customs_office_code: str = "05100010"
    country_code: str = "AM"
    customs_zone_number: str | None = None
    confirmed: bool = False


class FillerProfile(BaseModel):
    """Box 54 — the person completing the declaration."""

    model_config = ConfigDict(frozen=True)

    surname: str = Field(min_length=1)
    given_name: str = Field(min_length=1)
    phone: str | None = None
    email: str | None = None


class ImporterProfile(BaseModel):
    """The importing company, for the runs where the documents do not name it.

    Never a substitute for what a document says: dossier 03 §5.3 requires the importer to
    come from the invoice's buyer or the consignment note's consignee, and this fills only
    what neither states.
    """

    model_config = ConfigDict(frozen=True)

    name: str | None = None
    tax_code: str | None = None
    street_house: str | None = None


class DeclarantProfile(BaseModel):
    """Everything about the declarant that no document carries."""

    model_config = ConfigDict(frozen=True)

    goods_location: GoodsLocationProfile | None = None
    filler: FillerProfile | None = None
    importer: ImporterProfile | None = None


class AssemblyInput(BaseModel):
    """One run's whole input."""

    model_config = ConfigDict(frozen=True)

    invoice: InvoiceRecord
    lines: tuple[LineDraft, ...] = Field(min_length=1)
    """In the order they will be filed, which is the invoice's printed order. The item
    numbers are positions in this tuple; the line ids are the join key every stage shares."""

    consignment_note: ConsignmentNote | None = None
    profile: DeclarantProfile = DeclarantProfile()


class UnitTier(StrEnum):
    """Which rung of the ladder resolved a line's unit.

    Dossier 03 §4.1 requires every resolution to be logged with its tier, and the tier is
    the whole account of how much the unit is worth: the nomenclature prescribing it and
    a kilogram default are not the same claim.
    """

    CODE_SUPPLEMENTARY = "code_supplementary"
    """The nomenclature's own unit for the assigned commodity code. Authoritative."""

    INVOICE = "invoice"
    """The invoice's own unit column, where the code carries none."""

    PRODUCT_KIND = "product_kind"
    """Inferred from what the goods physically are."""

    KILOGRAM_DEFAULT = "kilogram_default"
    """Nothing resolved. Always flagged."""


class UnitResolution(BaseModel):
    """One line's resolved unit and the rung that produced it."""

    model_config = ConfigDict(frozen=True)

    line_id: str
    tier: UnitTier
    okei: str
    name_hy: str
    source_text: str | None = None
    """The string the tier read, where it read one."""

    conflicted_with_invoice: bool = False
    """The code and the invoice named different units. The code wins and the operator is
    told, because the two disagreeing is the shape that files a magnitude under a count."""


class AssembledDeclaration(BaseModel):
    """A complete internal declaration, and everything a human must confirm about it."""

    model_config = ConfigDict(frozen=True)

    declaration: Declaration
    review_items: tuple[ReviewItem, ...] = ()
    unit_resolutions: tuple[UnitResolution, ...] = ()
    """Per line, in line order. Structured rather than prose so that the tier can be
    asserted and counted, not only read."""
