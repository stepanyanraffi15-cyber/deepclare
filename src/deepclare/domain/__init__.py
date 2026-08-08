"""M1 Domain Vocabulary — serialization-independent definitions.

Dossier 10 §3 M1. This package is definitional: it depends on nothing.

Must not know about: any storage shape, any transport, any model, any prompt, and in
particular the element names, ordering or formatting of the filed document. The natural
hierarchy is domain truth; the filed document's shape belongs to the filing adapter.
"""

from deepclare.domain.documents import (
    ConsignmentNote,
    DocumentRole,
    InvoiceGoodsLine,
    InvoiceRecord,
    LineEnrichment,
    PageClass,
    PageClassification,
    Party,
    SourceLanguage,
)
from deepclare.domain.provenance import (
    Confidence,
    DocumentRegion,
    Provenance,
    Traced,
    Transform,
    ValueOrigin,
)
from deepclare.domain.review import ReviewItem, ReviewKind

__all__ = [
    "Confidence",
    "ConsignmentNote",
    "DocumentRegion",
    "DocumentRole",
    "InvoiceGoodsLine",
    "InvoiceRecord",
    "LineEnrichment",
    "PageClass",
    "PageClassification",
    "Party",
    "Provenance",
    "ReviewItem",
    "ReviewKind",
    "SourceLanguage",
    "Traced",
    "Transform",
    "ValueOrigin",
]
