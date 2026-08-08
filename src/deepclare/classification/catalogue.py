"""L4 — a commodity code printed in a supplied vendor catalogue.

A vendor-printed code is a strong hint and it is not the importer's own filing. So the
short-circuit it produces is deliberately weak in three ways, each of which is the point:

* **Moderate confidence, 0.7.** Somebody at the supplier classified this product for
  their own market and their own tariff. That is worth more than nothing and less than a
  filing this importer stood behind.
* **Always flagged for review**, whatever the confidence gate would have said.
* **Shorter than ten digits never short-circuits.** A 6- or 8-digit catalogue code names
  a subheading, not a leaf, and picking a leaf inside it is exactly the judgement the
  graph exists to make.

The code is validated against the nomenclature here as well as at the gate on the way
out — accepting it *is* the decision this layer makes, and a layer that decides on an
unchecked value has decided nothing.
"""

from __future__ import annotations

from deepclare.classification.codes import (
    LEAF_DIGITS,
    NATIONAL_DIGITS,
    digits_of,
    leaf_form,
)
from deepclare.classification.line import ClassificationLine
from deepclare.classification.records import VENDOR_CATALOGUE_LAYER, LineClassification
from deepclare.classification.state import StepRecord
from deepclare.domain import Confidence, Transform
from deepclare.reference.store import NomenclatureStore

CATALOGUE_CONFIDENCE = 0.7
"""Moderate, and fixed. It is not a measurement of anything; it is the standing of the
source, and it is the same for every catalogue whatever the code."""

LEGAL_BASIS = "vendor catalogue"


class VendorCatalogueLayer:
    """Short-circuits a line whose catalogue names a code this tree can file."""

    def __init__(self, store: NomenclatureStore) -> None:
        self._store = store

    def decide(self, line: ClassificationLine) -> LineClassification | None:
        """The classification, or None to delegate the line inward."""
        if line.catalogue_code is None:
            return None

        printed = line.catalogue_code.value
        found = digits_of(printed)
        if len(found) not in (LEAF_DIGITS, NATIONAL_DIGITS):
            return None
        leaf = leaf_form(printed)
        if leaf is None or not self._store.exists(leaf):
            return None

        entry = self._store.entry(leaf)
        traced = line.catalogue_code
        if leaf != printed:
            traced = traced.with_transform(
                Transform(
                    operation="digits-only, reduced to the 10-digit leaf",
                    before=printed,
                    after=leaf,
                    reason="the catalogue prints the code in its own format; the "
                    "internal form is the 10-digit leaf of this nomenclature",
                ),
                leaf,
            )
        traced = traced.model_copy(
            update={"confidence": Confidence(derivation=CATALOGUE_CONFIDENCE)}
        )

        path = (entry.path_en if entry else None) or leaf
        return LineClassification(
            line_id=line.line_id,
            code=traced,
            needs_review=True,
            rationale=(
                f"Taken from the commodity code {printed!r} printed in a supplied "
                f"vendor catalogue, which exists in this nomenclature as {path}. The "
                "supplier classified this product for their own market, so confirm it "
                "against the goods before filing."
            ),
            supplementary_unit=entry.supplementary_unit if entry else None,
            legal_basis=LEGAL_BASIS,
            steps=(
                StepRecord(
                    node="L4",
                    detail=(
                        f"vendor catalogue prints {printed!r}; accepted as {leaf} at "
                        f"confidence {CATALOGUE_CONFIDENCE}, flagged for review, no "
                        "model call and no traversal"
                    ),
                ),
            ),
            decided_by=VENDOR_CATALOGUE_LAYER,
        )
