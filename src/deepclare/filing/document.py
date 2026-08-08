"""The element tree, the one serializer allowed to turn it into bytes, and its inverse.

Dossier 03 §6 specifies the physical shape of the file, and records that the default
output of common XML libraries — single-quoted lowercase prolog, whole document on one
line — matches none of it. So the tree is built here and written here, by hand:

    <?xml version="1.0" encoding="UTF-8"?><ESADout_CU:ESADout_CU …>
      <ESADout_CU:CustomsProcedure>IM</ESADout_CU:CustomsProcedure>
    </ESADout_CU:ESADout_CU>

Double-quoted uppercase prolog, root on the prolog's own line, two-space indent, one
element per line, no self-closing tags anywhere, and **no trailing newline** — the last
byte of the file is the root's closing angle bracket in all 71 ground truths.

**Every element carries its namespace prefix as data**, because the filed format splits
one document across three prefixes and which element sits under which is per-element
contract. `name` is always the local name, so a path, a child sequence and a facet
lookup all key on the same string whatever prefix the element was written under.

**Absence has exactly one representation: the element is not there.** `leaf` and
`container` enforce that by returning `None` rather than an element, so an absent value
cannot become an empty one by accident anywhere upstream — the predecessor's
self-closing empty containers were flagged as its single highest-risk unexamined
behaviour precisely because nothing structural prevented them.

`parse_document` is the exact inverse of `serialize`: it reads any filed declaration
into the same tree, prefixes included, so conformance can judge a document that this
repository did not write. That is what makes a corpus ground truth checkable.
"""

from __future__ import annotations

from collections.abc import Iterator
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict, Field

INDENT = "  "
PROLOG = '<?xml version="1.0" encoding="UTF-8"?>'


class Element(BaseModel):
    """One node. Either it carries text or it carries children, never both and never
    neither — a node with nothing in it is not written at all."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    """The local name, never qualified. The prefix is a separate field."""

    prefix: str | None = None
    """The namespace prefix this element is written under, or `None` for an unprefixed
    element. Carried rather than derived so that a document read from outside can be
    judged on the prefixes it actually uses."""

    text: str | None = None
    children: tuple["Element", ...] = ()
    attributes: tuple[tuple[str, str], ...] = ()
    """Attribute name exactly as written, including any prefix, paired with its value."""

    @property
    def qualified_name(self) -> str:
        return f"{self.prefix}:{self.name}" if self.prefix else self.name


def leaf(name: str, text: str | None, prefix: str | None = None) -> Element | None:
    """A text element, or nothing at all when there is nothing to say.

    Whitespace-only counts as nothing. An element present and blank is a third state the
    contract does not have and the portal has no defined behaviour for.
    """
    if text is None or not text.strip():
        return None
    return Element(name=name, prefix=prefix, text=text)


def container(
    name: str, children: list[Element | None], prefix: str | None = None
) -> Element | None:
    """A parent element, or nothing when every child turned out to be absent."""
    present = tuple(child for child in children if child is not None)
    if not present:
        return None
    return Element(name=name, prefix=prefix, children=present)


def escape_text(value: str) -> str:
    """Escape element content.

    The three markup characters, and a carriage return.

    The evidence base carries `&lt;`, `&gt;` and `&amp;` and no other entity anywhere,
    quotation marks appear literally inside text, and a line break inside a goods
    description is written as a **literal** line break rather than a character reference —
    130 leaves across the 71 filings do exactly that. Escaping one would parse to the same
    value and differ byte for byte from every filed declaration.

    The carriage return is the exception, and it is not a style choice: every XML parser
    normalises a literal `\\r` out of element content, so writing one literally loses it
    silently on the way back in. No filing in the evidence base carries one, so this
    escape never fires there and exists only so that a value cannot be quietly altered.
    """
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\r", "&#13;")
    )


def escape_attribute(value: str) -> str:
    return escape_text(value).replace('"', "&quot;")


def serialize(root: Element) -> str:
    """Write the document exactly as the contract wants it."""
    lines: list[str] = []
    _write(root, depth=0, lines=lines)
    lines[0] = PROLOG + lines[0].lstrip()
    return "\n".join(lines)


def _write(element: Element, depth: int, lines: list[str]) -> None:
    pad = INDENT * depth
    tag = element.qualified_name
    attributes = "".join(
        f' {name}="{escape_attribute(value)}"' for name, value in element.attributes
    )
    if element.children:
        lines.append(f"{pad}<{tag}{attributes}>")
        for child in element.children:
            _write(child, depth + 1, lines)
        lines.append(f"{pad}</{tag}>")
        return
    body = escape_text(element.text or "")
    lines.append(f"{pad}<{tag}{attributes}>{body}</{tag}>")


def parse_document(xml: str) -> Element:
    """Read a filed declaration into the same tree `serialize` writes.

    Prefixes come from the document's own namespace declarations rather than from any
    table here, so a document that puts an element under the wrong prefix is read as
    having done so and conformance can say which one.
    """
    prefixes = _declared_prefixes(xml)
    return _convert(ElementTree.fromstring(xml), prefixes, is_root=True)


def _declared_prefixes(xml: str) -> list[tuple[str, str]]:
    """The namespace declarations in document order, as (prefix, URI)."""
    parser = ElementTree.XMLPullParser(events=("start-ns",))
    parser.feed(xml)
    parser.close()
    declared: list[tuple[str, str]] = []
    for _, payload in parser.read_events():
        prefix, uri = payload
        if (prefix, uri) not in declared:
            declared.append((prefix, uri))
    return declared


def _split(tag: str, prefixes: list[tuple[str, str]]) -> tuple[str | None, str]:
    if not tag.startswith("{"):
        return None, tag
    uri, local = tag[1:].split("}", 1)
    for prefix, declared_uri in prefixes:
        if declared_uri == uri:
            return (prefix or None), local
    return f"{{{uri}}}", local


def _convert(
    node: ElementTree.Element, prefixes: list[tuple[str, str]], is_root: bool
) -> Element:
    prefix, name = _split(node.tag, prefixes)
    attributes: list[tuple[str, str]] = []
    if is_root:
        attributes.extend(
            (f"xmlns:{declared}" if declared else "xmlns", uri)
            for declared, uri in prefixes
        )
    for key, value in node.attrib.items():
        key_prefix, key_name = _split(key, prefixes)
        attributes.append((f"{key_prefix}:{key_name}" if key_prefix else key_name, value))
    children = tuple(_convert(child, prefixes, is_root=False) for child in node)
    return Element(
        name=name,
        prefix=prefix,
        text=None if children else node.text,
        children=children,
        attributes=tuple(attributes),
    )


class Located(BaseModel):
    """An element together with where it sits, for anything that has to judge it."""

    model_config = ConfigDict(frozen=True)

    element: Element
    path: str
    """Slash-separated **local** element names from the root, e.g.
    `ESADout_CU/ESADout_CUGoodsShipment/ESADout_CUGoods/GoodsDescription`. Prefixes and
    positions are deliberately absent: a path names a place in the contract, and the
    prefix and the value are reported alongside it."""

    parent_name: str | None
    depth: int
    """1 for the root."""


def walk(root: Element) -> Iterator[Located]:
    """Every element in document order, each knowing its path, parent and depth."""
    yield from _walk(root, parent_name=None, parent_path="", depth=1)


def _walk(
    element: Element, parent_name: str | None, parent_path: str, depth: int
) -> Iterator[Located]:
    path = f"{parent_path}/{element.name}" if parent_path else element.name
    yield Located(element=element, path=path, parent_name=parent_name, depth=depth)
    for child in element.children:
        yield from _walk(child, parent_name=element.name, parent_path=path, depth=depth + 1)
