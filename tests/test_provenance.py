"""The transform chain: append-only, and it cannot change what a value is."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from deepclare.domain import Confidence, Provenance, Traced, Transform, ValueOrigin

EXTRACTED = Provenance(origin=ValueOrigin.EXTRACTED, source_document_id="doc1")


def transform(before: str, after: str) -> Transform:
    return Transform(operation="strip-spaces-uppercase", before=before, after=after)


def test_a_transform_is_appended_and_the_value_replaced() -> None:
    plate = Traced[str](
        value="12 Ab 345", provenance=EXTRACTED, confidence=Confidence(extraction=0.8)
    )
    normalized = plate.with_transform(transform("12 Ab 345", "12AB345"), "12AB345")
    assert normalized.value == "12AB345"
    assert len(normalized.provenance.transforms) == 1
    assert normalized.confidence == plate.confidence
    assert plate.provenance.transforms == (), "the original must be untouched"


def test_the_chain_accumulates() -> None:
    once = Traced[str](value="a", provenance=EXTRACTED).with_transform(
        transform("a", "b"), "b"
    )
    twice = once.with_transform(transform("b", "c"), "c")
    assert [t.after for t in twice.provenance.transforms] == ["b", "c"]


def test_a_transform_cannot_change_the_type_of_the_value() -> None:
    """A string that became a number would otherwise be recorded as though it were fine."""
    plate = Traced[str](value="12AB345", provenance=EXTRACTED)
    with pytest.raises(ValidationError):
        plate.with_transform(transform("12AB345", "12"), 12)  # type: ignore[arg-type]


def test_the_parametrisation_survives_the_transform() -> None:
    weight = Traced[Decimal](value=Decimal("1.5"), provenance=EXTRACTED)
    rounded = weight.with_transform(transform("1.5", "2"), Decimal("2"))
    assert isinstance(rounded.value, Decimal)
    assert type(rounded) is type(weight)


def test_an_origin_must_carry_what_it_implies() -> None:
    with pytest.raises(ValidationError, match="source document"):
        Provenance(origin=ValueOrigin.EXTRACTED)
    with pytest.raises(ValidationError, match="rule"):
        Provenance(origin=ValueOrigin.DERIVED)
    with pytest.raises(ValidationError, match="prompt"):
        Provenance(origin=ValueOrigin.GENERATED)


def test_the_weakest_confidence_is_what_ranks_a_review() -> None:
    assert Confidence(extraction=0.9, derivation=0.4).lowest == 0.4
    assert Confidence().lowest is None
