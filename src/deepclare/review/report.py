"""The structured report: everything a human must look at, grouped and ordered.

The report is assembled from two streams and nothing else — the review items every
module raised, and the values those modules produced with the account attached to each.
Nothing here computes a value, re-checks a rule, or decides anything about the
declaration. Where a number appears in this report, some other module put it there.

Items and values join on the pair *(domain concept, goods line)*. That join is the
reason the keying rule matters beyond tidiness: an item that named an XML element could
not be joined to the value it is about, because the value does not know its element name
and never will.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from deepclare.domain import ReviewItem, ReviewKind, ValueOrigin
from deepclare.review.defects import ReportDefect, defects_in_item, defects_in_value
from deepclare.review.ordering import (
    CONSEQUENCE_ORDER,
    group_sort_key,
    item_sort_key,
    scope_rank,
    value_sort_key,
    worst_kind,
)
from deepclare.review.values import ReportedValue

INFERRED_ORIGINS = (ValueOrigin.DERIVED, ValueOrigin.GENERATED)
"""What "inferred" means on a line flag: nobody read this off a page. It was computed by
a rule or written by a model, and the operator is being told which."""


class ReviewEntry(BaseModel):
    """One review item, next to the value it concerns.

    `value` is None when no value was reported under that concept — which is the normal
    case for an omission, where the point is that there is no value.
    """

    model_config = ConfigDict(frozen=True)

    item: ReviewItem
    value: ReportedValue | None = None


class Abstention(BaseModel):
    """A value the system declined to supply, and why.

    Not a failure to be tidied away: an abstention that says what would resolve it turns
    a dead end into one more turn, and it is the reason the omission kind exists.
    """

    model_config = ConfigDict(frozen=True)

    concept: str
    rationale: str
    remedy: str | None = None


class ReviewFlags(BaseModel):
    """The summary a client renders beside a goods line to decide what to verify.

    Every field is a projection of the items and values already in the group. Nothing is
    counted, recomputed or inferred here — `inferred` reports which values *say* they
    were inferred, by reading the origin their producer attached.

    There is deliberately no reused-from-history flag. The predecessor's single exposed
    provenance distinction was "this came from your own prior filing, verification
    skippable"; this product has no reuse path, so the flag would be a claim about
    something that does not exist.
    """

    model_config = ConfigDict(frozen=True)

    line_id: str | None = None
    needs_review: bool = False
    most_consequential: ReviewKind | None = None
    """The rank the group was sorted on, so a client can badge the line the same way."""

    inferred: tuple[str, ...] = ()
    """Concepts on this line that were computed or written rather than read."""

    abstentions: tuple[Abstention, ...] = ()


class ReviewGroup(BaseModel):
    """Everything about one goods line, or about the shipment as a whole."""

    model_config = ConfigDict(frozen=True)

    line_id: str | None = None
    """None is the shipment level, not a missing line."""

    entries: tuple[ReviewEntry, ...] = ()
    values: tuple[ReportedValue, ...] = ()
    """Every value reported in this group, weakest confidence first — the provenance
    table an operator reads when an item sends them to check something."""

    flags: ReviewFlags = ReviewFlags()


class KindTally(BaseModel):
    """How many items of one kind the run raised."""

    model_config = ConfigDict(frozen=True)

    kind: ReviewKind
    count: int = Field(ge=0)


class ReviewReport(BaseModel):
    """The human-facing account of one run."""

    model_config = ConfigDict(frozen=True)

    defects: tuple[ReportDefect, ...] = ()
    """Faults in the account itself, not in the declaration. They are listed first
    because they say how far the rest of the report can be trusted."""

    groups: tuple[ReviewGroup, ...] = ()
    tallies: tuple[KindTally, ...] = ()
    """All four kinds, always, in consequence order. A zero is information."""

    @property
    def total_items(self) -> int:
        return sum(tally.count for tally in self.tallies)

    @property
    def line_count(self) -> int:
        return sum(1 for group in self.groups if group.line_id is not None)


def build_report(
    items: Sequence[ReviewItem], values: Sequence[ReportedValue] = ()
) -> ReviewReport:
    """Assemble the report from what the run produced.

    Both arguments are what other modules made: this function groups, joins, orders and
    counts them, and does nothing else to them.
    """
    items_by_line = _by_line(items)
    values_by_line = _by_line(values)

    groups = [
        _group(line_id, items_by_line.get(line_id, ()), values_by_line.get(line_id, ()))
        for line_id in set(items_by_line) | set(values_by_line)
    ]
    groups.sort(
        key=lambda group: group_sort_key(
            group.line_id, [entry.item.kind for entry in group.entries]
        )
    )

    defects = [defect for item in items for defect in defects_in_item(item)]
    defects += [defect for value in values for defect in defects_in_value(value)]
    defects.sort(key=lambda defect: (*scope_rank(defect.line_id), defect.concept))

    return ReviewReport(
        defects=tuple(defects),
        groups=tuple(groups),
        tallies=_tallies(items),
    )


class _LineScoped(Protocol):
    """Anything the report groups. Items and values are both scoped the same way."""

    @property
    def line_id(self) -> str | None: ...


def _by_line[T: _LineScoped](records: Iterable[T]) -> dict[str | None, tuple[T, ...]]:
    grouped: dict[str | None, list[T]] = defaultdict(list)
    for record in records:
        grouped[record.line_id].append(record)
    return {line_id: tuple(records) for line_id, records in grouped.items()}


def _group(
    line_id: str | None, items: Sequence[ReviewItem], values: Sequence[ReportedValue]
) -> ReviewGroup:
    # Two values reported under one concept on one line means two producers wrote the
    # same thing, which the provenance table below shows in full. The join takes the
    # first so that the entry shows a value rather than none.
    by_concept: dict[str, ReportedValue] = {}
    for value in values:
        by_concept.setdefault(value.concept, value)

    entries = [
        ReviewEntry(item=item, value=by_concept.get(item.concept)) for item in items
    ]
    entries.sort(
        key=lambda entry: item_sort_key(
            entry.item.kind,
            entry.item.concept,
            entry.value.confidence if entry.value else None,
        )
    )

    ordered_values = sorted(
        values, key=lambda value: value_sort_key(value.concept, value.confidence)
    )
    return ReviewGroup(
        line_id=line_id,
        entries=tuple(entries),
        values=tuple(ordered_values),
        flags=_flags(line_id, entries, ordered_values),
    )


def _flags(
    line_id: str | None,
    entries: Sequence[ReviewEntry],
    values: Sequence[ReportedValue],
) -> ReviewFlags:
    return ReviewFlags(
        line_id=line_id,
        needs_review=bool(entries),
        most_consequential=worst_kind(entry.item.kind for entry in entries),
        inferred=tuple(
            value.concept
            for value in values
            if value.provenance.origin in INFERRED_ORIGINS
        ),
        abstentions=tuple(
            Abstention(
                concept=entry.item.concept,
                rationale=entry.item.detail,
                remedy=entry.item.remedy,
            )
            for entry in entries
            if entry.item.kind is ReviewKind.OMITTED
        ),
    )


def _tallies(items: Sequence[ReviewItem]) -> tuple[KindTally, ...]:
    return tuple(
        KindTally(kind=kind, count=sum(1 for item in items if item.kind is kind))
        for kind in CONSEQUENCE_ORDER
    )
