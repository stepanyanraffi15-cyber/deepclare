"""Deciding what an unlabelled file is, from its name alone.

A declared role always wins. When there is none, the name is read in a fixed precedence:

    consignment-note keyword
      → catalogue/specification keyword
        → XML extension or declaration keyword
          → invoice

The order is not arbitrary and neither is the default. A prior declaration is the only
XML among the sources, which is why the extension alone settles it. Everything left over
defaults to the invoice because a missing invoice is the fatal case: a submission with no
invoice is refused outright, so guessing "invoice" costs a misrouted page while guessing
anything else costs the whole run.

Matching is a case-insensitive substring test, because real file names run words
together (`CMR12345.pdf`) and token splitting would miss them.
"""

from __future__ import annotations

from deepclare.domain import DocumentRole
from deepclare.intake.submission import SubmittedFile

_CONSIGNMENT_NOTE_KEYWORDS = (
    "cmr",
    "consignment",
    "waybill",
    "накладная",
    "բեռնագիր",
)
_CATALOG_SPEC_KEYWORDS = (
    "catalog",
    "catalogue",
    "spec",
    "datasheet",
    "brochure",
    "каталог",
    "կատալոգ",
)
_DECLARATION_KEYWORDS = (
    "declar",
    "деклар",
    "հայտարարագիր",
)
_DECLARATION_EXTENSION = ".xml"


def role_of(file: SubmittedFile) -> DocumentRole:
    """The role this file will be routed by: what the client declared, or what its name says."""
    return file.declared_role or infer_role_from_filename(file.file_name)


def infer_role_from_filename(file_name: str) -> DocumentRole:
    """Read a role out of a file name, in the fixed precedence. Never fails."""
    name = file_name.casefold()

    if _mentions(name, _CONSIGNMENT_NOTE_KEYWORDS):
        return DocumentRole.CONSIGNMENT_NOTE
    if _mentions(name, _CATALOG_SPEC_KEYWORDS):
        return DocumentRole.CATALOG_SPEC
    if name.endswith(_DECLARATION_EXTENSION) or _mentions(name, _DECLARATION_KEYWORDS):
        return DocumentRole.PRIOR_DECLARATION
    return DocumentRole.INVOICE


def _mentions(lowered_name: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in lowered_name for keyword in keywords)
