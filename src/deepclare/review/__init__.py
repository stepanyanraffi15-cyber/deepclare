"""M13 Review Surface — the human-facing account of a run.

In: the review items every module raised, and the values those modules produced, each
carrying the provenance and the three graded confidences its producer attached.
Out: a structured report grouped by goods line and ordered by consequence, the per-value
provenance behind it, and the per-line flags a client uses to decide what to verify.

**Must not know about:** how to compute any value, the filed document's serialization, or
the transport that carries the report. It aggregates and presents; it never derives.

Three rules govern the module:

1. **It never produces a value.** Every number, every code and every confidence in a
   report was put there by the module that made it. Nothing here recomputes, re-checks,
   rounds or fills anything, because a review surface that can disagree with the
   declaration is a second implementation of the declaration.

2. **Provenance and confidence are attached at the point of production.** They cannot be
   reconstructed afterwards, so a value that arrives without what its origin implies is
   a defect at its producer. It is reported as one, in the producer's name, and the value
   is still shown — the alternative is inventing a plausible number and printing it in a
   document a human trusts.

3. **Items and values are keyed by domain concept, never by an element path.** Only the
   filing adapter knows how a value is written. Concept keying is also what lets an item
   join to the value it concerns, which is how an item can show its own confidence.

The ordering rule is stated once, in `ordering`, and printed at the head of every
rendered report: shipment level before goods lines; then consequence to the filed
document, which follows the product's governing asymmetry that wrong is worse than
missing; then weakest confidence first; then concept name, so the same findings always
print the same report.

There is no reused-from-history flag. It was the predecessor's one exposed provenance
distinction and this product has no reuse path, so the flag would assert something that
cannot happen.
"""

from deepclare.review.defects import ReportDefect
from deepclare.review.ordering import CONSEQUENCE_ORDER, ORDERING_RULE
from deepclare.review.render import render_report
from deepclare.review.report import (
    Abstention,
    KindTally,
    ReviewEntry,
    ReviewFlags,
    ReviewGroup,
    ReviewReport,
    build_report,
)
from deepclare.review.values import ReportedValue, reported

__all__ = [
    "CONSEQUENCE_ORDER",
    "ORDERING_RULE",
    "Abstention",
    "KindTally",
    "ReportDefect",
    "ReportedValue",
    "ReviewEntry",
    "ReviewFlags",
    "ReviewGroup",
    "ReviewReport",
    "build_report",
    "render_report",
    "reported",
]
