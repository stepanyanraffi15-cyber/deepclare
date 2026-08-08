"""L1 — the existence gate. The outermost layer, and it works on the return.

**No code leaves this module that is absent from the current nomenclature, whatever
produced it.** The picker inside the graph can only choose codes retrieval returned, so
they are real by construction — but every other producer copies a code out of a document
somebody typed. Real stored declarations carry an all-zeros 11-digit filler where nobody
looked a code up, and codes that were valid when they were filed and have since left the
tree. Both pass a length check and a digit check.

On rejection it strips **only the code**. Confidence goes with it, because a confidence
about a code that does not exist is not a smaller confidence, it is a meaningless one;
the supplementary unit goes with it, because it was read off the entry that is not there.
Everything else — the candidates, the material verdicts, the legal basis, the trace —
stays, and the rationale is rewritten to say what happened. The line is flagged.

The gate is cheap enough to run on every code, which is what lets it be unconditional.
"""

from __future__ import annotations

from deepclare.classification.codes import (
    LEAF_DIGITS,
    NATIONAL_DIGITS,
    digits_of,
    leaf_form,
    national_suffix,
)
from deepclare.classification.records import LineClassification
from deepclare.domain import Transform
from deepclare.reference.store import NomenclatureStore

CONCEPT = "commodity code"


class ExistenceGate:
    """Checks whatever the inner layers decided, on its way back out."""

    def __init__(self, store: NomenclatureStore) -> None:
        self._store = store

    def check(self, classification: LineClassification) -> LineClassification:
        """Pass an abstention through; validate a code, or strip it."""
        traced = classification.code
        if traced is None:
            return classification

        given = traced.value
        leaf = leaf_form(given)
        if leaf is None or not self._store.exists(given):
            return _stripped(classification, given, self._why(given))
        if leaf == given:
            return classification
        return _reduced(classification, given, leaf)

    def _why(self, code: str) -> str:
        """The specific reason, because "not in the nomenclature" hides four failures."""
        found = digits_of(code)
        if found != code.strip():
            return "it is not made only of digits"
        if set(found) == {"0"}:
            return (
                "it is a run of zeros, which is what a hand-typed stand-in for a code "
                "looks like and is not a code"
            )
        if len(found) not in (LEAF_DIGITS, NATIONAL_DIGITS):
            return (
                f"it is {len(found)} digits long, and this nomenclature files "
                f"{LEAF_DIGITS}-digit leaves ({NATIONAL_DIGITS} with the national digit)"
            )
        return (
            "no entry of the current nomenclature has that code — it was either never "
            "in this tree or has been retired from it"
        )


def _stripped(
    classification: LineClassification, code: str, why: str
) -> LineClassification:
    return classification.model_copy(
        update={
            "code": None,
            "supplementary_unit": None,
            "needs_review": True,
            "rationale": (
                f"The commodity code {code!r} was not filed because {why}. No code is "
                f"filed for this line. The outcome it replaced was: "
                f"{classification.rationale}"
            ),
            "resolving_evidence": (
                classification.resolving_evidence
                or "A commodity code that exists in the current nomenclature."
            ),
        }
    )


def _reduced(
    classification: LineClassification, given: str, leaf: str
) -> LineClassification:
    """An 11-digit filed code reduced to the 10-digit internal form it names.

    The 11th digit is the Armenian national subdivision and it is appended downstream. It
    is `0` on roughly 98% of filings and the rule is not universally correct: a small
    number of real codes carry a non-zero national digit, and those splits exist in no
    10-digit index. Dropping a non-zero one here and appending `0` there would produce a
    different code than the one that was supplied, so the loss is recorded on the value
    and the line is flagged.
    """
    suffix = national_suffix(given)
    reduced = classification.code.with_transform(  # type: ignore[union-attr]
        Transform(
            operation=f"reduce-{NATIONAL_DIGITS}-to-{LEAF_DIGITS}",
            before=given,
            after=leaf,
            reason="the internal form is the 10-digit leaf; the national digit is "
            "appended when the declaration is written",
        ),
        leaf,
    )
    if suffix == "0":
        return classification.model_copy(update={"code": reduced})
    return classification.model_copy(
        update={
            "code": reduced,
            "needs_review": True,
            "rationale": (
                f"The code was supplied as {given!r}, whose national subdivision digit "
                f"is {suffix!r} rather than 0. This declaration appends 0, so the filed "
                f"code would be {leaf}0 and not the code supplied. Confirm which is "
                f"correct. The outcome it came from was: {classification.rationale}"
            ),
        }
    )
