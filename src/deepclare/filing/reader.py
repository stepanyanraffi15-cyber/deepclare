"""The read direction: a filed declaration becomes domain records again.

One module owns both directions because the same contract knowledge is needed to write a
filing and to read one back, and splitting it guarantees the two copies drift apart.

Four rules come from what real filed declarations actually contain, and each of them is
the difference between reading a document and reading only our own output:

* **Locate by local element name, never by prefix.** Prefixes are per-document and the
  wider corpus carries the address block under a different prefix from everywhere else. A
  name-plus-namespace-keyed consumer silently drops those addresses.
* **Resolve by parent.** `Rate` is a decimal tariff rate in one block and a two-letter
  code in another.
* **Tolerate what we never write.** Presented-document blocks, payment calculations, an
  additional commodity code, and an un-namespaced camelCase post-filing correction
  artifact that the portal's own exports contain. All of them are read past, none is
  written back.
* **Nothing is dropped in silence.** Every element that did not become a domain value
  comes back in `unread`, with the reason. That includes the repetition-by-renaming
  idiom: a second net weight is filed as a numerically-suffixed sibling rather than a
  repeated element, and a name-keyed consumer misses it entirely.

Blocks are located by the names `contract` takes from the evidence base, which settled
what an earlier revision of this reader had to work around. It identified a goods block
as "the child with a `GoodsNumeric` in it" because the specification named the leaves and
not their containers; 71 ground-truth declarations name every container, so the reader
asks for the container it wants and reports anything it did not consume.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict

from deepclare.domain.declaration import (
    CodedValue,
    Consignment,
    Declaration,
    DeliveryTerms,
    FillerPerson,
    GoodsItem,
    GoodsLocation,
    Organization,
    Packaging,
    PostalAddress,
    SupplementaryQuantity,
    TransportBlock,
)
from deepclare.domain.documents import DocumentRole
from deepclare.domain.provenance import Confidence, Provenance, Traced, ValueOrigin
from deepclare.filing import contract as c
from deepclare.filing.errors import MalformedFiledDocument

_RENAMED_REPEAT = re.compile(r"^(?P<base>[A-Za-z_]+)(?P<index>[0-9]+)$")


class UnreadElement(BaseModel):
    """Something in the file that did not become a domain value."""

    model_config = ConfigDict(frozen=True)

    path: str
    value: str | None
    reason: str
    known: bool
    """True when the contract is on record as carrying this element and this product on
    record as never producing it — expected, not a surprise."""


class ParsedFiling(BaseModel):
    model_config = ConfigDict(frozen=True)

    declaration: Declaration
    unread: tuple[UnreadElement, ...]
    census: dict[str, int]
    """Every local element name in the file and how many times it occurs."""


def read_declaration(xml: str | bytes, filing_id: str) -> ParsedFiling:
    """Parse one filed declaration. `filing_id` identifies the source in provenance."""
    text = xml.decode("utf-8") if isinstance(xml, bytes) else xml
    if "<!DOCTYPE" in text:
        raise MalformedFiledDocument(
            "the document declares a DTD; filed declarations carry none and entity "
            "expansion is not a risk worth taking on a file from outside"
        )
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as error:
        raise MalformedFiledDocument(f"not well-formed XML: {error}") from error
    if _local(root.tag) != c.ROOT:
        raise MalformedFiledDocument(
            f"root element is {_local(root.tag)!r}, not {c.ROOT!r}"
        )
    return _FilingReader(root, filing_id).read()


def _local(tag: str) -> str:
    """The element name with any namespace stripped, prefixed or not."""
    return tag.rsplit("}", 1)[-1]


class _FilingReader:
    """One pass over one document, tracking what it consumed so nothing is lost."""

    def __init__(self, root: ElementTree.Element, filing_id: str) -> None:
        self._root = root
        self._filing_id = filing_id
        self._consumed: set[int] = set()
        self._malformed: list[UnreadElement] = []
        self._paths: dict[int, str] = {}
        self._record_paths(root, c.ROOT)

    # --- plumbing ---------------------------------------------------------------------

    def _record_paths(self, node: ElementTree.Element, path: str) -> None:
        self._paths[id(node)] = path
        for child in node:
            self._record_paths(child, f"{path}/{_local(child.tag)}")

    def _child(self, parent: ElementTree.Element, name: str) -> ElementTree.Element | None:
        for child in parent:
            if _local(child.tag) == name:
                return child
        return None

    def _children(
        self, parent: ElementTree.Element, name: str
    ) -> list[ElementTree.Element]:
        return [child for child in parent if _local(child.tag) == name]

    def _take(self, node: ElementTree.Element, reason: str) -> None:
        """Consume a whole sub-tree that carries nothing new, saying why once."""
        self._malformed.append(
            UnreadElement(
                path=self._paths[id(node)],
                value=None,
                reason=reason,
                known=True,
            )
        )
        for element in node.iter():
            self._consumed.add(id(element))

    def _text(self, parent: ElementTree.Element, name: str) -> str | None:
        child = self._child(parent, name)
        if child is None:
            return None
        self._consumed.add(id(child))
        text = (child.text or "").strip()
        return text or None

    def _provenance(self) -> Provenance:
        return Provenance(
            origin=ValueOrigin.EXTRACTED,
            source_document_id=self._filing_id,
            source_document_role=DocumentRole.PRIOR_DECLARATION.value,
        )

    def _confidence(self) -> Confidence:
        # The value was read losslessly out of a machine-written document, so there is no
        # transcription doubt. Derivation and validity stay unassessed: nothing here knows
        # whether the filing was accepted.
        return Confidence(extraction=1.0)

    def _string(self, parent: ElementTree.Element, name: str) -> Traced[str] | None:
        text = self._text(parent, name)
        if text is None:
            return None
        return Traced[str](
            value=text, provenance=self._provenance(), confidence=self._confidence()
        )

    def _decimal(self, parent: ElementTree.Element, name: str) -> Traced[Decimal] | None:
        text = self._text(parent, name)
        if text is None:
            return None
        try:
            value = Decimal(text)
        except InvalidOperation:
            self._unreadable(parent, name, text, "not a decimal number")
            return None
        return Traced[Decimal](
            value=value, provenance=self._provenance(), confidence=self._confidence()
        )

    def _integer(self, parent: ElementTree.Element, name: str) -> Traced[int] | None:
        text = self._text(parent, name)
        if text is None:
            return None
        if not text.isdigit():
            self._unreadable(parent, name, text, "not an integer")
            return None
        return Traced[int](
            value=int(text), provenance=self._provenance(), confidence=self._confidence()
        )

    def _boolean(self, parent: ElementTree.Element, name: str) -> Traced[bool] | None:
        text = self._text(parent, name)
        if text is None:
            return None
        lowered = text.lower()
        if lowered not in {"true", "false"}:
            self._unreadable(parent, name, text, "not true or false")
            return None
        return Traced[bool](
            value=lowered == "true",
            provenance=self._provenance(),
            confidence=self._confidence(),
        )

    def _pair(
        self, parent: ElementTree.Element, code_name: str, name_name: str
    ) -> CodedValue | None:
        """A code and its name. Half a pair is not a value — the portal drops it anyway."""
        code = self._string(parent, code_name)
        name = self._string(parent, name_name)
        if code is None or name is None:
            return None
        return CodedValue(code=code, name=name)

    def _unreadable(
        self, parent: ElementTree.Element, name: str, value: str, reason: str
    ) -> None:
        child = self._child(parent, name)
        path = self._paths.get(id(child), f"{self._paths[id(parent)]}/{name}")
        self._malformed.append(
            UnreadElement(path=path, value=value, reason=reason, known=False)
        )

    # --- the pass ---------------------------------------------------------------------

    def read(self) -> ParsedFiling:
        self._consumed.add(id(self._root))

        shipment = self._child(self._root, c.SHIPMENT)
        if shipment is None:
            raise MalformedFiledDocument(
                f"the document carries no {c.SHIPMENT}; everything but the two header "
                "codes and the filler sits inside it"
            )
        self._consumed.add(id(shipment))

        total_goods = self._integer(shipment, c.TOTAL_GOODS_NUMBER)
        if total_goods is None:
            raise MalformedFiledDocument(
                f"the document carries no {c.TOTAL_GOODS_NUMBER}"
            )

        # Boxes 8, 9 and 14 are one company written three times, byte-identical in every
        # filing in the evidence base. Reading the first is reading all three.
        importer_block = self._child(shipment, c.CONSIGNEE)
        for role in (c.RESPONSIBLE_PERSON, c.DECLARANT):
            duplicate = self._child(shipment, role)
            if duplicate is not None:
                self._take(
                    duplicate,
                    "the importer is filed identically in boxes 8, 9 and 14; read once",
                )

        consignor_block = self._child(shipment, c.CONSIGNOR)

        declaration = Declaration(
            origin_country_name=self._string(shipment, c.ORIGIN_COUNTRY_NAME_SHIPMENT),
            total_goods_number=total_goods,
            total_package_number=self._decimal(shipment, c.TOTAL_PACKAGE_NUMBER),
            consignor=(
                self._organization(consignor_block) if consignor_block is not None else None
            ),
            importer=(
                self._organization(importer_block) if importer_block is not None else None
            ),
            goods_location=self._goods_location(shipment),
            consignment=self._consignment(shipment),
            goods=tuple(
                self._goods_item(block) for block in self._children(shipment, c.GOODS_ITEM)
            ),
            filler=self._filler(),
        )

        # The header constants carry no domain choice and are checked rather than read.
        for parent, name in (
            (self._root, c.CUSTOMS_PROCEDURE),
            (self._root, c.CUSTOMS_MODE_CODE),
            (shipment, c.SPECIFICATION_NUMBER),
            (shipment, c.SPECIFICATION_LIST_NUMBER),
            (shipment, c.TOTAL_SHEET_NUMBER),
        ):
            self._text(parent, name)

        return ParsedFiling(
            declaration=declaration,
            unread=tuple(self._malformed) + self._leftovers(),
            census=self._census(),
        )

    def _organization(self, block: ElementTree.Element) -> Organization:
        self._consumed.add(id(block))
        name = self._string(block, c.ORGANIZATION_NAME)
        if name is not None and name.value == c.ABSENT_ORGANIZATION_NAME:
            name = None
        features = self._child(block, c.ORGANIZATION_FEATURES)
        tax_code = None
        if features is not None:
            self._consumed.add(id(features))
            tax_code = self._string(features, c.TAX_CODE)
        address_block = self._child(block, c.ADDRESS)
        address = None
        if address_block is not None:
            self._consumed.add(id(address_block))
            country = self._pair(address_block, c.COUNTRY_CODE, c.COUNTRY_NAME)
            street = self._string(address_block, c.STREET_HOUSE)
            # An address block with nothing in it is not an address. Two of the 71 ground
            # truths carry one; reading it as a value would make the write direction
            # reproduce an empty container the contract has no rule for.
            if country is not None or street is not None:
                address = PostalAddress(country=country, street_house=street)
        return Organization(name=name, tax_code=tax_code, address=address)

    def _goods_location(self, shipment: ElementTree.Element) -> GoodsLocation | None:
        block = self._child(shipment, c.GOODS_LOCATION)
        if block is None:
            return None
        self._consumed.add(id(block))
        information_type = self._string(block, c.GOODS_LOCATION_INFORMATION_TYPE)
        office = self._string(block, c.GOODS_LOCATION_OFFICE)
        country = self._string(block, c.GOODS_LOCATION_COUNTRY_CODE)
        if information_type is None or office is None or country is None:
            return None
        return GoodsLocation(
            information_type_code=information_type,
            customs_office_code=office,
            country_code=country,
        )

    def _goods_item(self, block: ElementTree.Element) -> GoodsItem:
        self._consumed.add(id(block))
        number = self._integer(block, c.GOODS_NUMERIC)
        if number is None:
            raise MalformedFiledDocument("a goods block carries no item number")
        description = self._string(block, c.GOODS_DESCRIPTION)
        if description is None:
            raise MalformedFiledDocument(
                f"goods item {number.value} carries no {c.GOODS_DESCRIPTION}"
            )
        quantity_block = self._child(block, c.SUPPLEMENTARY_QUANTITY)
        quantity = None
        if quantity_block is not None:
            self._consumed.add(id(quantity_block))
            figure = self._decimal(quantity_block, c.GOODS_QUANTITY)
            unit_name = self._string(quantity_block, c.MEASURE_UNIT_NAME)
            # A filing may carry the unit code alone; the code is the portal's key and
            # the name is rendered from it, so the code decides whether this is a value.
            unit_code = self._string(quantity_block, c.MEASURE_UNIT_CODE)
            if figure is not None and unit_code is not None and unit_name is not None:
                quantity = SupplementaryQuantity(
                    quantity=figure, unit_code=unit_code, unit_name=unit_name
                )
        return GoodsItem(
            item_number=number.value,
            line_id=str(number.value),
            description=description,
            gross_weight=self._decimal(block, c.GROSS_WEIGHT),
            net_weight=self._decimal(block, c.NET_WEIGHT),
            invoiced_cost=self._decimal(block, c.INVOICED_COST),
            commodity_code=self._string(block, c.COMMODITY_CODE),
            origin_country=self._pair(block, c.ORIGIN_COUNTRY_CODE, c.ORIGIN_COUNTRY_NAME),
            customs_cost_method=self._string(block, c.CUSTOMS_COST_METHOD),
            supplementary_quantity=quantity,
            packaging=self._packaging(block),
        )

    def _packaging(self, block: ElementTree.Element) -> Packaging:
        packaging_block = self._child(block, c.GOODS_PACKAGING)
        if packaging_block is None:
            return Packaging()
        self._consumed.add(id(packaging_block))
        packing_block = self._child(packaging_block, c.PACKING_INFORMATION)
        packing_code = None
        packing_quantity = None
        if packing_block is not None:
            self._consumed.add(id(packing_block))
            packing_code = self._string(packing_block, c.PACKING_CODE)
            packing_quantity = self._decimal(packing_block, c.PACKING_QUANTITY)
        return Packaging(
            package_count=self._decimal(packaging_block, c.PACKAGE_QUANTITY),
            package_type_code=self._string(packaging_block, c.PACKAGE_TYPE_CODE),
            packing_code=packing_code,
            packing_quantity=packing_quantity,
        )

    def _consignment(self, shipment: ElementTree.Element) -> Consignment:
        """Box 19 and the two transport blocks, plus the contract terms that sit beside
        them rather than inside them. One domain record spans both containers."""
        block = self._child(shipment, c.CONSIGNMENT)
        terms_block = self._child(shipment, c.CONTRACT_TERMS)
        if block is None and terms_block is None:
            return Consignment()
        indicator = None
        departure = None
        border = None
        if block is not None:
            self._consumed.add(id(block))
            indicator = self._boolean(block, c.CONTAINER_INDICATOR)
            departure = self._transport(block, c.DEPARTURE_TRANSPORT)
            border = self._transport(block, c.BORDER_TRANSPORT)
        if terms_block is None:
            return Consignment(
                container_indicator=indicator,
                departure_transport=departure,
                border_transport=border,
            )
        self._consumed.add(id(terms_block))
        return Consignment(
            container_indicator=indicator,
            departure_transport=departure,
            border_transport=border,
            currency_code=self._string(terms_block, c.CONTRACT_CURRENCY_CODE),
            total_invoice_amount=self._decimal(terms_block, c.TOTAL_INVOICE_AMOUNT),
            trade_country_code=self._string(terms_block, c.TRADE_COUNTRY_CODE),
            delivery_terms=self._delivery_terms(terms_block),
        )

    def _transport(
        self, block: ElementTree.Element, name: str
    ) -> TransportBlock | None:
        leg = self._child(block, name)
        if leg is None:
            return None
        self._consumed.add(id(leg))
        mode = self._string(leg, c.TRANSPORT_MODE_CODE)
        if mode is None:
            return None
        return TransportBlock(mode_code=mode)

    def _delivery_terms(self, block: ElementTree.Element) -> DeliveryTerms | None:
        terms = self._child(block, c.DELIVERY_TERMS)
        if terms is None:
            return None
        self._consumed.add(id(terms))
        code = self._string(terms, c.DELIVERY_TERMS_CODE)
        if code is None:
            return None
        return DeliveryTerms(terms_code=code)

    def _filler(self) -> FillerPerson | None:
        """Box 54 sits at root level, outside the shipment."""
        block = self._child(self._root, c.FILLER)
        if block is None:
            return None
        self._consumed.add(id(block))
        surname = self._string(block, c.FILLER_SURNAME)
        given_name = self._string(block, c.FILLER_GIVEN_NAME)
        if surname is None or given_name is None:
            return None
        return FillerPerson(surname=surname, given_name=given_name)

    # --- accounting -------------------------------------------------------------------

    def _leftovers(self) -> tuple[UnreadElement, ...]:
        """Everything the pass did not consume, with why it is unsurprising when it is."""
        unread: list[UnreadElement] = []
        for node in self._root.iter():
            if id(node) in self._consumed:
                continue
            name = _local(node.tag)
            text = (node.text or "").strip() or None
            unread.append(
                UnreadElement(
                    path=self._paths.get(id(node), name),
                    value=text,
                    reason=self._reason(name),
                    known=name in c.NEVER_EMITTED
                    or name in c.READ_ONLY_ELEMENTS
                    or name in c.CONTRACT_CONSTANTS,
                )
            )
        return tuple(unread)

    def _reason(self, name: str) -> str:
        if name in c.CONTRACT_CONSTANTS:
            return "a constant of the contract; the domain never varies it"
        if name in c.NEVER_EMITTED:
            return "the contract carries it; this product never writes it"
        if name in c.READ_ONLY_ELEMENTS:
            return "appears in filed declarations and has no domain concept here"
        repeat = _RENAMED_REPEAT.match(name)
        if repeat is not None:
            return (
                f"repetition by renaming: a further {repeat['base']} filed as a "
                f"numerically-suffixed sibling, which a name-keyed consumer misses"
            )
        return "no domain concept maps to this element"

    def _census(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self._root.iter():
            name = _local(node.tag)
            counts[name] = counts.get(name, 0) + 1
        return counts
