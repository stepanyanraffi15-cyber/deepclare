"""How a case becomes declaration XML — the one thing the harness does not decide.

A producer takes a case's input paths and returns the declaration XML for it, as text.
That is the whole contract. The pipeline is one producer. Reading a file a previous run
emitted is another, and is the one shipped here, because it lets the harness be run and
verified before any pipeline exists: point it at each case's own ground truth and every
number must come out perfect.

A producer raises `ProductionFailed` when it cannot produce a declaration for a case.
The harness records that against the case and keeps going — seventy cases of real model
calls must not be lost to the seventy-first — but a failed case is never silently
dropped: it is counted, listed with its reason, and it keeps the run from being reported
as complete.
"""

from __future__ import annotations

from collections.abc import Callable

from deepclare.evaluation.cases import CaseInputs

DeclarationProducer = Callable[[CaseInputs], str]
"""Case in, declaration XML out."""


class ProductionFailed(RuntimeError):
    """No declaration could be produced for this case, for the stated reason."""


def emitted_file(filename: str) -> DeclarationProducer:
    """A producer that reads an XML file a previous run already wrote into the case.

    `python -m deepclare.evaluation ... --from-file ground_truth.xml` turns this into
    the harness's own self-check: scoring each case's truth against itself must be
    perfect on every metric, and anything less is a defect in the harness rather than
    a finding about the product.
    """

    def produce(case: CaseInputs) -> str:
        path = case.directory / filename
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProductionFailed(f"{path} could not be read: {exc}") from exc

    return produce
