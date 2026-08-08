"""The layer stack: one code per goods line, or an abstention with a stated reason.

A line descends through the layers until one of them decides, and the decision returns
outward through every layer it passed. The whole stack is five lines of `classify`, which
is the point — the order is a fact about the product and it should be readable as one.

    L1  existence gate        wraps everything, and does its work on the return
    L4  vendor-catalogue code short-circuits at moderate confidence, always flagged
    --  Code Assignment graph the per-line traversal, which abstains rather than guessing

**There is no L2 and no L3.** The specification describes two layers that reuse codes
from the customer's own filed declarations and from an older description-to-code store.
Customer-history reuse was removed from this product deliberately: no code here searches
anyone's prior filings. Nomenclature search over the reference collection is a different
thing and is what the graph runs on.

The numbering is the specification's and is kept rather than renumbered, so that a reader
holding both can see at a glance that two layers are missing on purpose.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from deepclare.classification.assignment import CodeAssignment
from deepclare.classification.catalogue import VendorCatalogueLayer
from deepclare.classification.existence import ExistenceGate
from deepclare.classification.features import ClassificationFeatures
from deepclare.classification.graph import Graph
from deepclare.classification.line import ClassificationLine
from deepclare.classification.records import LineClassification
from deepclare.models import GenerativeModel
from deepclare.reference.store import NomenclatureStore


class Classifier:
    """Assigns a commodity code to one goods line at a time.

    Construct one per run. Lines are independent by contract — the traversal never sees
    another line's outcome — so classifying them in any order gives the same answers.
    """

    def __init__(
        self,
        *,
        store: NomenclatureStore,
        model: GenerativeModel,
        prompts_dir: Path,
        features: ClassificationFeatures | None = None,
    ) -> None:
        self._features = features or ClassificationFeatures()
        self._existence_gate = ExistenceGate(store)
        self._vendor_catalogue = VendorCatalogueLayer(store)
        self._code_assignment = CodeAssignment(
            store=store,
            model=model,
            prompts_dir=prompts_dir,
            features=self._features,
        )

    @property
    def features(self) -> ClassificationFeatures:
        return self._features

    @property
    def graph(self) -> Graph:
        """The Code Assignment graph declaration, printable without running it."""
        return self._code_assignment.graph

    def classify(self, line: ClassificationLine) -> LineClassification:
        """Descend the stack until a layer decides, then return through the gate."""
        decided = self._vendor_catalogue.decide(line)
        if decided is None:
            decided = self._code_assignment.decide(line)
        return self._existence_gate.check(decided)

    def classify_all(
        self, lines: Sequence[ClassificationLine]
    ) -> tuple[LineClassification, ...]:
        """Every line, in the order given. One failure ends the batch."""
        return tuple(self.classify(line) for line in lines)
