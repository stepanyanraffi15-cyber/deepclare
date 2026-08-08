"""A declared graph: nodes, edges, and the conditions on the edges.

This is the only part of the system that is genuinely a graph rather than a line, and it
is built as one on purpose. Three properties follow from the declaration and none of them
survives if a node is allowed to call the next one:

* **The topology reads in one place.** Every edge and every branch condition is in the
  declaration, not scattered through the bodies of eight functions.
* **It is printable without running.** `describe()` renders the whole thing from the
  declaration alone, so what the code does and what the diagram says cannot drift.
* **It is traceable node by node afterwards.** A traversal returns the state it ended in,
  and the state carries the step log every node appended to.

A node takes state and returns state. It never chooses what runs next; the edges do.

**Mis-declarations are caught at construction, not at run time.** Every node must be
reachable, every edge must name something that exists, and the last edge out of every
node must be unconditional — which is what makes it impossible for a traversal to arrive
somewhere with no way out.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from deepclare.classification.errors import GraphDeclarationError
from deepclare.classification.state import TraversalState

ENTRY = "entry"
"""Where a traversal starts. Not a node: nothing runs here, the edges out of it choose."""

END = "end"
"""Where a traversal finishes. Not a node."""

ALWAYS = "always"
"""How an unconditional edge reads when the graph is printed."""


@dataclass(frozen=True)
class Node:
    """One step of the traversal."""

    id: str
    title: str
    purpose: str
    run: Callable[[TraversalState], TraversalState]


@dataclass(frozen=True)
class Edge:
    """One transition, with the condition under which it is taken.

    `holds` of `None` is an unconditional edge. `when` is the same condition in words,
    and it is what `describe()` prints — the two are written together so that a printed
    graph states the real condition rather than a summary of it.
    """

    source: str
    target: str
    when: str
    holds: Callable[[TraversalState], bool] | None = None


class Graph:
    """A validated node-and-edge declaration that can be printed or traversed."""

    def __init__(self, name: str, nodes: Sequence[Node], edges: Sequence[Edge]) -> None:
        self.name = name
        self._nodes = {node.id: node for node in nodes}
        if len(self._nodes) != len(nodes):
            raise GraphDeclarationError("two nodes share an id")
        self._edges = tuple(edges)
        self._validate()

    # --- inspection --------------------------------------------------------

    @property
    def nodes(self) -> tuple[Node, ...]:
        return tuple(self._nodes.values())

    @property
    def edges(self) -> tuple[Edge, ...]:
        return self._edges

    def describe(self) -> str:
        """The whole graph as text, without running it."""
        width = max(len(node.id) for node in self._nodes.values())
        lines = [self.name, "", "nodes"]
        for node in self._nodes.values():
            lines.append(f"  {node.id:<{width}}  {node.title}")
            lines.append(f"  {'':<{width}}    {node.purpose}")
        lines.append("")
        lines.append("edges")
        source_width = max(len(edge.source) for edge in self._edges)
        target_width = max(len(edge.target) for edge in self._edges)
        for edge in self._edges:
            lines.append(
                f"  {edge.source:<{source_width}} -> {edge.target:<{target_width}}"
                f"   {edge.when}"
            )
        return "\n".join(lines)

    # --- traversal ---------------------------------------------------------

    def run(self, state: TraversalState) -> TraversalState:
        """Traverse from the entry to the end, returning the state that comes out."""
        position = self._next(ENTRY, state)
        # A bound on how many nodes one traversal may visit. It is not a retry counter:
        # the one retry in this graph is guarded structurally, by the reset clearing the
        # slot the entry branch tests. This exists so that a mis-declared cycle raises
        # instead of hanging, and it cannot fire on a correct declaration.
        budget = 4 * len(self._nodes)
        while position != END:
            if budget <= 0:
                raise GraphDeclarationError(
                    f"{self.name}: traversal did not terminate. The declaration has a "
                    f"cycle with no exit; the steps taken were "
                    f"{[step.node for step in state.steps]}"
                )
            budget -= 1
            state = self._nodes[position].run(state)
            position = self._next(position, state)
        return state

    def _next(self, source: str, state: TraversalState) -> str:
        for edge in self._edges:
            if edge.source == source and (edge.holds is None or edge.holds(state)):
                return edge.target
        raise GraphDeclarationError(
            f"{self.name}: no edge out of {source!r} was taken. Construction requires "
            "the last edge out of every source to be unconditional, so reaching this "
            "means the declaration changed without the validation."
        )

    # --- declaration checks -------------------------------------------------

    def _validate(self) -> None:
        known = set(self._nodes) | {END}
        sources = {edge.source for edge in self._edges}
        if ENTRY not in sources:
            raise GraphDeclarationError(f"{self.name}: no edge leaves the entry")

        for edge in self._edges:
            if edge.source != ENTRY and edge.source not in self._nodes:
                raise GraphDeclarationError(
                    f"{self.name}: edge from unknown node {edge.source!r}"
                )
            if edge.target not in known:
                raise GraphDeclarationError(
                    f"{self.name}: edge to unknown node {edge.target!r}"
                )

        for source in (ENTRY, *self._nodes):
            outgoing = [edge for edge in self._edges if edge.source == source]
            if not outgoing:
                raise GraphDeclarationError(
                    f"{self.name}: {source!r} has no outgoing edge, so a traversal that "
                    "reaches it cannot leave"
                )
            if outgoing[-1].holds is not None:
                raise GraphDeclarationError(
                    f"{self.name}: the last edge out of {source!r} is conditional, so a "
                    "traversal can arrive with no edge to take"
                )
            unconditional = [
                index for index, edge in enumerate(outgoing) if edge.holds is None
            ]
            if unconditional[0] != len(outgoing) - 1:
                raise GraphDeclarationError(
                    f"{self.name}: {source!r} declares an edge after an unconditional "
                    "one, which can never be taken"
                )

        unreachable = set(self._nodes) - self._reachable()
        if unreachable:
            raise GraphDeclarationError(
                f"{self.name}: {sorted(unreachable)} cannot be reached from the entry"
            )

    def _reachable(self) -> set[str]:
        seen: set[str] = set()
        frontier = [
            edge.target for edge in self._edges if edge.source == ENTRY
        ]
        while frontier:
            node = frontier.pop()
            if node in seen or node == END:
                continue
            seen.add(node)
            frontier.extend(
                edge.target for edge in self._edges if edge.source == node
            )
        return seen
