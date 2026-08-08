"""What one goods line looks like to code assignment.

It is the description module's per-line context plus the three things that module was
deliberately not shown, because a description is written before a code exists and must
not depend on one:

* the Armenian description and the retrieval term it wrote — the primary statement of
  what these goods are;
* a commodity code printed on the invoice line, which is the exporter's broker's own
  classification and whose first six digits are internationally harmonized;
* a commodity code printed in a supplied vendor catalogue.

Reusing the description module's context builder rather than rebuilding the sibling
summary here is deliberate: two implementations of "which lines are this line's trade
context" would drift, and the narrowing calls and the description writer would then be
reasoning about different shipments.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from deepclare.classification.errors import ClassificationError
from deepclare.description import LineContext, LineDescription, build_line_contexts
from deepclare.domain import InvoiceRecord, LineEnrichment, SourceLanguage, Traced


class ClassificationLine(BaseModel):
    """One goods line, as the classifier sees it.

    Everything in here reaches a model in some form. What is absent is absent on
    purpose — the shipment's other outcomes, the declarant, the quantities and the
    prices are not evidence about what a good *is*.
    """

    model_config = ConfigDict(frozen=True)

    line_id: str = Field(pattern=r"^[1-9][0-9]*$")

    description_hy: str = Field(min_length=1)
    """The Armenian text that will be filed for this line."""

    search_term_hy: str = Field(min_length=1)
    """A short Armenian generic-noun phrase for the product's category."""

    source_name: str = Field(min_length=1)
    """The invoice's own wording, as printed and untranslated."""

    source_language: SourceLanguage
    """Withheld from the final pick and the verifier. Broad context measurably helps
    chapter and heading choice on terse SKU names and measurably distracts leaf-level
    discrimination."""

    unit: str | None = None
    trade_name: str | None = None
    material: str | None = None
    grounding_facts: tuple[str, ...] = ()
    sibling_names: tuple[str, ...] = ()
    """Withheld from the final pick, for the same measured reason as the language tag."""

    printed_code: Traced[str] | None = None
    """A commodity code printed on this invoice line, as read. Foreign national codes
    are expected — Turkish GTIP, Georgian, EU TARIC — so only the first six digits mean
    anything here, and the rest is another country's national suffix."""

    catalogue_code: Traced[str] | None = None
    """A commodity code printed in a supplied vendor catalogue for these goods."""


def build_classification_lines(
    invoice: InvoiceRecord,
    descriptions: Sequence[LineDescription],
    enrichments: Sequence[LineEnrichment] = (),
) -> tuple[ClassificationLine, ...]:
    """One classification line per invoice goods line, in printed order.

    Every goods line must have a description keyed by its id. A line whose description
    is missing cannot be classified, and failing here names the line, where a lookup
    failure later would name a dictionary.
    """
    contexts = {context.line_id: context for context in build_line_contexts(invoice, enrichments)}
    written = {description.line_id: description for description in descriptions}
    catalogue = {
        enrichment.line_id: enrichment.printed_customs_code
        for enrichment in enrichments
        if enrichment.printed_customs_code is not None
    }

    lines = []
    for goods_line in invoice.goods_lines:
        description = written.get(goods_line.line_id)
        if description is None:
            raise ClassificationError(
                f"line {goods_line.line_id} ({goods_line.description.value!r}) has no "
                "description. Code assignment runs on the written description and cannot "
                "start without one."
            )
        lines.append(
            _line(
                contexts[goods_line.line_id],
                description,
                goods_line.printed_customs_code,
                catalogue.get(goods_line.line_id),
            )
        )
    return tuple(lines)


def _line(
    context: LineContext,
    description: LineDescription,
    printed_code: Traced[str] | None,
    catalogue_code: Traced[str] | None,
) -> ClassificationLine:
    return ClassificationLine(
        line_id=context.line_id,
        description_hy=description.text.value,
        search_term_hy=description.search_term.value,
        source_name=context.goods_name,
        source_language=context.source_language,
        unit=context.unit,
        trade_name=context.trade_name,
        material=context.material,
        grounding_facts=context.grounding_facts,
        sibling_names=context.sibling_names,
        printed_code=printed_code,
        catalogue_code=catalogue_code,
    )
