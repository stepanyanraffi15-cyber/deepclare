"""Review items — the machine-readable account of everything a human must confirm.

Dossier 02 §1: the system never asks a question. There is no interactive node, no wait
state, no approval gate anywhere in the topology. Every uncertainty becomes one of these
instead, and the operator resolves them after the run.

The four kinds and their operator meanings are proven and transfer as concepts (dossier
03 §8.2); their flat single-list shape is serialization and does not.

Dossier 10 §3 M11: review items are keyed by **domain concept, never by an element
path**. Assembly decides what a value should be; only the filing adapter knows how it is
written. An item that names an XML element has leaked the contract upward.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReviewKind(StrEnum):
    """What the operator has to do about it.

    The four are distinct actions, not severity levels: PLACEHOLDER and OMITTED both
    mean "the filed document is not right yet" but call for opposite fixes, and GUESS
    means the document is filable as-is but may be wrong.
    """

    PLACEHOLDER = "placeholder"
    """A stand-in was filed. Dossier 03 §6: exactly two elements in the whole contract
    are permitted to carry one, and both are party organization names."""

    GUESS = "guess"
    """A value was inferred or defaulted and filed. The operator should confirm it."""

    NEEDS_REVIEW = "needs_review"
    """Filed, but requires a human action — restate a quantity in the right unit,
    confirm a preference, supply a material."""

    OMITTED = "omitted"
    """No schema-valid value existed, so the element was left out entirely and the
    operator fills it on the portal."""


class ReviewItem(BaseModel):
    """One thing a human must look at.

    `concept` is a domain concept name — "line gross weight", "shipment origin country"
    — never an XML element name.
    """

    model_config = ConfigDict(frozen=True)

    kind: ReviewKind
    concept: str = Field(min_length=1)
    detail: str = Field(
        min_length=1,
        description="Free text addressed to the operator: what happened and what to do.",
    )
    line_id: str | None = Field(
        default=None,
        description="The goods line this concerns, or None for shipment-level items.",
    )
    remedy: str | None = Field(
        default=None,
        description="What evidence would resolve it. Dossier 02 §10.3 records this as "
        "the highest-value human-in-the-loop affordance in the product: an abstention "
        "that explains what would resolve it converts a dead end into one more turn.",
    )
