"""M9 Classification — one commodity code per goods line, or an abstention.

In: the goods line's evidence, the Armenian description and retrieval term the
description module wrote, reference-data query results, and any code printed on the
source documents.

Out: one 10-digit code or an abstention with its rationale; a confidence; the candidate
set; the supplementary unit read off the chosen entry; the legal basis; and the per-step
trace of the traversal.

**Must not know:** the filing contract, the review-item vocabulary, the declarant
profile, the service edge, or the outcomes of other goods lines — the traversal is per
line and independent. The review *flag* and the rationale a review item is built from are
produced here; the item itself is not, and nothing in this package imports the review
vocabulary.

**Owns the existence gate** as its outermost layer: no code leaves this module that is
absent from the current nomenclature, whatever produced it.

**Searches no customer's prior filings.** Two layers of the specification's stack did
exactly that and were removed from the product deliberately. Nomenclature search over the
reference collection is a different thing and is what the graph runs on.

The governing asymmetry decides every close call in here: on a legal document a wrong
value is a consequential error while a missing one is work left for a human. So a code
the model invents is not quietly replaced by the nearest retrieved one, a narrowing
choice never removes a candidate, and the pick is given enough of the tree to see that
none of the candidates fits.
"""

from deepclare.classification.assignment import GRAPH_NAME, CodeAssignment, build_graph
from deepclare.classification.catalogue import CATALOGUE_CONFIDENCE, VendorCatalogueLayer
from deepclare.classification.classifier import Classifier
from deepclare.classification.confidence import (
    below_review_gate,
    composite_confidence,
    normalized_similarity,
)
from deepclare.classification.errors import ClassificationError, GraphDeclarationError
from deepclare.classification.existence import ExistenceGate
from deepclare.classification.features import ClassificationFeatures
from deepclare.classification.graph import END, ENTRY, Edge, Graph, Node
from deepclare.classification.line import ClassificationLine, build_classification_lines
from deepclare.classification.nodes import NARROWING_TIER, PICK_TIER, NodeContext
from deepclare.classification.records import STAGE, LineClassification
from deepclare.classification.state import GraphOutcome, StepRecord, TraversalState

__all__ = [
    "CATALOGUE_CONFIDENCE",
    "END",
    "ENTRY",
    "GRAPH_NAME",
    "NARROWING_TIER",
    "PICK_TIER",
    "STAGE",
    "ClassificationError",
    "ClassificationFeatures",
    "ClassificationLine",
    "Classifier",
    "CodeAssignment",
    "Edge",
    "ExistenceGate",
    "Graph",
    "GraphDeclarationError",
    "GraphOutcome",
    "LineClassification",
    "Node",
    "NodeContext",
    "StepRecord",
    "TraversalState",
    "VendorCatalogueLayer",
    "below_review_gate",
    "build_classification_lines",
    "build_graph",
    "composite_confidence",
    "normalized_similarity",
]
