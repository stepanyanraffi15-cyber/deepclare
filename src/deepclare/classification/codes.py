"""Reading code-shaped text, which is never quite a code.

Every string that arrives here was typed or printed by somebody: a broker's invoice in
another country's national format, a catalogue's product table, a model's answer. They
carry dots, spaces, letters, national suffixes and — in real filed declarations — a
hand-typed run of zeros standing in for a code nobody looked up.

Nothing in this module decides anything. It turns text into the digits it meant, or into
nothing at all, and the layers above decide what that means.
"""

from __future__ import annotations

import re

HARMONIZED_DIGITS = 6
"""The internationally harmonized prefix. Digits beyond it are one country's national
subdivision and mean nothing in another country's tree."""

LEAF_DIGITS = 10
"""The filable leaf of this nomenclature, and the internal form of every code here."""

NATIONAL_DIGITS = 11
"""The filed form: the leaf plus the Armenian national subdivision digit."""

CHAPTER_DIGITS = 2
HEADING_DIGITS = 4

_NON_DIGIT = re.compile(r"\D+")


def digits_of(text: str | None) -> str:
    """Just the digits, in order. `8536.50.90 00` becomes `8536509000`."""
    return "" if text is None else _NON_DIGIT.sub("", text)


def is_filler(code: str) -> bool:
    """A run of zeros, which is what a hand-typed stand-in for a code looks like.

    Found in real stored declarations as an all-zeros 11-digit value. It passes every
    length and digit check and exists in no nomenclature.
    """
    return bool(code) and set(code) == {"0"}


def harmonized_prefix(text: str | None) -> str | None:
    """The first six digits of a printed code, or None if there are not six to take.

    A printed code shorter than six digits does not reach the harmonized level, so it
    identifies no subheading anywhere and is not evidence about this tree.
    """
    found = digits_of(text)
    if len(found) < HARMONIZED_DIGITS:
        return None
    prefix = found[:HARMONIZED_DIGITS]
    return None if is_filler(prefix) else prefix


def leaf_form(text: str | None) -> str | None:
    """The 10-digit internal form of a code, or None if the text is not one.

    The filed 11-digit national form reduces to its leaf; anything else — a 6- or 8-digit
    stub, a wrong length, a filler — is not a code that can be assigned to a line.
    """
    found = digits_of(text)
    if len(found) == NATIONAL_DIGITS:
        found = found[:LEAF_DIGITS]
    if len(found) != LEAF_DIGITS or is_filler(found):
        return None
    return found


def national_suffix(text: str | None) -> str | None:
    """The 11th digit of a filed code, when the text carries one.

    It is `0` on roughly 98% of filings and the rule "append zero" is not universally
    correct: a small number of real codes carry a non-zero national digit, and those
    splits exist in no 10-digit index. Dropping one silently would change the code.
    """
    found = digits_of(text)
    return found[LEAF_DIGITS] if len(found) == NATIONAL_DIGITS else None


def normalize_chapter(text: str | None) -> str | None:
    """A model's chapter answer as two digits, or None.

    Left-pad, then truncate: `5` is chapter `05` and `3926` names chapter `39`. Whether
    the result is a chapter of this tree is a question for the tree, not for this
    function.
    """
    found = digits_of(text)
    if not found:
        return None
    return found.zfill(CHAPTER_DIGITS)[:CHAPTER_DIGITS]


def normalize_at(text: str | None, width: int) -> str | None:
    """A model's heading or subheading answer at a fixed width, or None if it is short.

    Unlike a chapter, these are not padded. A three-digit answer where four are expected
    is not a heading missing a leading zero, it is an answer that did not name a heading.
    """
    found = digits_of(text)
    return found[:width] if len(found) >= width else None
