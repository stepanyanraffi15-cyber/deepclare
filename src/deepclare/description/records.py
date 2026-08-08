"""From what the model answered to a domain record, with the checks a prompt cannot make.

Two jobs. First, attach provenance: the description is *generated*, not read off a page,
and the account of which prompt at which version wrote it is recoverable nowhere else, so
it is attached here at the producer.

Second, refuse an answer that is the right shape and the wrong thing. Three checks run,
and each exists because prompt wording cannot enforce it:

* **The text is Armenian.** The one thing this module produces is Armenian filed text.
  An answer in Latin script is not a description with a defect, it is not a description.
* **Every figure in the text comes from the documents.** A number, percentage or rating
  that appears in no source is a fabricated specific — on a customs declaration that is a
  false statement to the authority, not a quality defect. The check is deliberately
  forgiving about form (it asks whether the digits appear anywhere in the input) because
  it is meant to catch inventions, not punctuation.
* **Neither text is blank.** A blank description is not a lesser description.

All three raise. There is no repair, no second attempt and no fallback to a generic
Armenian noun: filing a stand-in as though it were a description is exactly the failure
this product exists to avoid, and a missing description is work left for a human.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from deepclare.description.context import LineContext, detect_source_language
from deepclare.description.errors import DescriptionError
from deepclare.description.schemas import WriteDescription
from deepclare.domain import (
    Confidence,
    Provenance,
    SourceLanguage,
    Traced,
    ValueOrigin,
)
from deepclare.models import ModelCall

STAGE = "description"
"""What every value produced here names as its producing stage."""

_DIGIT_RUN = re.compile(r"\d+(?:[.,]\d+)*")


class ProductKind(StrEnum):
    """What the goods physically are, which is not what the invoice's unit column says.

    It is the model's read of the product itself — discrete goods are routinely invoiced
    by the kilogram — and it feeds unit resolution downstream, never the other way round.
    """

    PIECE = "piece"
    WEIGHT = "weight"
    LENGTH = "length"
    AREA = "area"
    VOLUME = "volume"


class DescriptionCompleteness(StrEnum):
    """How well grounded the written description is in the documents behind it.

    A self-report, and a report about the *input*: a sparse line is `LOW` however much
    text was written about it.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# The completeness self-report is the only statement this call makes about how far to
# trust what it wrote, so it is what the generated values' derivation confidence is built
# from. The three numbers stand for the three declared bands and nothing else: no
# measurement in this system has calibrated them, and they must not be read as
# probabilities. They exist because a generated value that declares no confidence leaves
# the review surface with nothing to rank it by.
_DERIVATION_BY_COMPLETENESS = {
    DescriptionCompleteness.HIGH: 0.9,
    DescriptionCompleteness.MEDIUM: 0.6,
    DescriptionCompleteness.LOW: 0.3,
}


class LineDescription(BaseModel):
    """One goods line's Armenian description, and what was written alongside it."""

    model_config = ConfigDict(frozen=True)

    line_id: str = Field(pattern=r"^[1-9][0-9]*$")
    text: Traced[str]
    """The Armenian description. It becomes the leading segment of the filed text; the
    size and quantity segments are appended to it downstream, from computed figures."""

    search_term: Traced[str]
    """A short Armenian generic-noun phrase, for the commodity-code lookup. Never
    filed."""

    product_kind: Traced[ProductKind]
    completeness: DescriptionCompleteness
    """Not traced: it is a statement *about* the values above rather than a value of its
    own, and it is never filed."""

    call: ModelCall


def description_from_answer(
    answer: WriteDescription, context: LineContext, call: ModelCall
) -> LineDescription:
    """Build the record from what the model returned, or raise."""
    text = _armenian(answer.description, context, "description")
    search_term = _armenian(answer.search_term, context, "search term")
    completeness = DescriptionCompleteness(answer.completeness)
    provenance = Provenance(
        origin=ValueOrigin.GENERATED,
        stage=STAGE,
        prompt_name=call.prompt_name,
        prompt_version=call.prompt_version,
    )
    confidence = Confidence(derivation=_DERIVATION_BY_COMPLETENESS[completeness])
    return LineDescription(
        line_id=context.line_id,
        text=Traced[str](value=text, provenance=provenance, confidence=confidence),
        search_term=Traced[str](
            value=search_term, provenance=provenance, confidence=confidence
        ),
        product_kind=Traced[ProductKind](
            value=ProductKind(answer.product_kind),
            provenance=provenance,
            confidence=confidence,
        ),
        completeness=completeness,
        call=call,
    )


def _armenian(written: str, context: LineContext, what: str) -> str:
    """Check one written string, and return it stripped of surrounding whitespace."""
    text = written.strip()
    if not text:
        raise DescriptionError(
            f"line {context.line_id}: the {what} came back empty. There is nothing to "
            f"file for {context.goods_name!r}."
        )
    if detect_source_language(text) is not SourceLanguage.ARMENIAN:
        raise DescriptionError(
            f"line {context.line_id}: the {what} carries no Armenian text — {text!r}. "
            "The declaration is filed in Armenian, and text in another script is not a "
            "description with a defect."
        )
    invented = _numbers_not_in_the_documents(text, context)
    if invented:
        raise DescriptionError(
            f"line {context.line_id}: the {what} states "
            f"{', '.join(repr(number) for number in invented)}, which no source document "
            f"states — {text!r}. A figure in a filed description that is not on a "
            "document behind it is a false statement to customs, not a wording problem."
        )
    return text


def _numbers_not_in_the_documents(
    text: str, context: LineContext
) -> tuple[str, ...]:
    """Figures in the written text that appear nowhere in the input it was given.

    Containment on a decimal-separator-blind rendering, not equality: a figure the model
    wrote as `42,5` where the invoice printed `42.5` is the same figure, and this check is
    looking for figures that are not there at all rather than for figures written
    differently.
    """
    sources = _separator_blind(" ".join(_source_texts(context)))
    return tuple(
        dict.fromkeys(
            match.group(0)
            for match in _DIGIT_RUN.finditer(text)
            if _separator_blind(match.group(0)) not in sources
        )
    )


def _separator_blind(text: str) -> str:
    return text.replace(",", ".")


def _source_texts(context: LineContext) -> Iterable[str]:
    """Everything the writer was given that could legitimately carry a figure."""
    yield context.goods_name
    for optional in (context.trade_name, context.material):
        if optional:
            yield optional
    yield from context.grounding_facts
