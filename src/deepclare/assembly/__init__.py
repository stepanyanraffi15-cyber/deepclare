"""M11 Declaration Assembly — every cross-field rule.

In: the extracted records, the per-line drafts after reconciliation, the declarant
profile, and reference lookups for units, countries, packing and offices.
Out: a complete internal declaration with per-field provenance and confidence, plus
review items keyed by **domain concept, never by an element path**.

Owns the arithmetic and consistency core: the unit-resolution ladder, the quantity-unit
pairing rule, piece and package arithmetic, weight resolution and distribution,
code/name pairing, transport consistency, totals, and the deterministic assembly of the
filed description text.

**Must not know** element names, sequence order, cardinality, namespaces, encoding,
decimal and date formatting, padding, or empty-versus-absent handling. It knows what a
value should be; it does not know how the value is written.
"""

from deepclare.assembly.declaration import STAGE, assemble_declaration
from deepclare.assembly.trace import Review
from deepclare.assembly.inputs import (
    AssemblyInput,
    DeclarantProfile,
    FillerProfile,
    GoodsLocationProfile,
    ImporterProfile,
    LineDraft,
)
from deepclare.assembly.tables import ReferenceTables, load_tables

__all__ = [
    "STAGE",
    "AssemblyInput",
    "DeclarantProfile",
    "FillerProfile",
    "GoodsLocationProfile",
    "ImporterProfile",
    "LineDraft",
    "ReferenceTables",
    "Review",
    "assemble_declaration",
    "load_tables",
]
