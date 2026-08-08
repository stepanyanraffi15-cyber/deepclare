"""Where a value came from, how much to trust it, and what was done to it on the way.

Dossier 10 §4 invariant 1: every value carries provenance, graded confidence, and its
transform chain, attached **where it is produced**. Dossier 10 §3 M13 makes the
consequence explicit — the review surface cannot reconstruct any of this afterwards, so
a value that arrives without it is a defect at its producer, not something to paper over
downstream.

Dossier 03 §8.2 is the reason confidence is three numbers rather than one. The
predecessor conflated them into a single flag vocabulary, which cannot answer three
different questions:

  * extraction  — was it read correctly off the page?
  * derivation  — is the inference that produced it sound?
  * validity    — will the external customs system accept it?

A value can be read perfectly, derived soundly, and still be rejected on filing.

This module knows nothing about XML, storage, transport, or any model. It is
definitional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ValueOrigin(StrEnum):
    """The kind of act that produced a value.

    These are distinct because the review surface treats them differently and because
    the transform chain means something different for each.
    """

    EXTRACTED = "extracted"
    """Read off a source document. Carries document, page and region."""

    DERIVED = "derived"
    """Computed by a deterministic rule from other values. Carries stage and rule."""

    GENERATED = "generated"
    """Written by a model rather than read or computed. Carries stage and prompt."""

    REUSED = "reused"
    """Copied from one of the tenant's own prior filings. Carries the source record."""

    SUPPLIED = "supplied"
    """Came from the declarant profile or configuration, not from any document."""

    CONSTANT = "constant"
    """Fixed by the jurisdiction or the filing contract. Never uncertain."""


class DocumentRegion(BaseModel):
    """Where on a page a value was read from.

    Coordinates are fractions of page width and height so they survive rescaling.
    Dossier 03 §8.1 records that the predecessor kept per-page text structure "so later
    stages can cite provenance" but that no downstream field ever recorded which page or
    region it came from. This type exists so that gap does not repeat.
    """

    model_config = ConfigDict(frozen=True)

    page_number: int = Field(ge=1, description="1-based, within the logical document")
    left: float | None = Field(default=None, ge=0.0, le=1.0)
    top: float | None = Field(default=None, ge=0.0, le=1.0)
    right: float | None = Field(default=None, ge=0.0, le=1.0)
    bottom: float | None = Field(default=None, ge=0.0, le=1.0)


class Transform(BaseModel):
    """One normalization applied between the ink on the page and the filed value.

    Dossier 03 §8.2 requires the ordered list of these so that any filed value can be
    traced back to what was printed. Each entry says what was done and what it did.
    """

    model_config = ConfigDict(frozen=True)

    operation: str = Field(min_length=1, description="e.g. 'uppercase', 'truncate-50'")
    before: str
    after: str
    reason: str | None = Field(
        default=None,
        description="Why the transform was necessary, when that is not obvious from "
        "the operation — typically a contract constraint.",
    )


class Confidence(BaseModel):
    """Three graded confidences, because one number cannot answer three questions.

    Each is in [0, 1]. `None` means "not assessed", which is honest and distinct from
    zero. A constant, for instance, has no meaningful extraction confidence.
    """

    model_config = ConfigDict(frozen=True)

    extraction: float | None = Field(default=None, ge=0.0, le=1.0)
    derivation: float | None = Field(default=None, ge=0.0, le=1.0)
    validity: float | None = Field(default=None, ge=0.0, le=1.0)

    @property
    def lowest(self) -> float | None:
        """The weakest link, for ranking what a human should look at first."""
        assessed = [c for c in (self.extraction, self.derivation, self.validity)
                    if c is not None]
        return min(assessed) if assessed else None


class Provenance(BaseModel):
    """The full account of where one value came from.

    Which fields are populated depends on `origin`; the validator enforces the pairings
    that matter rather than leaving them to convention.
    """

    model_config = ConfigDict(frozen=True)

    origin: ValueOrigin

    # Extracted values: which upload, which page, which region.
    source_document_id: str | None = None
    source_document_role: str | None = None
    region: DocumentRegion | None = None

    # Derived and generated values: which stage, and which rule or prompt.
    stage: str | None = None
    rule: str | None = Field(
        default=None,
        description="For derived values, the named rule — e.g. "
        "'gross distributed from consignment-note total by quantity share'.",
    )
    prompt_name: str | None = None
    prompt_version: str | None = None

    # Reused values: which prior filing.
    source_filing_id: str | None = None

    # Supplied values: which part of the profile or configuration.
    supplied_by: str | None = None

    transforms: tuple[Transform, ...] = ()

    @model_validator(mode="after")
    def _require_the_fields_the_origin_implies(self) -> Self:
        if self.origin is ValueOrigin.EXTRACTED and not self.source_document_id:
            raise ValueError("an extracted value must name its source document")
        if self.origin is ValueOrigin.DERIVED and not self.rule:
            raise ValueError("a derived value must name the rule that produced it")
        if self.origin is ValueOrigin.GENERATED and not self.prompt_name:
            raise ValueError("a generated value must name the prompt that wrote it")
        if self.origin is ValueOrigin.REUSED and not self.source_filing_id:
            raise ValueError("a reused value must name the filing it came from")
        if self.origin is ValueOrigin.SUPPLIED and not self.supplied_by:
            raise ValueError("a supplied value must name what supplied it")
        return self


T = TypeVar("T")


class Traced(BaseModel, Generic[T]):
    """A value together with the account of where it came from.

    Every field that reaches the declaration is wrapped in one of these. The generic
    earns itself here: the wrapper is identical for strings, decimals, codes and dates,
    and there are dozens of concrete instantiations across the field model.
    """

    model_config = ConfigDict(frozen=True)

    value: T
    provenance: Provenance
    confidence: Confidence = Confidence()

    def with_transform(self, transform: Transform, new_value: T) -> Traced[T]:
        """Return a new traced value, recording the step that changed it.

        The chain is append-only: a filed value can always be walked back to the ink.
        """
        return Traced[T](
            value=new_value,
            provenance=self.provenance.model_copy(
                update={"transforms": self.provenance.transforms + (transform,)}
            ),
            confidence=self.confidence,
        )
