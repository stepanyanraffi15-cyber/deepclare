"""The outer chain: sequential code behind injected ports.

Dossier 02 §12 recommends exactly this shape and gives the reason. A graph framework earns
its place where there is genuine conditional traversal with a loop and a structural guard —
and there is exactly one such thing in this system, the per-line Code Assignment graph,
which is already declared as a graph inside the classification package. The outer chain has
no cycle, no fan-out and no join. Expressed as a framework graph it would be a straight
line of nodes with the framework's ceremony around it; expressed as a list of functions it
is a straight line of nodes that reads as one.

What the chain does keep from the graph description is the part that matters: every node
is named, every conditional edge is a declared `Branch`, and the whole topology can be
printed without running it. `describe_chain()` is that printout, and it is the thing to
read against dossier 02 §2 and §6.1.

Two properties hold for every node, and both are enforced by the shape rather than by
discipline:

* **A node is a function of the state before it.** The state is frozen, so a node returns
  the next one; nothing mutates a shared object and no node's effect depends on when it
  ran relative to a node it does not follow.
* **A node reaches for nothing.** Every capability arrives in `Ports`, so the whole chain
  runs with no network, no authentication, no job store and no persistence present.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from deepclare.run import stages
from deepclare.run.conditions import (
    CONSIGNMENT_NOTE_PRESENT,
    EVIDENCE_CAN_BE_READ,
    INVOICE_HAS_PAGES,
    PAGE_CLASSIFIER_CONFIGURED,
    RECONCILER_CONFIGURED,
    Branch,
)
from deepclare.run.ports import Ports
from deepclare.run.state import RunInput, RunState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Node:
    """One stage of the chain, with every condition attached to it."""

    name: str
    run: Callable[[RunState, Ports], RunState]
    spec: str
    """The node's identifier in dossier 02 §3, so the two can be read together."""

    gate: tuple[Branch, ...] = ()
    """Conditions that must all hold for the node to run at all. A node whose gate fails
    is skipped and the run continues — these are the specification's "stage skipped"
    edges, never its reject edges."""

    decides: tuple[Branch, ...] = field(default_factory=tuple)
    """Branches the node takes *inside* itself, because both answers do work rather than
    one of them skipping. Declared here so the printed topology is complete."""


CHAIN: tuple[Node, ...] = (
    Node("intake", stages.intake, "A1+A2"),
    Node("rasterize", stages.rasterize, "A3", gate=(INVOICE_HAS_PAGES,)),
    Node(
        "classify pages",
        stages.classify_pages,
        "A4",
        gate=(INVOICE_HAS_PAGES, PAGE_CLASSIFIER_CONFIGURED),
    ),
    Node("group pages", stages.group_pages, "A5", gate=(INVOICE_HAS_PAGES,)),
    Node(
        "read documents",
        stages.read_documents,
        "A6",
        decides=(INVOICE_HAS_PAGES, CONSIGNMENT_NOTE_PRESENT),
    ),
    Node("goods gate", stages.gate_goods_lines, "A12"),
    Node(
        "enrich evidence",
        stages.enrich_evidence,
        "A14",
        decides=(EVIDENCE_CAN_BE_READ,),
    ),
    Node("build line contexts", stages.build_contexts, "A15"),
    Node("write descriptions", stages.write_descriptions, "A17"),
    Node("classify lines", stages.classify_lines, "A18"),
    Node("completeness guard", stages.guard_completeness, "A19"),
    Node("assemble lines", stages.assemble_lines, "A20"),
    Node(
        "reconcile lines",
        stages.reconcile_lines,
        "A21+A22",
        decides=(RECONCILER_CONFIGURED,),
    ),
    Node("assemble declaration", stages.assemble_declaration, "A23"),
    Node("write filing", stages.write_filing, "A23"),
    Node("build review report", stages.build_review_report, "A24"),
)
"""The whole outer chain, in order.

Absent from it, and absent on purpose: the specification's A13 prior-filing matcher and
A16 foreign-text reuse probe. Both search a customer's own prior filings, and
customer-history reuse was removed from this product. A node that is not here cannot be
switched on by configuration.
"""


def execute(
    run_input: RunInput,
    ports: Ports,
    *,
    on_stage: Callable[[str, RunState], None] | None = None,
) -> RunState:
    """Run the chain and return the final state.

    The run never blocks: there is no interactive node, no wait state and no approval
    gate anywhere in it. What a human must confirm leaves as a review item, and the
    caller has a complete draft either way.

    Raising ends the run, and only three kinds of thing raise: a structurally invalid
    submission, a stage whose own contract was broken, and a model call that failed. None
    of them is retried — a second attempt at a legal document is a machine talking itself
    into an answer.
    """
    state = RunState(input=run_input)
    for node in CHAIN:
        blocked = next(
            (branch for branch in node.gate if not branch.holds(state, ports)), None
        )
        if blocked is not None:
            logger.info("skipping %s: %s", node.name, blocked.when_false)
            state = state.skipped(node.name, blocked.when_false)
            continue

        logger.info("running %s (%s)", node.name, node.spec)
        state = node.run(state, ports)
        if on_stage is not None:
            on_stage(node.name, state)
    return state


def describe_chain() -> str:
    """The topology, printable without running it."""
    lines = ["the outer chain, in order:"]
    for position, node in enumerate(CHAIN, start=1):
        lines.append(f"{position:>3}. {node.name}  [{node.spec}]")
        for branch in node.gate:
            lines.append(f"       runs only when: {branch.condition}")
            lines.append(f"       otherwise     : {branch.when_false}")
        for branch in node.decides:
            lines.append(f"       branches on   : {branch.condition}")
            lines.append(f"         yes         : {branch.when_true}")
            lines.append(f"         no          : {branch.when_false}")
    return "\n".join(lines)
