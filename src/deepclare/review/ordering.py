"""The order the report is read in — stated once, in one place, and used everywhere.

An operator reads a report top to bottom and stops when the working day does. What sits
at the top is therefore a product decision, not a consequence of dictionary order, so the
rule is written here rather than emerging from wherever the items happened to be built.

Four keys, applied in this order:

1. **Scope.** Shipment-level items come before any goods line, because a shipment-level
   value is wrong for every line at once.
2. **Consequence to the filed document.** The four item kinds are distinct operator
   actions rather than severity levels, so their order comes from the product's governing
   asymmetry — *wrong is worse than missing*:

   * `placeholder` — a stand-in is in the document. Something wrong was filed.
   * `omitted` — a value is absent. The operator supplies it on the portal.
   * `needs_review` — filed, and a human action is still outstanding.
   * `guess` — filed and plausible; confirm it.

   A goods line inherits the rank of the most consequential item on it, so the line
   carrying a placeholder is read before the line carrying only a guess. Lines with no
   items at all come last.
3. **The weakest confidence on the value the item concerns**, ascending. Of two guesses,
   the one derived at 0.3 is read before the one derived at 0.9. A value with no assessed
   confidence sorts after assessed ones: nothing is known about it, and nothing known is
   not the same as known to be poor.
4. **The concept name**, so that two runs over the same findings print the same report.

Within a group's provenance table the same rule applies from key 3 down: weakest first.
"""

from __future__ import annotations

from collections.abc import Iterable

from deepclare.domain import Confidence, ReviewKind

CONSEQUENCE_ORDER: tuple[ReviewKind, ...] = (
    ReviewKind.PLACEHOLDER,
    ReviewKind.OMITTED,
    ReviewKind.NEEDS_REVIEW,
    ReviewKind.GUESS,
)
"""The four kinds, most consequential to the filed document first."""

NOTHING_TO_ACT_ON = len(CONSEQUENCE_ORDER)
"""The rank of a group that raised no items. It sorts after every kind."""

ORDERING_RULE = (
    "Ordered: shipment level before goods lines; then by consequence to the filed "
    "document (placeholder, omitted, needs review, guess — wrong is worse than "
    "missing); then weakest confidence first; then by concept name."
)
"""One sentence, printed at the head of the report so the order is legible to whoever
reads it and not merely to whoever wrote it."""


def kind_rank(kind: ReviewKind) -> int:
    """How consequential this kind is to the filed document. Lower is read first."""
    return CONSEQUENCE_ORDER.index(kind)


def worst_kind(kinds: Iterable[ReviewKind]) -> ReviewKind | None:
    """The most consequential kind present, or None when there are no items."""
    present = sorted(kinds, key=kind_rank)
    return present[0] if present else None


def confidence_rank(confidence: Confidence | None) -> tuple[int, float]:
    """Weakest assessed confidence first; unassessed after everything assessed."""
    lowest = confidence.lowest if confidence is not None else None
    if lowest is None:
        return (1, 0.0)
    return (0, lowest)


def scope_rank(line_id: str | None) -> tuple[int, int, str]:
    """Shipment level, then numbered lines in numeric order, then anything else.

    Line ids are positional numbers, so `"10"` must not sort before `"2"`. An id that is
    not a number is not rejected here — the review surface presents what it is given —
    it simply sorts last among the lines, by text.
    """
    if line_id is None:
        return (0, 0, "")
    if line_id.isdigit():
        return (1, int(line_id), "")
    return (2, 0, line_id)


def group_sort_key(
    line_id: str | None, kinds: Iterable[ReviewKind]
) -> tuple[int, int, int, str]:
    """Scope first, then the most consequential item in the group, then the line order."""
    scope, number, text = scope_rank(line_id)
    worst = worst_kind(kinds)
    rank = NOTHING_TO_ACT_ON if worst is None else kind_rank(worst)
    return (scope, rank, number, text)


def item_sort_key(
    kind: ReviewKind, concept: str, confidence: Confidence | None
) -> tuple[int, int, float, str]:
    """Consequence, then the weakest confidence on the value it concerns, then name."""
    assessed, lowest = confidence_rank(confidence)
    return (kind_rank(kind), assessed, lowest, concept)


def value_sort_key(concept: str, confidence: Confidence) -> tuple[int, float, str]:
    """The provenance table: weakest confidence first, then name."""
    assessed, lowest = confidence_rank(confidence)
    return (assessed, lowest, concept)
