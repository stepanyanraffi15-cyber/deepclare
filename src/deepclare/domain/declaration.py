"""The declaration as a set of concepts, before anything decides how it is written.

Dossier 03 §1 is the shape this follows: a submission produces one declaration, which
carries shipment-level facts, a foreign consignor, an importer, a goods location, a
consignment with its transport, one or more goods items, and the person filling it in.

Nothing here knows an element name, a child order, a namespace, a decimal separator or
the difference between an omitted and an empty element. Those belong to the filing
adapter, and dossier 10 §3 M11 makes the split load-bearing: assembly knows *what value
is correct*, the adapter knows *how the value is written*.

Two consequences of that rule are easy to get wrong and are worth stating:

* **Values fixed by the contract are not here.** The procedure token, the mode codes,
  the preference marker, the specification and sheet numbers, the document-mode
  identifier — every one of them is a constant of the filed format with no domain
  choice behind it, so the adapter supplies them. A field here would invite a caller to
  vary something that cannot vary.
* **Code and name travel together.** Dossier 03 §4.5: the portal keys these fields on
  the code and renders the name from it, so a name filed without its code is dropped on
  import with no message. `CodedValue` makes the pair inseparable at the type level
  rather than by convention at six call sites.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from deepclare.domain.provenance import Traced


class CodedValue(BaseModel):
    """A code and the name that goes with it, which are emitted or omitted together.

    Dossier 03 §4.5 — all-or-nothing. Six pairs in the document behave this way, and a
    half-written pair is the contract's third failure signal: the import succeeds and
    the value is simply not there afterwards.
    """

    model_config = ConfigDict(frozen=True)

    code: Traced[str]
    name: Traced[str]


class PostalAddress(BaseModel):
    """A party's address, to the extent the filed format carries it."""

    model_config = ConfigDict(frozen=True)

    country: CodedValue | None = None
    street_house: Traced[str] | None = None
    """The street-and-house line. The filed format caps it, and one over-long value
    rejects the whole file — the adapter truncates and says so."""


class Organization(BaseModel):
    """A company on the declaration: the foreign consignor, or the importer."""

    model_config = ConfigDict(frozen=True)

    name: Traced[str] | None = None
    tax_code: Traced[str] | None = None
    """The Armenian taxpayer registration number, for the importer only. A foreign
    consignor has none and the contract has nowhere to put one."""

    address: PostalAddress | None = None


class GoodsLocation(BaseModel):
    """Box 30 — where this importer's goods sit while they clear.

    Dossier 03 §5.4: none of it is derivable from the documents. It is a property of the
    importer, comes from their profile, and an unconfirmed profile files a guess.
    """

    model_config = ConfigDict(frozen=True)

    information_type_code: Traced[str]
    customs_office_code: Traced[str]
    country_code: Traced[str]
    customs_zone_number: Traced[str] | None = None


class TransportMeansRecord(BaseModel):
    """One vehicle. Dossier 03 §4.6: one per distinct plate, the identifier verbatim."""

    model_config = ConfigDict(frozen=True)

    identifier: Traced[str]
    nationality_country_code: Traced[str] | None = None


class TransportBlock(BaseModel):
    """The vehicles and mode for one leg. Departure/arrival and border are identical.

    `vehicle_quantity` is carried rather than computed because dossier 03 §4.6 records a
    live disagreement about it: the accepted filings file twice the number of vehicle
    records under road mode 31, the predecessor filed the count 1:1, and no rejection was
    ever observed either way. Whoever resolves that decides the number; this type only
    carries it, and the adapter files what it is given.
    """

    model_config = ConfigDict(frozen=True)

    mode_code: Traced[str]
    vehicles: tuple[TransportMeansRecord, ...] = ()
    vehicle_quantity: Traced[int] | None = None


class BorderOffice(BaseModel):
    """Box 12 — the crossing point. Dossier 03 §5.6: the code is required once the block
    exists, so an unmapped route omits the whole block rather than half of it."""

    model_config = ConfigDict(frozen=True)

    code: Traced[str]
    name: Traced[str] | None = None
    country_code: Traced[str] | None = None


class DeliveryTerms(BaseModel):
    """Box 20 — the Incoterms code and its place, both verbatim and unvalidated."""

    model_config = ConfigDict(frozen=True)

    terms_code: Traced[str] | None = None
    place: Traced[str] | None = None


class Consignment(BaseModel):
    """How the shipment moved and on what commercial terms."""

    model_config = ConfigDict(frozen=True)

    container_indicator: Traced[bool] | None = None
    """Assembly supplies `false` when there is no consignment note to read a container
    keyword from. It is optional here so that reading a filed declaration that omits it
    cannot become an invented `false`."""

    dispatch_country: CodedValue | None = None
    border_office: BorderOffice | None = None
    departure_transport: TransportBlock | None = None
    border_transport: TransportBlock | None = None
    currency_code: Traced[str] | None = None
    total_invoice_amount: Traced[Decimal] | None = None
    trade_country_code: Traced[str] | None = None
    delivery_terms: DeliveryTerms | None = None


class SupplementaryQuantity(BaseModel):
    """Box 41 — a figure and the unit it is genuinely expressed in.

    Dossier 03 §4.2 is the reason all three parts are required together: a magnitude
    filed under a count unit is a mislabelled figure, and the pairing rule exists so that
    can never happen. The unit code is a fixed-width token, a string, never a number.
    """

    model_config = ConfigDict(frozen=True)

    quantity: Traced[Decimal]
    unit_code: Traced[str]
    unit_name: Traced[str]


class Packaging(BaseModel):
    """Boxes 6 and 31 — how many packages, of what kind, in what packing."""

    model_config = ConfigDict(frozen=True)

    package_count: Traced[Decimal] | None = None
    package_type_code: Traced[str] | None = None
    """The portal's 0/1/2 classifier. Assembly always populates it, always as a guess;
    optional here for the same reason as the container indicator."""

    packing_code: Traced[str] | None = None
    """UN/ECE Recommendation 21. Absent means the whole packing sub-block is absent."""

    packing_quantity: Traced[Decimal] | None = None


class GoodsItem(BaseModel):
    """One declared goods line — the heart of the model."""

    model_config = ConfigDict(frozen=True)

    item_number: int = Field(ge=1)
    """1-based sequential position within the declaration."""

    line_id: str = Field(pattern=r"^[1-9][0-9]*$")
    """The join key every stage shares, so a review item can name the line a human sees
    rather than the position it happened to land in."""

    description: Traced[str]
    gross_weight: Traced[Decimal] | None = None
    net_weight: Traced[Decimal] | None = None
    invoiced_cost: Traced[Decimal] | None = None

    commodity_code: Traced[str] | None = None
    """The filed form: the ten-digit leaf plus the Armenian national digit. Absent means
    the classifier abstained, and the abstention rationale is a review item."""

    origin_country: CodedValue | None = None
    customs_cost_method: Traced[str] | None = None
    """Box 43. Assembly never leaves it blank — a line with a price files transaction
    value, one without files the reserve method as a guess. Optional here only so that
    reading a filed declaration cannot invent one."""

    supplementary_quantity: SupplementaryQuantity | None = None
    """Absent hangs the portal's import at 100% with no message. Dossier 03 §4.2 gives
    the fallback that keeps it populated; the adapter refuses to call a document
    conformant without it."""

    packaging: Packaging = Packaging()
    """Dossier 03 §5.5 emits the packaging block on every line so the 0/1/2 classifier is
    always in front of the user. That is a product decision and not an importer
    requirement, so a line with nothing to put in it writes no block rather than an empty
    one."""


class FillerPerson(BaseModel):
    """Box 54 — the person completing the declaration, from the declarant profile."""

    model_config = ConfigDict(frozen=True)

    surname: Traced[str]
    given_name: Traced[str]
    phone: Traced[str] | None = None
    email: Traced[str] | None = None


class Declaration(BaseModel):
    """One import declaration, complete, in domain terms.

    This is what assembly produces and what the filing adapter writes. Absence is a
    plain `None` here: the adapter is the only thing that knows absence is expressed by
    leaving the element out.
    """

    model_config = ConfigDict(frozen=True)

    origin_country_name: Traced[str] | None = None
    """Box 16. Name only — this one has no code half, unlike every other country field."""

    total_goods_number: Traced[int]
    total_package_number: Traced[Decimal] | None = None
    """The portal recomputes this on import, so the filed value is a preview."""

    consignor: Organization | None = None
    """The foreign seller or shipper, box 2."""

    importer: Organization | None = None
    """One company fills boxes 8, 9 and 14 on an import; the adapter fans it out."""

    goods_location: GoodsLocation | None = None
    consignment: Consignment
    goods: tuple[GoodsItem, ...] = Field(min_length=1)
    filler: FillerPerson | None = None
