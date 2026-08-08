"""Attaching the account to a value, and collecting what a human must confirm.

Dossier 10 §3 M13 states the rule this module exists to keep: provenance and confidence
are attached **at the point of production**, by the producing module, because the review
surface cannot reconstruct them afterwards. Assembly produces a great many values — every
distributed weight, every resolved unit, every computed piece total — and each one gets
its account here rather than at whatever call site happened to compute it.

The confidence numbers are **bands, not measurements**. Nothing in this system has
calibrated them and they must not be read as probabilities. They exist so the review
surface can rank what a human should look at first, and their only real content is their
order: read verbatim beats computed from two printed factors beats distributed across
lines beats defaulted because nothing else resolved.
"""

from __future__ import annotations

from typing import Any, TypeVar

from deepclare.domain import (
    Confidence,
    Provenance,
    ReviewItem,
    ReviewKind,
    Traced,
    Transform,
    ValueOrigin,
)

STAGE = "assembly"
"""What every value produced here names as its producing stage."""

VERBATIM = 0.95
"""A printed value carried through unchanged, or arithmetic on printed values alone."""

COMPUTED = 0.75
"""A figure derived by a rule from grounded inputs — a piece total, a package count."""

DISTRIBUTED = 0.45
"""A share of a shipment total apportioned across lines. Sound in sum, uncertain per
line, and the broker's own reconciliation rather than a measurement."""

COARSE = 0.35
"""A stand-in from a rule of thumb rather than from this shipment's own numbers — the
nine-tenths net-of-gross ratio is the only one."""

DEFAULTED = 0.2
"""Nothing resolved and a default was filed. The weakest thing this module produces."""


T = TypeVar("T")


def derived(
    value: T, rule: str, confidence: float, transforms: tuple[Transform, ...] = ()
) -> Traced[T]:
    """A value this module computed, with the rule that computed it."""
    return Traced[Any](
        value=value,
        provenance=Provenance(
            origin=ValueOrigin.DERIVED, stage=STAGE, rule=rule, transforms=transforms
        ),
        confidence=Confidence(derivation=confidence),
    )


def supplied(value: T, by: str) -> Traced[T]:
    """A value from the declarant profile or configuration, not from any document."""
    return Traced[Any](
        value=value,
        provenance=Provenance(origin=ValueOrigin.SUPPLIED, stage=STAGE, supplied_by=by),
        confidence=Confidence(derivation=VERBATIM),
    )


def constant(value: T, what: str) -> Traced[T]:
    """A value fixed by the jurisdiction rather than chosen. Never uncertain."""
    return Traced[Any](
        value=value,
        provenance=Provenance(origin=ValueOrigin.CONSTANT, stage=STAGE, rule=what),
        confidence=Confidence(derivation=1.0, validity=1.0),
    )


def restated(source: Traced[Any], value: T, transform: Transform) -> Traced[T]:
    """The same value in a different form, keeping the chain back to the ink.

    Used where a printed figure is converted rather than replaced — tonnes into
    kilograms, a ten-digit leaf into the eleven-digit filed code. The provenance stays
    the source's, because the value is still that document's value.
    """
    return Traced[Any](
        value=value,
        provenance=source.provenance.model_copy(
            update={"transforms": source.provenance.transforms + (transform,)}
        ),
        confidence=source.confidence,
    )


def transform(operation: str, before: object, after: object, reason: str) -> Transform:
    return Transform(
        operation=operation, before=str(before), after=str(after), reason=reason
    )


class Review:
    """Everything the run must tell a human, in the order it was found.

    A plain accumulator on purpose. The four kinds are four different operator actions,
    not severity levels, and every method below names the action rather than a level.

    `concept` is a domain concept — "line gross weight", "shipment origin country". An
    element name here has leaked the filing contract upward, which the review surface
    detects and reports as a defect in the report itself.
    """

    def __init__(self) -> None:
        self._items: list[ReviewItem] = []

    def guess(
        self, concept: str, detail: str, *, line_id: str | None = None, remedy: str | None = None
    ) -> None:
        """A value was inferred or defaulted and filed. Confirm it."""
        self._add(ReviewKind.GUESS, concept, detail, line_id, remedy)

    def needs_review(
        self, concept: str, detail: str, *, line_id: str | None = None, remedy: str | None = None
    ) -> None:
        """Filed, and a human has to act on it before it is right."""
        self._add(ReviewKind.NEEDS_REVIEW, concept, detail, line_id, remedy)

    def omitted(
        self, concept: str, detail: str, *, line_id: str | None = None, remedy: str | None = None
    ) -> None:
        """No sound value existed, so nothing was filed and the operator fills it in."""
        self._add(ReviewKind.OMITTED, concept, detail, line_id, remedy)

    def placeholder(
        self, concept: str, detail: str, *, line_id: str | None = None, remedy: str | None = None
    ) -> None:
        """A stand-in was filed. Only two leaves in the whole contract tolerate one."""
        self._add(ReviewKind.PLACEHOLDER, concept, detail, line_id, remedy)

    def _add(
        self,
        kind: ReviewKind,
        concept: str,
        detail: str,
        line_id: str | None,
        remedy: str | None,
    ) -> None:
        self._items.append(
            ReviewItem(
                kind=kind, concept=concept, detail=detail, line_id=line_id, remedy=remedy
            )
        )

    @property
    def items(self) -> tuple[ReviewItem, ...]:
        return tuple(self._items)
