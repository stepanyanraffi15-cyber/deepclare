"""The read direction: a filed declaration becomes domain records again.

One module owns both directions because the same contract knowledge is needed to write a
filing and to read one back, and splitting it guarantees the two copies drift apart.

Four rules come from what real filed declarations actually contain, and each of them is
the difference between reading a document and reading only our own output:

* **Locate by local element name, never by prefix.** Prefixes are per-document and two
  filed files carry the address block under a different prefix from everywhere else. A
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

Containers are identified by **what they contain**, not by what they are called. The
specification names every leaf of the filed format and only some of its containers, so a
name-keyed reader could read nothing but this repository's own output. Identifying a
goods block as "the child that has a `GoodsNumeric` in it" reads a real accepted filing,
which is the one piece of evidence that would confirm the names `contract` has to guess —
`ParsedFiling.census` is there to be read straight off such a file.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict

from deepclare.domain.declaration import (
    BorderOffice,
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
    TransportMeansRecord,
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
    """Every element name in the file and how many times it occurs. Reading it off a real
    accepted filing is how the container names this adapter has to guess get settled."""


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

    def _has(self, parent: ElementTree.Element, name: str) -> bool:
        """A node with no children is falsey in ElementTree, so presence is asked for
        explicitly everywhere rather than by truth-testing the node."""
        return self._child(parent, name) is not None

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

        total_goods = self._integer(self._root, c.TOTAL_GOODS_NUMBER)
        if total_goods is None:
            raise MalformedFiledDocument(
                f"the document carries no {c.TOTAL_GOODS_NUMBER}"
            )

        parties = [
            child for child in self._root if self._has(child, c.ORGANIZATION_NAME)
        ]
        importers = [p for p in parties if self._descendant(p, c.TAX_CODE) is not None]
        consignors = [p for p in parties if p not in importers]
        # Boxes 8, 9 and 14 are one company written three times, byte-identical in every
        # filing. Reading the first is reading all three.
        for duplicate in importers[1:]:
            self._take(
                duplicate,
                "the importer is filed identically in boxes 8, 9 and 14; read once",
            )
        for duplicate in consignors[1:]:
            self._take(duplicate, "a second consignor block; the declaration carries one")

        declaration = Declaration(
            origin_country_name=self._string(self._root, c.ORIGIN_COUNTRY_NAME_SHIPMENT),
            total_goods_number=total_goods,
            total_package_number=self._decimal(self._root, c.TOTAL_PACKAGE_NUMBER),
            consignor=self._organization(consignors[0]) if consignors else None,
            importer=self._organization(importers[0]) if importers else None,
            goods_location=self._goods_location(),
            consignment=self._consignment(),
            goods=tuple(self._goods_item(block) for block in self._goods_blocks()),
            filler=self._filler(),
        )

        # The header constants carry no domain choice and are checked rather than read.
        for name in (
            c.CUSTOMS_PROCEDURE,
            c.CUSTOMS_MODE_CODE,
            c.SPECIFICATION_NUMBER,
            c.SPECIFICATION_LIST_NUMBER,
            c.TOTAL_SHEET_NUMBER,
        ):
            self._text(self._root, name)

        return ParsedFiling(
            declaration=declaration,
            unread=tuple(self._malformed) + self._leftovers(),
            census=self._census(),
        )

    def _descendant(self, node: ElementTree.Element, name: str) -> ElementTree.Element | None:
        for child in node.iter():
            if child is not node and _local(child.tag) == name:
                return child
        return None

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
            address = PostalAddress(
                country=self._pair(address_block, c.COUNTRY_CODE, c.COUNTRY_NAME),
                street_house=self._string(address_block, c.STREET_HOUSE),
            )
        return Organization(name=name, tax_code=tax_code, address=address)

    def _goods_location(self) -> GoodsLocation | None:
        block = next(
            (
                child
                for child in self._root
                if self._has(child, c.GOODS_LOCATION_INFORMATION_TYPE)
                or _local(child.tag) == c.GOODS_LOCATION
            ),
            None,
        )
        if block is None:
            return None
        self._consumed.add(id(block))
        information_type = self._string(block, c.GOODS_LOCATION_INFORMATION_TYPE)
        office = self._string(block, c.GOODS_LOCATION_OFFICE_CODE)
        country = self._string(block, c.GOODS_LOCATION_COUNTRY_CODE)
        if information_type is None or office is None or country is None:
            return None
        zone_block = self._child(block, c.CUSTOMS_ZONE)
        zone = None
        if zone_block is not None:
            self._consumed.add(id(zone_block))
            zone = self._string(zone_block, c.CUSTOMS_ZONE_NUMBER)
        return GoodsLocation(
            information_type_code=information_type,
            customs_office_code=office,
            country_code=country,
            customs_zone_number=zone,
        )

    def _goods_blocks(self) -> list[ElementTree.Element]:
        return [child for child in self._root if self._has(child, c.GOODS_NUMERIC)]

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

    def _consignment(self) -> Consignment:
        block = next(
            (child for child in self._root if _local(child.tag) == c.CONSIGNMENT), None
        )
        if block is None:
            return Consignment()
        self._consumed.add(id(block))
        transports = [child for child in block if self._has(child, c.TRANSPORT_MODE_CODE)]
        terms_block = next(
            (
                child
                for child in block
                if self._has(child, c.CONTRACT_CURRENCY_CODE)
                or self._has(child, c.TOTAL_INVOICE_AMOUNT)
                or self._has(child, c.DELIVERY_TERMS)
            ),
            None,
        )
        if terms_block is not None:
            self._consumed.add(id(terms_block))
        return Consignment(
            container_indicator=self._boolean(block, c.CONTAINER_INDICATOR),
            dispatch_country=self._pair(
                block, c.DISPATCH_COUNTRY_CODE, c.DISPATCH_COUNTRY_NAME
            ),
            border_office=self._border_office(block),
            departure_transport=self._transport(transports[0]) if transports else None,
            border_transport=self._transport(transports[1]) if len(transports) > 1 else None,
            currency_code=self._string(terms_block, c.CONTRACT_CURRENCY_CODE)
            if terms_block is not None
            else None,
            total_invoice_amount=self._decimal(terms_block, c.TOTAL_INVOICE_AMOUNT)
            if terms_block is not None
            else None,
            trade_country_code=self._string(terms_block, c.TRADE_COUNTRY_CODE)
            if terms_block is not None
            else None,
            delivery_terms=self._delivery_terms(terms_block)
            if terms_block is not None
            else None,
        )

    def _border_office(self, block: ElementTree.Element) -> BorderOffice | None:
        office = self._child(block, c.BORDER_OFFICE)
        if office is None:
            return None
        self._consumed.add(id(office))
        code = self._string(office, c.BORDER_OFFICE_CODE)
        if code is None:
            return None
        return BorderOffice(
            code=code,
            name=self._string(office, c.BORDER_OFFICE_NAME),
            country_code=self._string(office, c.BORDER_OFFICE_COUNTRY_CODE),
        )

    def _transport(self, block: ElementTree.Element) -> TransportBlock | None:
        self._consumed.add(id(block))
        mode = self._string(block, c.TRANSPORT_MODE_CODE)
        if mode is None:
            return None
        vehicles: list[TransportMeansRecord] = []
        for means in block:
            if _local(means.tag) != c.TRANSPORT_MEANS:
                continue
            self._consumed.add(id(means))
            identifier = self._string(means, c.TRANSPORT_IDENTIFIER)
            if identifier is None:
                continue
            vehicles.append(
                TransportMeansRecord(
                    identifier=identifier,
                    nationality_country_code=self._string(
                        means, c.TRANSPORT_NATIONALITY_CODE
                    ),
                )
            )
        return TransportBlock(
            mode_code=mode,
            vehicles=tuple(vehicles),
            vehicle_quantity=self._integer(block, c.TRANSPORT_MEANS_QUANTITY),
        )

    def _delivery_terms(self, block: ElementTree.Element) -> DeliveryTerms | None:
        terms = self._child(block, c.DELIVERY_TERMS)
        if terms is None:
            return None
        self._consumed.add(id(terms))
        code = self._string(terms, c.DELIVERY_TERMS_CODE)
        place = self._string(terms, c.DELIVERY_PLACE)
        if code is None and place is None:
            return None
        return DeliveryTerms(terms_code=code, place=place)

    def _filler(self) -> FillerPerson | None:
        block = next(
            (
                child
                for child in self._root
                if self._descendant(child, c.FILLER_EMAIL) is not None
                or _local(child.tag) == c.FILLER
            ),
            None,
        )
        if block is None:
            return None
        self._consumed.add(id(block))
        surname = self._string(block, c.FILLER_SURNAME)
        given_name = self._string(block, c.FILLER_GIVEN_NAME)
        if surname is None or given_name is None:
            return None
        contact = self._child(block, c.FILLER_CONTACT)
        phone = None
        email = None
        if contact is not None:
            self._consumed.add(id(contact))
            phone = self._string(contact, c.FILLER_PHONE)
            email = self._string(contact, c.FILLER_EMAIL)
        return FillerPerson(
            surname=surname, given_name=given_name, phone=phone, email=email
        )

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
