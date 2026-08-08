"""The element tree, and the one serializer allowed to turn it into bytes.

Dossier 03 §6 specifies the physical shape of the file, and records that the default
output of common XML libraries — single-quoted lowercase prolog, whole document on one
line — matches none of it. So the tree is built here and written here, by hand:

    <?xml version="1.0" encoding="UTF-8"?><ESADout_CU …>
      <CustomsProcedure>IM</CustomsProcedure>
    </ESADout_CU>

Double-quoted uppercase prolog, root on the prolog's own line, two-space indent, one
element per line, and no self-closing tags anywhere.

**Absence has exactly one representation: the element is not there.** All 311 accepted
filings contain zero empty elements, zero self-closing elements and zero placeholder
strings. `leaf` and `container` enforce that by returning `None` rather than an element,
so an absent value cannot become an empty one by accident anywhere upstream — the
predecessor's self-closing empty containers were flagged as its single highest-risk
unexamined behaviour precisely because nothing structural prevented them.
"""

from __future__ import annotations

from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict, Field

INDENT = "  "
PROLOG = '<?xml version="1.0" encoding="UTF-8"?>'


class Element(BaseModel):
    """One node. Either it carries text or it carries children, never both and never
    neither — a node with nothing in it is not written at all."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    text: str | None = None
    children: tuple["Element", ...] = ()
    attributes: tuple[tuple[str, str], ...] = ()


def leaf(name: str, text: str | None) -> Element | None:
    """A text element, or nothing at all when there is nothing to say.

    Whitespace-only counts as nothing. An element present and blank is a third state the
    contract does not have and the portal has no defined behaviour for.
    """
    if text is None or not text.strip():
        return None
    return Element(name=name, text=text)


def container(name: str, children: list[Element | None]) -> Element | None:
    """A parent element, or nothing when every child turned out to be absent."""
    present = tuple(child for child in children if child is not None)
    if not present:
        return None
    return Element(name=name, children=present)


def escape_text(value: str) -> str:
    """Escape element content, including the line breaks.

    Line breaks become character references so that "one element per line" survives a
    description with a newline in it. Filed declarations do carry embedded line breaks
    written this way, so this is the format's own idiom rather than an invention.
    """
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\r", "&#13;")
        .replace("\n", "&#10;")
    )


def escape_attribute(value: str) -> str:
    return escape_text(value).replace('"', "&quot;")


def serialize(root: Element) -> str:
    """Write the document exactly as the contract wants it."""
    lines: list[str] = []
    _write(root, depth=0, lines=lines)
    lines[0] = PROLOG + lines[0].lstrip()
    return "\n".join(lines) + "\n"


def _write(element: Element, depth: int, lines: list[str]) -> None:
    pad = INDENT * depth
    attributes = "".join(
        f' {name}="{escape_attribute(value)}"' for name, value in element.attributes
    )
    if element.children:
        lines.append(f"{pad}<{element.name}{attributes}>")
        for child in element.children:
            _write(child, depth + 1, lines)
        lines.append(f"{pad}</{element.name}>")
        return
    body = escape_text(element.text or "")
    lines.append(f"{pad}<{element.name}{attributes}>{body}</{element.name}>")


class Located(BaseModel):
    """An element together with where it sits, for anything that has to judge it."""

    model_config = ConfigDict(frozen=True)

    element: Element
    path: str
    """Slash-separated element names from the root, e.g.
    `ESADout_CU/ESADout_CUGoods/GoodsDescription`. Positions are deliberately absent:
    a path names a place in the contract, and the value is reported alongside it."""

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
