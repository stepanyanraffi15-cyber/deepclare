"""What is known about this corpus that changes how its numbers must be read.

Two facts, both measured, both of which make agreement with the corpus something other
than a correctness score. They live here rather than in a comment because the report
prints them: a number quoted without them says more than the evidence supports.
"""

from __future__ import annotations

CODES_ABSENT_FROM_NOMENCLATURE: frozenset[str] = frozenset(
    {"39069090090", "39100000090"}
)
"""Commodity codes the corpus labels goods with that do not exist.

The classification stack refuses a code that is not in the tree — that gate is the whole
reason a wrong code is rarer than a missing one — so on a line carrying one of these the
system's correct behaviour is to abstain, and abstaining scores as a miss. Ten of the
corpus's 2,842 goods lines carry one. Left in the aggregate they depress it silently, so
they are counted out of it and reported on their own."""

CODES_ABSENT_PROVENANCE = (
    "Measured over all 2,842 goods lines of the corpus against the nomenclature "
    "artifact and, for the residue, against the authority's own API: 2,832 codes "
    "resolve, these two do not. The corpus is synthetic, so they are generator "
    "artifacts rather than retired codes."
)

SYNTHETIC_LABEL_CAVEAT = (
    "The corpus is synthetic: fictional parties, recombined baskets, and commodity "
    "codes chosen by the generator rather than filed by a broker and accepted by the "
    "authority. Agreement with it measures agreement with the generator. It is not "
    "customs correctness, and a line where this system and the label disagree is not "
    "automatically a line this system got wrong — one examined closely had the label "
    "on an incandescent-lamp code and the system on the halogen code the goods "
    "actually described."
)

DESCRIPTION_LANGUAGE_CAVEAT = (
    "Description scores compare Armenian text to Armenian text with chrF, a character "
    "n-gram F-score. It reads inflection and word order more fairly than a token "
    "metric does, and it still cannot tell a correct description from a fluent wrong "
    "one. The attribute rubric is the part that checks something a broker would check."
)


def is_unresolvable(code: str) -> bool:
    """Whether a labelled code is one the nomenclature cannot contain."""
    return "".join(ch for ch in code if ch.isdigit()) in CODES_ABSENT_FROM_NOMENCLATURE
