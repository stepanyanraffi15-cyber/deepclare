"""Every branch in the outer chain, with its exact condition, in one place.

Dossier 02 §6.1 is a table of edges and conditions. This module is that table as code: a
condition is a named predicate with the specification's own wording beside it, and the
chain in `pipeline` references these rather than restating any of them. A branch buried
in a node body is a branch nobody can enumerate, and the first question asked of a
pipeline is always "what did it skip, and why".

Three edges of the specification's table are absent because the stages behind them are
absent from this product:

* **A13, the prior-filing matcher**, and **A16, the foreign-text reuse probe** — customer-
  history reuse was removed deliberately. There is no port, so there is no branch.
* **A2 → A6 direct read**, "no page classifier configured, each file read whole by its
  routed role". It survives, but not as an edge that skips the grouper: with no classifier
  there are simply no verdicts, and the grouper's own rule — no verdict leaves a page on
  its file's role — produces exactly the direct read. One code path, one policy, and the
  over-inclusion rule cannot be bypassed by a configuration.

The remaining reject edges are not here because they are not branches: intake, grouping
and the completeness guard raise, and a raise is not a path through the graph.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from deepclare.intake.formats import is_page_bearing
from deepclare.run.ports import Ports
from deepclare.run.state import RunState


@dataclass(frozen=True)
class Branch:
    """One conditional edge: what decides it, and what each answer means."""

    name: str
    condition: str
    """The condition in the specification's own terms, so the code and the table can be
    read against each other without a translation step."""

    when_true: str
    when_false: str
    decide: Callable[[RunState, Ports], bool]

    def holds(self, state: RunState, ports: Ports) -> bool:
        return self.decide(state, ports)


# --- the predicates -------------------------------------------------------------------


def _invoice_has_pages(state: RunState, ports: Ports) -> bool:
    """Dossier 02 §6.1, A2: a workbook has no pages to pool, so it is unambiguously the
    invoice and is read directly rather than rasterized, classified and grouped."""
    return is_page_bearing(state.require_routed().invoice.file_format)


def _page_classifier_configured(state: RunState, ports: Ports) -> bool:
    """Dossier 02 §6.1, A2 → A3: the segmentation path needs a classifier to segment
    with. Without one the pages are still rendered and still grouped; they simply carry
    no verdict, and every page stays on its source file's role."""
    return ports.page_classifier is not None


def _consignment_note_present(state: RunState, ports: Ports) -> bool:
    """Dossier 02 §6.1, A5 → A6: the consignment note is extracted **only if at least one
    page was classified as one**. The grouper reports that by producing the document."""
    return state.require_grouped().consignment_note is not None


def _evidence_can_be_read(state: RunState, ports: Ports) -> bool:
    """Dossier 02 §6.1, A15 branch → A14: an evidence resolver is configured **and** there
    is at least one evidence document. The specification's "or a non-blank note" half has
    no subject here — this product takes no free-text note with a submission."""
    return (
        ports.evidence_enricher is not None
        and state.grouped is not None
        and len(state.grouped.supporting_evidence) > 0
    )


def _reconciler_configured(state: RunState, ports: Ports) -> bool:
    """Dossier 02 §6.1, A20 → A21: cross-line reconciliation runs when a harmonizer is
    configured, and the drafted lines are filed untouched when it is not. The pass is
    best-effort in both directions: every one of its own failure paths returns the lines
    exactly as they arrived, so it can never be the reason a run fails."""
    return ports.reconciler is not None


# --- the table ------------------------------------------------------------------------

INVOICE_HAS_PAGES = Branch(
    name="invoice media type",
    condition="the invoice's format carries pages",
    when_true="rasterize, classify and group its pages",
    when_false="read the workbook directly — no pages to pool",
    decide=_invoice_has_pages,
)

PAGE_CLASSIFIER_CONFIGURED = Branch(
    name="page classifier configured",
    condition="a page-type classifier port was injected",
    when_true="classify the whole page batch in one call",
    when_false="no verdicts; every page keeps its source file's role",
    decide=_page_classifier_configured,
)

CONSIGNMENT_NOTE_PRESENT = Branch(
    name="consignment note present",
    condition="at least one page was grouped as a consignment note",
    when_true="read it, for weights, transport and packaging",
    when_false="the declaration is drafted from the invoice alone",
    decide=_consignment_note_present,
)

EVIDENCE_CAN_BE_READ = Branch(
    name="evidence enrichable",
    condition="an evidence enricher is configured and evidence documents were grouped",
    when_true="fill line gaps from the supporting documents",
    when_false="stage skipped; any evidence is carried but not read",
    decide=_evidence_can_be_read,
)

RECONCILER_CONFIGURED = Branch(
    name="harmonizer configured",
    condition="a cross-line reconciler port was injected",
    when_true="critique the drafted lines, then conform them",
    when_false="stage skipped; the drafted lines pass through untouched",
    decide=_reconciler_configured,
)

BRANCHES = (
    INVOICE_HAS_PAGES,
    PAGE_CLASSIFIER_CONFIGURED,
    CONSIGNMENT_NOTE_PRESENT,
    EVIDENCE_CAN_BE_READ,
    RECONCILER_CONFIGURED,
)


def describe_branches() -> str:
    """The branch table, printable without running anything."""
    lines = ["branch                     condition -> yes / no"]
    for branch in BRANCHES:
        lines.append(f"  {branch.name}")
        lines.append(f"      when   {branch.condition}")
        lines.append(f"      yes    {branch.when_true}")
        lines.append(f"      no     {branch.when_false}")
    return "\n".join(lines)
