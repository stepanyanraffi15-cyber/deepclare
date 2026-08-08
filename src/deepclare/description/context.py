"""The deterministic per-line context: what language a line is written in, and its siblings.

No model call happens here and none is needed. Both facts are cheap, both are stable, and
both are things a model would get wrong more often than a rule does.

**The source-language tag** exists for one measured failure: a foreign trade term read as
the English word it resembles. Turkish `RAY TAŞIYICI` is a carrier for DIN mounting rail,
not railway equipment. The tag hands the downstream models the right lexicon. It is
detected by script, first match wins on a single matching character anywhere in the
string, in this precedence: Armenian, Cyrillic, Farsi/Arabic, Turkish, else English/Latin.
Turkish is decided by `İıŞşĞğ` alone — `ö`, `ü` and `ç` are too common in other Latin
languages to be decisive. There is no transliteration anywhere in this pipeline, here
least of all.

**The sibling summary** exists for the terse SKU line. An unlabelled `MKR 2,5 MM` on an
invoice full of terminal blocks and encoders is electrical gear, not stationery; the
shipment's other lines say which trade it is in. It is a summary, not the lines
themselves: the nearest few names, each cut short, because what it carries is the trade
context and not the neighbours' details.

**What this deliberately withholds is as load-bearing as what it carries.** A prohibition
backed by omission cannot be violated, and four things are omitted rather than forbidden:

* the commodity code printed on the line — description writing runs *before* code
  assignment and its output is an input to it, so a dependency on a code would invert the
  graph;
* the quantity and the package counts — every figure in the filed text is arithmetic
  computed elsewhere, and a figure the model wrote would be a duplicate or a
  contradiction;
* the printed dimensions — the size segment is appended to the written text downstream,
  from the invoice's own figure;
* the invoice's own totals and the shipment's weights — none of them describes what the
  goods *are*.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from deepclare.domain import (
    InvoiceGoodsLine,
    InvoiceRecord,
    LineEnrichment,
    SourceLanguage,
    Traced,
)

MAX_SIBLINGS = 10
"""How many other invoice lines the summary carries. Enough to establish a trade, few
enough that a 60-line invoice does not bury the line being described."""

SIBLING_EXCERPT_CHARS = 60
"""How much of each sibling name is kept. A goods name states its product within its
first few words; the rest is model numbers and packing detail, which is the neighbour's
identity and not this line's context."""

# Ranges rather than a Unicode-category lookup: the question is which of five known
# source scripts this text is in, not what every character is.
_ARMENIAN = ((0x0530, 0x058F), (0xFB13, 0xFB17))
_CYRILLIC = ((0x0400, 0x04FF), (0x0500, 0x052F))
_ARABIC = ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
_TURKISH_DIACRITICS = frozenset("İıŞşĞğ")


def detect_source_language(text: str) -> SourceLanguage:
    """Which script a goods name is written in.

    Precedence decides, not position: one Armenian character anywhere makes the line
    Armenian even if the rest is Latin, because a Latin brand embedded in Armenian text
    is ordinary and the reverse is not.
    """
    if _has_char_in(text, _ARMENIAN):
        return SourceLanguage.ARMENIAN
    if _has_char_in(text, _CYRILLIC):
        return SourceLanguage.RUSSIAN
    if _has_char_in(text, _ARABIC):
        return SourceLanguage.FARSI_ARABIC
    if any(character in _TURKISH_DIACRITICS for character in text):
        return SourceLanguage.TURKISH
    return SourceLanguage.ENGLISH_LATIN


class LineContext(BaseModel):
    """Everything the description writer is given about one goods line.

    Assembled here so that the boundary is visible in one place: what is in this object
    is what reaches the model, and nothing else about the line does.
    """

    model_config = ConfigDict(frozen=True)

    line_id: str = Field(pattern=r"^[1-9][0-9]*$")
    goods_name: str = Field(min_length=1)
    """The invoice's own wording, exactly as printed and untranslated."""

    source_language: SourceLanguage
    unit: str | None = None
    """As printed. It hints at the physical form — litres at a liquid, pieces at a
    countable article — and is never copied into the description."""

    unit_price: Decimal | None = None
    """A weak hint only: a very low per-unit price suggests bulk material, a high one a
    finished product."""

    trade_name: str | None = None
    """The brand or model printed for this line, never guessed from the product."""

    material: str | None = None
    """Material or composition, as a supporting document states it."""

    grounding_facts: tuple[str, ...] = ()
    """What supporting evidence says about these goods, in the words it said it in."""

    sibling_names: tuple[str, ...] = ()
    """Other goods names from the same invoice, shortened, nearest first in printed
    order."""


def build_line_contexts(
    invoice: InvoiceRecord,
    enrichments: Sequence[LineEnrichment] = (),
    *,
    max_siblings: int = MAX_SIBLINGS,
    sibling_excerpt_chars: int = SIBLING_EXCERPT_CHARS,
) -> tuple[LineContext, ...]:
    """One context per goods line, in the invoice's printed order.

    An enrichment naming a line the invoice does not have is dropped; two enrichments
    naming one line leave the last one standing. Both follow the enricher's own contract:
    a verdict about a line that does not exist is noise, not an error to stop a run for.
    """
    by_line_id = {enrichment.line_id: enrichment for enrichment in enrichments}
    return tuple(
        _context_for(
            line,
            invoice.goods_lines,
            position,
            by_line_id.get(line.line_id),
            max_siblings,
            sibling_excerpt_chars,
        )
        for position, line in enumerate(invoice.goods_lines)
    )


def _context_for(
    line: InvoiceGoodsLine,
    all_lines: Sequence[InvoiceGoodsLine],
    position: int,
    enrichment: LineEnrichment | None,
    max_siblings: int,
    sibling_excerpt_chars: int,
) -> LineContext:
    goods_name = line.description.value.strip()
    return LineContext(
        line_id=line.line_id,
        goods_name=goods_name,
        source_language=detect_source_language(goods_name),
        unit=_text(line.unit),
        unit_price=_number(line.unit_price),
        trade_name=_text(line.trade_name),
        material=_text(enrichment.material) if enrichment else None,
        grounding_facts=(
            tuple(fact.value for fact in enrichment.grounding_facts)
            if enrichment
            else ()
        ),
        sibling_names=_sibling_names(
            all_lines, position, max_siblings, sibling_excerpt_chars
        ),
    )


def _sibling_names(
    all_lines: Sequence[InvoiceGoodsLine],
    position: int,
    max_siblings: int,
    excerpt_chars: int,
) -> tuple[str, ...]:
    """The nearest other lines, shortened, returned in printed order.

    Nearest rather than first: an invoice groups a product family together, so the rows
    beside this one are the ones that say what it is. Ties go to the earlier line, which
    only decides which of two equally-near neighbours is kept when the budget runs out.
    """
    others = [index for index in range(len(all_lines)) if index != position]
    nearest = sorted(others, key=lambda index: (abs(index - position), index))
    return tuple(
        _excerpt(all_lines[index].description.value, excerpt_chars)
        for index in sorted(nearest[:max_siblings])
    )


def _excerpt(text: str, limit: int) -> str:
    """Shorten to the limit, marking the cut so a truncated name cannot read as a
    complete one."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[:limit]}…"


def _has_char_in(text: str, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(
        any(low <= ord(character) <= high for low, high in ranges) for character in text
    )


def _text(traced: Traced[str] | None) -> str | None:
    """The plain value of an optional traced string.

    The context is what reaches a model, and a model is shown values rather than the
    account of where they came from. Provenance stays on the invoice record, which is
    what the written description's own provenance will point back to.
    """
    return None if traced is None else traced.value


def _number(traced: Traced[Decimal] | None) -> Decimal | None:
    return None if traced is None else traced.value
