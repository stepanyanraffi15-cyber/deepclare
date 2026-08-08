"""The Code Assignment graph, declared once, and the layer that runs it per line.

Everything below the node functions is topology: which node runs first, what each edge's
condition is, and where a traversal ends. It is here rather than inside the nodes so that
the whole shape can be read — and printed — in one place.

**The retry is guarded structurally, not by a counter.** The only cycle in the graph is
C7 back to C1, and C7's whole job is to clear the printed prefix, which is the slot the
entry branch tests and the slot the dead-end condition tests. A second pass therefore
cannot enter the fast path and cannot reach C7 again. Nothing counts anything.

**The retry re-enters at C1, not at the entry branch**, which is the same fact seen from
the other side: re-entering at the branch would test a slot C7 just cleared and take the
other edge anyway, but it would leave the graph one edit away from a loop.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from deepclare.classification.features import ClassificationFeatures
from deepclare.classification.graph import ALWAYS, END, ENTRY, Edge, Graph, Node
from deepclare.classification.line import ClassificationLine
from deepclare.classification.nodes import (
    NodeContext,
    is_dead_end,
    pick_final_code,
    pick_heading_and_write_query,
    prefer_subheading,
    reset_dead_end,
    retrieve_candidates,
    shortlist_chapters,
    take_printed_code,
    usable_printed_prefix,
    verify_pick,
)
from deepclare.classification.records import LineClassification, classification_from_traversal
from deepclare.classification.state import TraversalState
from deepclare.models import GenerativeModel
from deepclare.reference.store import NomenclatureStore

GRAPH_NAME = "Code Assignment — one traversal per goods line"


def build_graph(ctx: NodeContext) -> Graph:
    """Declare the graph. Nothing runs; this is the shape."""
    features = ctx.features

    def fast_path_applies(state: TraversalState) -> bool:
        return features.printed_code_fast_path and (
            usable_printed_prefix(state.line, ctx.store) is not None
        )

    nodes = [
        Node(
            "C0",
            "printed-code fast path",
            "Take the chapter and heading from a code printed on the invoice line; skip "
            "both narrowing calls and the subheading call.",
            partial(take_printed_code, ctx=ctx),
        ),
        Node(
            "C1",
            "chapter shortlister",
            "Shortlist one or two of the ninety-six chapters from the full menu.",
            partial(shortlist_chapters, ctx=ctx),
        ),
        Node(
            "C2",
            "heading picker and query writer",
            "One call: pick the top two headings across the shortlisted chapters and "
            "write the English search description retrieval will embed.",
            partial(pick_heading_and_write_query, ctx=ctx),
        ),
        Node(
            "C3",
            "subheading preferencer",
            "Name one or two likely 6-digit subheadings, as a soft annotation on the "
            "candidates and never as a retrieval filter.",
            partial(prefer_subheading, ctx=ctx),
        ),
        Node(
            "C4",
            "candidate retriever",
            "Embed the query once and search the leaves within the narrowest available "
            "scope, applying no similarity threshold.",
            partial(retrieve_candidates, ctx=ctx),
        ),
        Node(
            "C5",
            "final code picker",
            "Choose one 10-digit code from the candidates, or abstain with a reason.",
            partial(pick_final_code, ctx=ctx),
        ),
        Node(
            "C6",
            "independent verifier",
            "A second opinion on the chosen code alone; veto only, turning an "
            "unconfirmed pick into an abstention.",
            partial(verify_pick, ctx=ctx),
        ),
        Node(
            "C7",
            "dead-end reset",
            "Clear the printed-code scope so the normal narrowing runs exactly once.",
            partial(reset_dead_end, ctx=ctx),
        ),
    ]

    edges = [
        Edge(
            ENTRY,
            "C0",
            "the printed-code feature is on and the line's printed code reduces to at "
            "least 6 digits whose chapter and heading both exist in this tree",
            fast_path_applies,
        ),
        Edge(ENTRY, "C1", "otherwise"),
        Edge("C0", "C4", ALWAYS + " — the document already states the subheading"),
        Edge("C1", "C2", ALWAYS),
        Edge(
            "C2",
            "C3",
            "the subheading-preference feature is on",
            lambda _state: features.subheading_preference,
        ),
        Edge("C2", "C4", "the subheading-preference feature is off"),
        Edge("C3", "C4", ALWAYS),
        Edge("C4", "C5", ALWAYS),
        Edge(
            "C5",
            "C6",
            "the verification feature is on",
            lambda _state: features.verification,
        ),
        Edge(
            "C5",
            "C7",
            "verification is off and the fast path dead-ended: the printed prefix is "
            "still set and the result carries no code",
            is_dead_end,
        ),
        Edge("C5", END, "otherwise"),
        Edge(
            "C6",
            "C7",
            "the fast path dead-ended: the printed prefix is still set and the result "
            "carries no code — abstained, retrieved nothing, or was vetoed",
            is_dead_end,
        ),
        Edge("C6", END, "otherwise"),
        Edge(
            "C7",
            "C1",
            ALWAYS + " — re-entry is at the chapter node, not the entry branch, so the "
            "fast path cannot re-fire; C7 having cleared the prefix is the loop guard",
        ),
    ]
    return Graph(GRAPH_NAME, nodes, edges)


class CodeAssignment:
    """The innermost layer: one traversal of the graph per goods line.

    It knows nothing about the layers outside it and returns an abstention rather than
    delegating anywhere — there is nothing under it.
    """

    def __init__(
        self,
        *,
        store: NomenclatureStore,
        model: GenerativeModel,
        prompts_dir: Path,
        features: ClassificationFeatures | None = None,
    ) -> None:
        self._context = NodeContext(
            store=store,
            model=model,
            prompts_dir=Path(prompts_dir),
            features=features or ClassificationFeatures(),
        )
        self._graph = build_graph(self._context)

    @property
    def graph(self) -> Graph:
        """The declaration itself, for printing and for tests that never call a model."""
        return self._graph

    def decide(self, line: ClassificationLine) -> LineClassification:
        """Traverse the graph once for this line."""
        finished = self._graph.run(TraversalState(line=line))
        return classification_from_traversal(finished)
