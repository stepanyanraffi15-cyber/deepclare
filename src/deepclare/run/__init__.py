"""M14 Run Orchestration — the outer chain, and nothing that belongs to a stage.

In: one submission's files, the declarant profile, and the behaviour switches of this
run. Out: the internal declaration, the filed document, the review report, and the
account of what the run did.

**Must not know about:** how any value is produced, what a commodity code means, how the
filed document is written, or what a review item is for. It sequences stages, decides
branches, and enforces the one contract the stages share — that every per-line stage
returns one result per input line, keyed by the caller-assigned line id.

Four rules govern the package, and each is a property of the shape rather than a habit:

1. **State is one explicit typed object.** Never a dictionary accumulating keys. A slot
   read before its writer ran names the stage that fills it; nothing can add a slot in
   passing.

2. **Branch conditions are declared in one place.** `conditions` is dossier 02 §6.1 as
   code — a named predicate with the specification's wording beside it — and the chain
   references them. A branch inside a node body is a branch nobody can enumerate.

3. **Every capability is injected.** Nothing in the chain constructs a provider, opens a
   store or reads an environment variable, so the whole run executes with no network, no
   authentication, no job store and no persistence present. `wiring` is the composition
   root and is not part of the chain.

4. **The run never blocks on a human.** There is no interactive node, no wait state and
   no approval gate anywhere in it. Every uncertainty leaves as a review item and the
   caller has a complete draft either way.

And one asymmetry decides the failure behaviour. A best-effort stage never sinks a run —
cross-line consistency returns the drafted lines untouched on every one of its failure
paths — while a broken contract stops it immediately, because a declaration that silently
dropped a goods line is a different shipment and no review item can say so.

There is no prior-filing reuse stage and no port for one. Customer-history reuse was
removed from this product deliberately; nomenclature search over the reference collection
is a different thing and lives inside classification.
"""

from deepclare.run.conditions import BRANCHES, Branch, describe_branches
from deepclare.run.errors import ContractError, RunError, StateError
from deepclare.run.pipeline import CHAIN, Node, describe_chain, execute
from deepclare.run.ports import (
    ClassifierPort,
    DescriptionWriterPort,
    DocumentReaderPort,
    EvidenceEnricherPort,
    Ports,
    ReconcilerPort,
    WorkbookReaderPort,
)
from deepclare.run.reporting import reported_values
from deepclare.run.state import RunInput, RunOptions, RunState
from deepclare.run.summary import format_summary
from deepclare.run.wiring import open_ports

__all__ = [
    "BRANCHES",
    "CHAIN",
    "Branch",
    "ClassifierPort",
    "ContractError",
    "DescriptionWriterPort",
    "DocumentReaderPort",
    "EvidenceEnricherPort",
    "Node",
    "Ports",
    "ReconcilerPort",
    "RunError",
    "RunInput",
    "RunOptions",
    "RunState",
    "StateError",
    "WorkbookReaderPort",
    "describe_branches",
    "describe_chain",
    "execute",
    "format_summary",
    "open_ports",
    "reported_values",
]
