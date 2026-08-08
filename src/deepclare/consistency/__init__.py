"""M10 Cross-Line Consistency — reconciling one shipment's drafted lines against one
another.

In: the fully drafted lines — the invoice's own wording, the **final** Armenian text that
will be filed, the deterministic segments inside that text, the commodity code and the
tariff's supplementary unit.

Out: a corrected description, code and unit per line; the set of lines it changed; and a
review item for every change a human must confirm.

**Must not know:** the filed document's element structure, the declarant profile, tenancy,
jobs, or the reference data other than through the same existence check classification
owns. That last one is structural rather than promised: the reconciler is constructed with
an `ExistenceGate`, not with the nomenclature store, so there is no unit lookup and no
retrieval to reach for.

**It never sets a quantity figure.** Neither model here is given one, neither answer shape
has a field for one, and a rewrite that drops a figure the invoice states is refused. A
prohibition backed by omission cannot be violated.

**It is never the reason a run fails.** Every failure path — a provider error, a malformed
answer, a rewrite that breaks a guardrail — leaves the drafted lines exactly as they were
drafted and the run proceeds.

### The anchors this module was specified to have, and does not

The specification builds both calls around *golden* lines: lines whose Armenian wording
came from one of the customer's own confirmed prior filings, marked authoritative, never
rewritten, and used as the reference style every sibling line is conformed to. Customer-
history reuse was removed from this product deliberately, so there are no golden lines and
there is no house style to propagate.

What replaces them is **mutual** conformance: with no line privileged, the reference is
whatever the shipment's own lines agree on, and a line that disagrees with its family is
the one that moves. Three consequences are worth naming rather than discovering:

* The critic's "never report an issue against a reference line" rule has no subject and is
  gone. Every line is equally open to criticism, and equally able to be the model for
  another.
* Conformance can now converge on the majority's mistake — five lines wrong in the same
  way have nothing to be measured against. The defence is that this pass only ever changes
  *wording and code agreement*, every change carries a review item, and no change is ever
  the source of a figure.
* The rewriter's dynamic exemplars — the only retrieval-driven few-shot in the system —
  are gone with the golden lines. The draft itself is the exemplar set.
"""

from deepclare.consistency.critic import CRITIC_TIER, ConsistencyCritic
from deepclare.consistency.errors import ConsistencyError
from deepclare.consistency.guards import (
    collapsed_lines,
    dropped_number_tokens,
    refusal_for_description,
)
from deepclare.consistency.reconcile import Reconciler
from deepclare.consistency.records import (
    STAGE,
    ConsistencyField,
    ConsistencyIssue,
    ConsistencyOutcome,
    Critique,
    DraftedLine,
    LineChange,
    PassOutcome,
    ReconciledLine,
    RejectedRewrite,
)
from deepclare.consistency.rewriter import (
    REWRITER_TIER,
    ConsistencyRewriter,
    LineProposal,
    RewriteAttempt,
)

__all__ = [
    "CRITIC_TIER",
    "REWRITER_TIER",
    "STAGE",
    "ConsistencyCritic",
    "ConsistencyError",
    "ConsistencyField",
    "ConsistencyIssue",
    "ConsistencyOutcome",
    "ConsistencyRewriter",
    "Critique",
    "DraftedLine",
    "LineChange",
    "LineProposal",
    "PassOutcome",
    "ReconciledLine",
    "Reconciler",
    "RejectedRewrite",
    "RewriteAttempt",
    "collapsed_lines",
    "dropped_number_tokens",
    "refusal_for_description",
]
