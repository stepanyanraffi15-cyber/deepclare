"""Every capability a run needs, as a protocol it is handed rather than reaches for.

Dossier 10 §4: domain work is separate from delivery, and the run must be executable with
no network boundary, no authentication, no job store and no persistence present. That is
only true if nothing inside the chain constructs a provider client, opens a vector store
or reads an environment variable. So each capability arrives as an injected object, and
the chain never learns what is behind one.

Four of the six are optional, and `None` is a declared branch rather than a missing
dependency:

* **no page classifier** — every page keeps its source file's role, which is the
  specification's direct-read path expressed through the grouper rather than around it;
* **no evidence enricher** — supporting documents are carried but not read, and the
  operator is told so;
* **no reconciler** — the drafted lines are filed as they were drafted.

The two that are required are the two without which there is no declaration: something
that reads a document, and something that assigns a code.

What is *not* here is as deliberate. There is no prior-filing matcher and no reuse probe.
Customer-history reuse was removed from this product, so a port for it would be a socket
for a component that must never exist.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from deepclare.assembly.tables import ReferenceTables
from deepclare.classification.line import ClassificationLine
from deepclare.classification.records import LineClassification
from deepclare.consistency.records import ConsistencyOutcome, DraftedLine
from deepclare.description.context import LineContext
from deepclare.description.records import LineDescription
from deepclare.domain import LineEnrichment
from deepclare.intake.classifier import PageTypeClassifier
from deepclare.intake.grouping import LogicalDocument
from deepclare.intake.router import RoutedDocument
from deepclare.reading.records import ConsignmentNoteReading, InvoiceReading


@runtime_checkable
class DocumentReaderPort(Protocol):
    """Reads a logical document into verbatim, untranslated records."""

    def read_invoice(self, document: LogicalDocument) -> InvoiceReading: ...

    def read_consignment_note(
        self, document: LogicalDocument
    ) -> ConsignmentNoteReading: ...


@runtime_checkable
class WorkbookReaderPort(Protocol):
    """Reads a page-less invoice — a workbook — which vision never sees.

    Separate from the document reader because the input is a different thing: a routed
    file rather than a page group, structured data rather than an image. A run whose
    invoice is a workbook and which was handed no workbook reader stops naming what is
    missing, rather than drafting a declaration with no goods on it.
    """

    def read_invoice(self, document: RoutedDocument) -> InvoiceReading: ...


@runtime_checkable
class EvidenceEnricherPort(Protocol):
    """Fills gaps in the invoice's own lines from supporting documents.

    Never overrides an invoice value: dossier 02 §3 A14 is explicit that enrichment fills
    gaps only. A verdict naming a line the invoice does not have is dropped downstream by
    the context builder's own contract, so this port promises nothing about completeness.
    """

    def enrich(
        self, documents: Sequence[LogicalDocument], lines: Sequence[str]
    ) -> Sequence[LineEnrichment]: ...


@runtime_checkable
class DescriptionWriterPort(Protocol):
    """Writes the Armenian text that will be filed for one goods line."""

    def write(self, context: LineContext) -> LineDescription: ...


@runtime_checkable
class ClassifierPort(Protocol):
    """Assigns one commodity code per goods line, or abstains with a reason."""

    def classify(self, line: ClassificationLine) -> LineClassification: ...


@runtime_checkable
class ReconcilerPort(Protocol):
    """Reconciles one shipment's drafted lines against one another."""

    def reconcile(self, lines: Sequence[DraftedLine]) -> ConsistencyOutcome: ...


@dataclass(frozen=True)
class Ports:
    """Everything a run is handed. Constructed once, at the edge, and never inside.

    `tables` is here rather than in the input because it is acquired — it is read off
    disk by the composition root — and dossier 10 §4 keeps knowledge separate from its
    acquisition. The input records what a run *decided*; the ports carry what it was
    *given*.
    """

    reader: DocumentReaderPort
    classifier: ClassifierPort
    description_writer: DescriptionWriterPort
    tables: ReferenceTables

    page_classifier: PageTypeClassifier | None = None
    workbook_reader: WorkbookReaderPort | None = None
    evidence_enricher: EvidenceEnricherPort | None = None
    reconciler: ReconcilerPort | None = None

    def describe(self) -> str:
        """Which optional capabilities this run has, for the run's own account of itself."""
        configured = {
            "page classifier": self.page_classifier is not None,
            "workbook reader": self.workbook_reader is not None,
            "evidence enricher": self.evidence_enricher is not None,
            "cross-line reconciler": self.reconciler is not None,
        }
        return ", ".join(
            f"{name}: {'yes' if present else 'no'}"
            for name, present in configured.items()
        )
