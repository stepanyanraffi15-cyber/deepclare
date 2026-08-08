"""M12 Filing Format Adapter — the only module that knows the filed declaration format.

Dossier 10 §3 M12 and §4 rule 1: value production is separate from value expression, and
**exactly one module knows the filed format, in both directions**. Everything upstream
decides what a value should be; this package decides how it is written, and reads one
back the same way so the two directions cannot drift apart.

**Must not know:** how any value was produced, which model produced it, tenancy, jobs,
the reference data beyond value-set membership checks handed to it, or the user
interface. Nothing here imports from any pipeline stage.

**Its external interface is fixed.** Unlike every other boundary in this system, the
filed document's structure is not a design choice. Its three failure signals are opaque
and field-blind — a wrong-format rejection naming no field, a hang partway through import
with no message, and silent value drop where the import succeeds and the value is simply
gone — so conformance is enforced here, before writing, never discovered on filing.

Read `contract` before changing anything, and read `observed` before that. Every element
name, every namespace prefix and every child sequence is generated from the ground-truth
declarations in the evaluation corpus and is not written by hand anywhere: the
misspellings are contract, the child order is enforced even for optional siblings, and
the three namespace prefixes are assigned per element with no rule behind them.
"""

from deepclare.filing.conformance import (
    ConformanceResult,
    Finding,
    RuleOutcome,
    RuleStatus,
    check,
)
from deepclare.filing.document import Element, parse_document
from deepclare.filing.errors import (
    FilingContractError,
    MalformedFiledDocument,
    UnrepresentableValue,
)
from deepclare.filing.reader import ParsedFiling, UnreadElement, read_declaration
from deepclare.filing.writer import FiledDocument, write_declaration

__all__ = [
    "ConformanceResult",
    "Element",
    "FiledDocument",
    "FilingContractError",
    "Finding",
    "MalformedFiledDocument",
    "ParsedFiling",
    "RuleOutcome",
    "RuleStatus",
    "UnreadElement",
    "UnrepresentableValue",
    "check",
    "parse_document",
    "read_declaration",
    "write_declaration",
]
