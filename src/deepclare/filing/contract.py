"""The filed format itself: every element name, every sequence, every constant, every facet.

This is the one place in DeepClare that spells the customs contract out. Dossier 04 §0
is the framing and it is not negotiable: the element names, their order, their
cardinality, the namespaces and the empty-versus-absent rules belong to an external
customs system. Deviations fail import with one opaque message that names no field, no
line and no reason. Nothing here is a design.

Three of the format's properties look like mistakes and are not:

* **The misspellings are the contract.** `CounryName`, `ESADout_CUConsigment`,
  `Pakage*`/`Paking*`, `E_mail`, `ContainerIdentificaror` are the schema's own spellings
  and are reproduced character for character. Correcting one produces a rejected file.
* **Order is enforced even where presence is not.** Every complex type is a sequence.
  Two optional siblings in the wrong order rejected the whole file — the confirmed case
  is packaging quantity emitted after packaging type — and the message named no element.
* **Fixed-width codes are strings.** `00`, `000`, `055`, the eight-digit office codes.
  Parsing one as a number and writing it back destroys it, and nothing but literal
  discipline holds the widths.

## What this module does not know, and what that costs

Dossier 03 §5 names every *leaf* the emitter writes. It does not name several of the
*containers* those leaves sit in — the goods-item wrapper, the three importer party
blocks, the goods-location block and its children, the two transport blocks, the
contract-terms block, and the filler block and its children. Those names appear nowhere
in the specification, the authority's 5.10.0 schema was never obtained, and the corpus
of accepted filings that would settle them is customer data that did not transfer.

They are listed in `UNCONFIRMED_ELEMENT_NAMES`. An emitted document containing any of
them is **not filable**: `conformance.check` reports the rule `element-name-evidence` as
unconfirmed and names each one with its path. The names below are placeholders that keep
the document readable enough to diff against a real accepted filing — which is the one
thing that would confirm them — and they are wrong until that diff is done.

The same applies to `NAMESPACE_URI`. The specification states the namespace *family*
(the customs authority's `urn:customs.ru:…` set) and its version (5.10.0), and dossier
07 §2.6 records that filed documents carry three distinct prefixes. Which elements sit
in which of the three is not recorded anywhere, so this module puts the whole document
in one default namespace and reports `namespace-assignment` as unconfirmed rather than
inventing a three-way split per element.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

# --- namespace ------------------------------------------------------------------------

NAMESPACE_URI = "urn:customs.ru:Information:CustomsDocuments:ESADout_CU:5.10.0"
"""The root schema's namespace at the version actually filed and accepted.

The vendored schema set is 5.0.7 and declares
`urn:customs.ru:Information:CustomsDocuments:ESADout_CU:5.0.7`; the documents the portal
accepts are 5.10.0. Substituting the version is the only derivation the specification
supports, and it is unverified.
"""

DOCUMENT_MODE_ID = "1006107E"
"""Root attribute. Schema-fixed; the only permitted value."""


# --- element names --------------------------------------------------------------------
#
# Grouped by the block they belong to, in emission order. Spelling is contract.

ROOT = "ESADout_CU"

CUSTOMS_PROCEDURE = "CustomsProcedure"
CUSTOMS_MODE_CODE = "CustomsModeCode"
ORIGIN_COUNTRY_NAME_SHIPMENT = "OriginCountryName"
SPECIFICATION_NUMBER = "SpecificationNumber"
SPECIFICATION_LIST_NUMBER = "SpecificationListNumber"
TOTAL_GOODS_NUMBER = "TotalGoodsNumber"
TOTAL_PACKAGE_NUMBER = "TotalPackageNumber"
TOTAL_SHEET_NUMBER = "TotalSheetNumber"

CONSIGNOR = "ESADout_CUConsignor"
CONSIGNEE = "ESADout_CUConsignee"
RESPONSIBLE_PERSON = "ESADout_CUFinancialResponsiblePerson"
DECLARANT = "ESADout_CUDeclarant"
ORGANIZATION_NAME = "OrganizationName"
ORGANIZATION_FEATURES = "RAOrganizationFeatures"
TAX_CODE = "UNN"
ADDRESS = "Address"
COUNTRY_CODE = "CountryCode"
COUNTRY_NAME = "CounryName"
STREET_HOUSE = "StreetHouse"

GOODS_LOCATION = "ESADout_CUGoodsLocation"
GOODS_LOCATION_INFORMATION_TYPE = "InformationTypeCode"
GOODS_LOCATION_OFFICE_CODE = "CustomsOfficeCode"
GOODS_LOCATION_COUNTRY_CODE = "CustomsCountryCode"
CUSTOMS_ZONE = "CustomsZone"
CUSTOMS_ZONE_NUMBER = "CustomsZoneNumber"

GOODS_ITEM = "ESADout_CUGoods"
GOODS_NUMERIC = "GoodsNumeric"
GOODS_DESCRIPTION = "GoodsDescription"
GROSS_WEIGHT = "GrossWeightQuantity"
NET_WEIGHT = "NetWeightQuantity"
INVOICED_COST = "InvoicedCost"
COMMODITY_CODE = "GoodsTNVEDCode"
ADDITIONAL_SIGN = "AdditionalSign"
ORIGIN_COUNTRY_CODE = "OriginCountryCode"
ORIGIN_COUNTRY_NAME = "OriginCountryName"
CUSTOMS_COST_METHOD = "CustomsCostCorrectMethod"
PREFERENCES = "Preferencii"
PREFERENCE_TAX = "CustomsTax"
PREFERENCE_DUTY = "CustomsDuty"
PREFERENCE_RATE = "Rate"
SUPPLEMENTARY_QUANTITY = "SupplementaryGoodsQuantity"
GOODS_QUANTITY = "GoodsQuantity"
MEASURE_UNIT_NAME = "MeasureUnitQualifierName"
MEASURE_UNIT_CODE = "MeasureUnitQualifierCode"
GOODS_PACKAGING = "ESADGoodsPackaging"
PACKAGE_QUANTITY = "PakageQuantity"
PACKAGE_TYPE_CODE = "PakageTypeCode"
PACKING_INFORMATION = "PackingInformation"
PACKING_CODE = "PackingCode"
PACKING_QUANTITY = "PakingQuantity"
GOODS_PROCEDURE = "ESADCustomsProcedure"
MAIN_MODE_CODE = "MainCustomsModeCode"
PRECEDING_MODE_CODE = "PrecedingCustomsModeCode"
GOODS_TRANSFER_FEATURE = "GoodsTransferFeature"

CONSIGNMENT = "ESADout_CUConsigment"
CONTAINER_INDICATOR = "ContainerIndicator"
DISPATCH_COUNTRY_CODE = "DispatchCountryCode"
DISPATCH_COUNTRY_NAME = "DispatchCountryName"
DESTINATION_COUNTRY_CODE = "DestinationCountryCode"
DESTINATION_COUNTRY_NAME = "DestinationCountryName"
BORDER_OFFICE = "BorderCustomsOffice"
BORDER_OFFICE_CODE = "Code"
BORDER_OFFICE_NAME = "OfficeName"
BORDER_OFFICE_COUNTRY_CODE = "CustomsCountryCode"
DEPARTURE_TRANSPORT = "ESADout_CUDepartureArrivalTransport"
BORDER_TRANSPORT = "ESADout_CUBorderTransport"
TRANSPORT_MODE_CODE = "TransportModeCode"
TRANSPORT_MEANS_QUANTITY = "TransportMeansQuantity"
TRANSPORT_MEANS = "TransportMeans"
TRANSPORT_IDENTIFIER = "TransportIdentifier"
TRANSPORT_NATIONALITY_CODE = "TransportMeansNationalityCode"
CONTRACT_TERMS = "ESADout_CUMainContractTerms"
CONTRACT_CURRENCY_CODE = "ContractCurrencyCode"
TOTAL_INVOICE_AMOUNT = "TotalInvoiceAmount"
TRADE_COUNTRY_CODE = "TradeCountryCode"
DELIVERY_TERMS = "CUESADDeliveryTerms"
DELIVERY_TERMS_CODE = "DeliveryTermsStringCode"
DELIVERY_PLACE = "DeliveryPlace"

FILLER = "ESADout_CUFillingPerson"
FILLER_SURNAME = "PersonSurname"
FILLER_GIVEN_NAME = "PersonName"
FILLER_CONTACT = "Contact"
FILLER_PHONE = "Phone"
FILLER_EMAIL = "E_mail"

UNCONFIRMED_ELEMENT_NAMES = frozenset(
    {
        CONSIGNEE,
        RESPONSIBLE_PERSON,
        DECLARANT,
        GOODS_LOCATION,
        GOODS_LOCATION_INFORMATION_TYPE,
        GOODS_LOCATION_OFFICE_CODE,
        # GOODS_LOCATION_COUNTRY_CODE is deliberately absent: `CustomsCountryCode` is an
        # attested name in the border-office block, and only its reuse *here* is an
        # assumption — which flagging the goods-location container already covers.
        CUSTOMS_ZONE,
        CUSTOMS_ZONE_NUMBER,
        GOODS_ITEM,
        DEPARTURE_TRANSPORT,
        BORDER_TRANSPORT,
        TRANSPORT_NATIONALITY_CODE,
        CONTRACT_TERMS,
        FILLER,
        FILLER_SURNAME,
        FILLER_GIVEN_NAME,
        FILLER_CONTACT,
        FILLER_PHONE,
    }
)
"""Names the specification never states. See this module's docstring — a document
carrying any of these is not filable until a real accepted filing confirms them."""


# --- constants the contract fixes -----------------------------------------------------

PROCEDURE_IMPORT = "IM"
MODE_CODE_HOME_USE = "40"
PRECEDING_MODE_NONE = "00"
TRANSFER_FEATURE_NONE = "000"
SINGLE_SPECIFICATION = "1"
SINGLE_SHEET = "1"

NO_PREFERENCE = "OO"
"""Box 36, filed three times. Two ASCII letter O, byte-verified — **not** digit zero.

Dossier 03 §5.5: filing a preference the goods do not qualify for under-declares duty,
which is legally consequential; filing this marker merely over-declares and is corrected
on the portal. A duty preference is derivable from origin and is deliberately never
derived.
"""

DOMESTIC_COUNTRY_CODE = "AM"
DOMESTIC_COUNTRY_NAME = "ՀԱՅԱՍՏԱՆ"
"""The importer is Armenian by definition on an IM/40 import into Armenia, and so is the
destination. Both are constants of this product's jurisdiction, not document data."""

ABSENT_ORGANIZATION_NAME = "-"
"""The only placeholder the contract tolerates, and only in two places.

Dossier 03 §6: a `-` in any schema-typed leaf is exactly what the portal rejects, and
every generated file of the placeholder era failed on it. The two free-text organization
names below are the whole of the exception.
"""

PLACEHOLDER_PERMITTED_PATHS = frozenset(
    {
        f"{ROOT}/{CONSIGNOR}/{ORGANIZATION_NAME}",
        f"{ROOT}/{CONSIGNEE}/{ORGANIZATION_NAME}",
        f"{ROOT}/{RESPONSIBLE_PERSON}/{ORGANIZATION_NAME}",
        f"{ROOT}/{DECLARANT}/{ORGANIZATION_NAME}",
    }
)


# --- sequences ------------------------------------------------------------------------
#
# Container -> its children in the order the contract requires. Optionality does not
# relax order: a child may be absent, but the ones present must appear in this order.

SEQUENCES: dict[str, tuple[str, ...]] = {
    ROOT: (
        CUSTOMS_PROCEDURE,
        CUSTOMS_MODE_CODE,
        ORIGIN_COUNTRY_NAME_SHIPMENT,
        SPECIFICATION_NUMBER,
        SPECIFICATION_LIST_NUMBER,
        TOTAL_GOODS_NUMBER,
        TOTAL_PACKAGE_NUMBER,
        TOTAL_SHEET_NUMBER,
        CONSIGNOR,
        CONSIGNEE,
        RESPONSIBLE_PERSON,
        DECLARANT,
        GOODS_LOCATION,
        GOODS_ITEM,
        CONSIGNMENT,
        FILLER,
    ),
    CONSIGNOR: (ORGANIZATION_NAME, ADDRESS),
    CONSIGNEE: (ORGANIZATION_NAME, ORGANIZATION_FEATURES, ADDRESS),
    RESPONSIBLE_PERSON: (ORGANIZATION_NAME, ORGANIZATION_FEATURES, ADDRESS),
    DECLARANT: (ORGANIZATION_NAME, ORGANIZATION_FEATURES, ADDRESS),
    ORGANIZATION_FEATURES: (TAX_CODE,),
    ADDRESS: (COUNTRY_CODE, COUNTRY_NAME, STREET_HOUSE),
    GOODS_LOCATION: (
        GOODS_LOCATION_INFORMATION_TYPE,
        GOODS_LOCATION_OFFICE_CODE,
        GOODS_LOCATION_COUNTRY_CODE,
        CUSTOMS_ZONE,
    ),
    CUSTOMS_ZONE: (CUSTOMS_ZONE_NUMBER,),
    GOODS_ITEM: (
        GOODS_NUMERIC,
        GOODS_DESCRIPTION,
        GROSS_WEIGHT,
        NET_WEIGHT,
        INVOICED_COST,
        COMMODITY_CODE,
        ADDITIONAL_SIGN,
        ORIGIN_COUNTRY_CODE,
        ORIGIN_COUNTRY_NAME,
        CUSTOMS_COST_METHOD,
        PREFERENCES,
        SUPPLEMENTARY_QUANTITY,
        GOODS_PACKAGING,
        GOODS_PROCEDURE,
    ),
    PREFERENCES: (PREFERENCE_TAX, PREFERENCE_DUTY, PREFERENCE_RATE),
    SUPPLEMENTARY_QUANTITY: (GOODS_QUANTITY, MEASURE_UNIT_NAME, MEASURE_UNIT_CODE),
    GOODS_PACKAGING: (PACKAGE_QUANTITY, PACKAGE_TYPE_CODE, PACKING_INFORMATION),
    PACKING_INFORMATION: (PACKING_CODE, PACKING_QUANTITY),
    GOODS_PROCEDURE: (MAIN_MODE_CODE, PRECEDING_MODE_CODE, GOODS_TRANSFER_FEATURE),
    CONSIGNMENT: (
        CONTAINER_INDICATOR,
        DISPATCH_COUNTRY_CODE,
        DISPATCH_COUNTRY_NAME,
        DESTINATION_COUNTRY_CODE,
        DESTINATION_COUNTRY_NAME,
        BORDER_OFFICE,
        DEPARTURE_TRANSPORT,
        BORDER_TRANSPORT,
        CONTRACT_TERMS,
    ),
    BORDER_OFFICE: (BORDER_OFFICE_CODE, BORDER_OFFICE_NAME, BORDER_OFFICE_COUNTRY_CODE),
    DEPARTURE_TRANSPORT: (TRANSPORT_MODE_CODE, TRANSPORT_MEANS_QUANTITY, TRANSPORT_MEANS),
    BORDER_TRANSPORT: (TRANSPORT_MODE_CODE, TRANSPORT_MEANS_QUANTITY, TRANSPORT_MEANS),
    TRANSPORT_MEANS: (TRANSPORT_IDENTIFIER, TRANSPORT_NATIONALITY_CODE),
    CONTRACT_TERMS: (
        CONTRACT_CURRENCY_CODE,
        TOTAL_INVOICE_AMOUNT,
        TRADE_COUNTRY_CODE,
        DELIVERY_TERMS,
    ),
    DELIVERY_TERMS: (DELIVERY_TERMS_CODE, DELIVERY_PLACE),
    FILLER: (FILLER_SURNAME, FILLER_GIVEN_NAME, FILLER_CONTACT),
    FILLER_CONTACT: (FILLER_PHONE, FILLER_EMAIL),
}

UNCONFIRMED_SEQUENCES = frozenset(
    {
        ROOT,
        GOODS_LOCATION,
        CUSTOMS_ZONE,
        CONSIGNMENT,
        CONTRACT_TERMS,
        DEPARTURE_TRANSPORT,
        BORDER_TRANSPORT,
        TRANSPORT_MEANS,
        FILLER,
        FILLER_CONTACT,
        CONSIGNEE,
        RESPONSIBLE_PERSON,
        DECLARANT,
        ADDRESS,
    }
)
"""Sequences read off the specification's own section and table order rather than stated
as an order. The goods item, its packaging, its preferences and its procedure are the
ones dossier 03 §5.5 states outright, and those are not listed here."""


# --- code and name pairs --------------------------------------------------------------

CODE_NAME_PAIRS: tuple[tuple[str, str, str], ...] = (
    (GOODS_ITEM, ORIGIN_COUNTRY_CODE, ORIGIN_COUNTRY_NAME),
    (CONSIGNMENT, DISPATCH_COUNTRY_CODE, DISPATCH_COUNTRY_NAME),
    (CONSIGNMENT, DESTINATION_COUNTRY_CODE, DESTINATION_COUNTRY_NAME),
    (ADDRESS, COUNTRY_CODE, COUNTRY_NAME),
    (SUPPLEMENTARY_QUANTITY, MEASURE_UNIT_CODE, MEASURE_UNIT_NAME),
    (BORDER_OFFICE, BORDER_OFFICE_CODE, BORDER_OFFICE_NAME),
)
"""Parent, code element, name element. Emitted together or not at all: the portal keys on
the code and renders the name from it, so a name without its code is dropped on import
with no message at all.

The parent is part of each entry because `OriginCountryName` is half of a pair inside a
goods item and a lone element at shipment level, where box 16 has no code half. Keyed by
name alone, the shipment's origin country would be reported as a broken pair on every
document ever written.
"""


# --- leaf facets ----------------------------------------------------------------------


class FacetKind(StrEnum):
    """The leaf types that are stable across schema versions and worth checking.

    Dossier 11 §6: the vendored schema set is the wrong version and produces false errors
    on genuinely valid files, so it transfers as a facet dictionary and never as an
    acceptance oracle. These five are the layer its own provenance note calls stable.
    """

    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    TEXT = "text"
    CODE = "code"


class Facet(BaseModel):
    """What one leaf's value has to look like."""

    model_config = ConfigDict(frozen=True)

    kind: FacetKind
    max_length: int | None = None
    """A hard cap. One over-long value rejects the whole file, with no element named."""

    advisory_max_length: int | None = None
    """A cap the schema states and real accepted filings exceed. Reported, never failed."""

    pattern: str | None = None
    fixed: str | None = None
    allowed: tuple[str, ...] | None = None
    digits: int | None = None
    """Exact digit count for a fixed-width token, checked as characters so that
    zero-padding is preserved rather than normalised away."""


_TEXT = Facet(kind=FacetKind.TEXT)
_DECIMAL = Facet(kind=FacetKind.DECIMAL)
_INTEGER = Facet(kind=FacetKind.INTEGER)
_ALPHA2_COUNTRY = Facet(kind=FacetKind.CODE, pattern=r"^[A-Z]{2}$")

FACETS: dict[tuple[str | None, str], Facet] = {
    # Header and shipment level.
    (ROOT, CUSTOMS_PROCEDURE): Facet(kind=FacetKind.CODE, fixed=PROCEDURE_IMPORT),
    (ROOT, CUSTOMS_MODE_CODE): Facet(kind=FacetKind.CODE, fixed=MODE_CODE_HOME_USE),
    (ROOT, ORIGIN_COUNTRY_NAME_SHIPMENT): _TEXT,
    (ROOT, SPECIFICATION_NUMBER): Facet(kind=FacetKind.INTEGER, fixed=SINGLE_SPECIFICATION),
    (ROOT, SPECIFICATION_LIST_NUMBER): Facet(
        kind=FacetKind.INTEGER, fixed=SINGLE_SPECIFICATION
    ),
    (ROOT, TOTAL_GOODS_NUMBER): _INTEGER,
    (ROOT, TOTAL_PACKAGE_NUMBER): _DECIMAL,
    (ROOT, TOTAL_SHEET_NUMBER): Facet(kind=FacetKind.INTEGER, fixed=SINGLE_SHEET),
    # Parties.
    (None, ORGANIZATION_NAME): Facet(kind=FacetKind.TEXT, advisory_max_length=150),
    (ORGANIZATION_FEATURES, TAX_CODE): Facet(
        kind=FacetKind.CODE, pattern=r"^[0-9]+$", advisory_max_length=8
    ),
    (ADDRESS, COUNTRY_CODE): _ALPHA2_COUNTRY,
    (ADDRESS, COUNTRY_NAME): _TEXT,
    (ADDRESS, STREET_HOUSE): Facet(kind=FacetKind.TEXT, max_length=50),
    # Goods location.
    (GOODS_LOCATION, GOODS_LOCATION_INFORMATION_TYPE): Facet(kind=FacetKind.CODE),
    (GOODS_LOCATION, GOODS_LOCATION_OFFICE_CODE): Facet(kind=FacetKind.CODE, digits=8),
    (GOODS_LOCATION, GOODS_LOCATION_COUNTRY_CODE): _ALPHA2_COUNTRY,
    (CUSTOMS_ZONE, CUSTOMS_ZONE_NUMBER): Facet(kind=FacetKind.CODE),
    # Goods item.
    (GOODS_ITEM, GOODS_NUMERIC): _INTEGER,
    (GOODS_ITEM, GOODS_DESCRIPTION): Facet(kind=FacetKind.TEXT, advisory_max_length=250),
    (GOODS_ITEM, GROSS_WEIGHT): _DECIMAL,
    (GOODS_ITEM, NET_WEIGHT): _DECIMAL,
    (GOODS_ITEM, INVOICED_COST): _DECIMAL,
    (GOODS_ITEM, COMMODITY_CODE): Facet(kind=FacetKind.CODE, digits=11),
    (GOODS_ITEM, ORIGIN_COUNTRY_CODE): _ALPHA2_COUNTRY,
    (GOODS_ITEM, ORIGIN_COUNTRY_NAME): _TEXT,
    (GOODS_ITEM, CUSTOMS_COST_METHOD): Facet(
        kind=FacetKind.CODE, allowed=("0", "1", "2", "3", "4", "5", "6")
    ),
    (PREFERENCES, PREFERENCE_TAX): Facet(kind=FacetKind.CODE, fixed=NO_PREFERENCE),
    (PREFERENCES, PREFERENCE_DUTY): Facet(kind=FacetKind.CODE, fixed=NO_PREFERENCE),
    # `Rate` is a decimal tariff rate inside the payment block and a two-character
    # alphabetic code here. Dossier 07 §2.5 records the collision: any consumer must
    # resolve this element by parent, never by name — which is why this table is keyed
    # by parent in the first place.
    (PREFERENCES, PREFERENCE_RATE): Facet(kind=FacetKind.CODE, fixed=NO_PREFERENCE),
    (SUPPLEMENTARY_QUANTITY, GOODS_QUANTITY): _DECIMAL,
    (SUPPLEMENTARY_QUANTITY, MEASURE_UNIT_NAME): _TEXT,
    (SUPPLEMENTARY_QUANTITY, MEASURE_UNIT_CODE): Facet(kind=FacetKind.CODE, digits=3),
    (GOODS_PACKAGING, PACKAGE_QUANTITY): _DECIMAL,
    (GOODS_PACKAGING, PACKAGE_TYPE_CODE): Facet(
        kind=FacetKind.CODE, allowed=("0", "1", "2")
    ),
    (PACKING_INFORMATION, PACKING_CODE): Facet(kind=FacetKind.CODE),
    (PACKING_INFORMATION, PACKING_QUANTITY): _DECIMAL,
    (GOODS_PROCEDURE, MAIN_MODE_CODE): Facet(
        kind=FacetKind.CODE, fixed=MODE_CODE_HOME_USE
    ),
    (GOODS_PROCEDURE, PRECEDING_MODE_CODE): Facet(
        kind=FacetKind.CODE, fixed=PRECEDING_MODE_NONE
    ),
    (GOODS_PROCEDURE, GOODS_TRANSFER_FEATURE): Facet(
        kind=FacetKind.CODE, fixed=TRANSFER_FEATURE_NONE
    ),
    # Consignment, transport, contract terms.
    (CONSIGNMENT, CONTAINER_INDICATOR): Facet(
        kind=FacetKind.CODE, allowed=("true", "false")
    ),
    (CONSIGNMENT, DISPATCH_COUNTRY_CODE): _ALPHA2_COUNTRY,
    (CONSIGNMENT, DISPATCH_COUNTRY_NAME): _TEXT,
    (CONSIGNMENT, DESTINATION_COUNTRY_CODE): Facet(
        kind=FacetKind.CODE, fixed=DOMESTIC_COUNTRY_CODE
    ),
    (CONSIGNMENT, DESTINATION_COUNTRY_NAME): Facet(
        kind=FacetKind.TEXT, fixed=DOMESTIC_COUNTRY_NAME
    ),
    (BORDER_OFFICE, BORDER_OFFICE_CODE): Facet(
        kind=FacetKind.CODE, pattern=r"^([0-9]{5}|[0-9]{8})$"
    ),
    (BORDER_OFFICE, BORDER_OFFICE_NAME): Facet(kind=FacetKind.TEXT, max_length=50),
    (BORDER_OFFICE, BORDER_OFFICE_COUNTRY_CODE): _ALPHA2_COUNTRY,
    (None, TRANSPORT_MODE_CODE): Facet(kind=FacetKind.CODE, pattern=r"^[0-9]{2}$"),
    (None, TRANSPORT_MEANS_QUANTITY): _INTEGER,
    (TRANSPORT_MEANS, TRANSPORT_IDENTIFIER): _TEXT,
    (TRANSPORT_MEANS, TRANSPORT_NATIONALITY_CODE): _ALPHA2_COUNTRY,
    (CONTRACT_TERMS, CONTRACT_CURRENCY_CODE): Facet(
        kind=FacetKind.CODE, pattern=r"^[A-Z]{3}$"
    ),
    (CONTRACT_TERMS, TOTAL_INVOICE_AMOUNT): _DECIMAL,
    (CONTRACT_TERMS, TRADE_COUNTRY_CODE): _ALPHA2_COUNTRY,
    (DELIVERY_TERMS, DELIVERY_TERMS_CODE): _TEXT,
    (DELIVERY_TERMS, DELIVERY_PLACE): Facet(kind=FacetKind.TEXT, max_length=50),
    # Filler.
    (FILLER, FILLER_SURNAME): _TEXT,
    (FILLER, FILLER_GIVEN_NAME): _TEXT,
    (FILLER_CONTACT, FILLER_PHONE): _TEXT,
    (FILLER_CONTACT, FILLER_EMAIL): _TEXT,
}


def facet_for(parent_name: str | None, local_name: str) -> Facet | None:
    """The facet for one leaf, resolved by parent first.

    Resolution order is deliberate. `Rate` means two different things in two different
    parents and a name-keyed lookup gets one of them wrong, so the parent-qualified entry
    always wins and the bare-name entry is only a fallback for leaves that genuinely mean
    the same thing wherever they appear.
    """
    keyed = FACETS.get((parent_name, local_name))
    if keyed is not None:
        return keyed
    return FACETS.get((None, local_name))


# --- what the contract knows and this product never writes ----------------------------

NEVER_EMITTED = frozenset(
    {
        "ElectronicDocumentSign",
        "RegNumberDoc",
        "ExecutionDate",
        "ContractCurrencyRate",
        "TotalCustCost",
        "CustCostCurrencyCode",
        ADDITIONAL_SIGN,
        "customsCostBeforeKdt",
    }
)
"""Elements a reader must expect and a writer must never produce.

The registration trio is assigned by the portal on registration. The currency rate the
portal fills. The additional-sign marker has no recorded trigger. `customsCostBeforeKdt`
is an un-namespaced, camelCase post-filing correction artifact that the portal's own
exports contain — tolerated on read, never written.

`TotalCustCost` and `CustCostCurrencyCode` are the uncomfortable pair: nominally
optional, present in all 311 accepted filings, and never emitted. Whether their absence
is tolerated is unproven, which is why `conformance.check` reports it every time rather
than letting it fade into the background.
"""

CONTRACT_CONSTANTS = frozenset(
    {
        CUSTOMS_PROCEDURE,
        CUSTOMS_MODE_CODE,
        SPECIFICATION_NUMBER,
        SPECIFICATION_LIST_NUMBER,
        TOTAL_SHEET_NUMBER,
        DESTINATION_COUNTRY_CODE,
        DESTINATION_COUNTRY_NAME,
        PREFERENCES,
        PREFERENCE_TAX,
        PREFERENCE_DUTY,
        PREFERENCE_RATE,
        GOODS_PROCEDURE,
        MAIN_MODE_CODE,
        PRECEDING_MODE_CODE,
        GOODS_TRANSFER_FEATURE,
    }
)
"""Elements whose value the domain never chooses. The write direction supplies them from
this module; the read direction has nothing to map them to, which is not a loss."""

READ_ONLY_ELEMENTS = frozenset(
    {
        "ContainerIdentificaror",
        "MeasureUnitCode",
        "PresentedDocument",
        "PaymentCalculation",
    }
)
"""Names that appear in filed declarations and never in ours. Kept so the read direction
recognises them as known rather than reporting them as unmapped noise."""

MAX_NESTING_DEPTH = 5
MAX_FILE_BYTES = 4 * 1024 * 1024
