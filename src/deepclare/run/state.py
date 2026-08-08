"""One run's input, and one run's state.

Dossier 02 §5.1 describes run state as a set of slots, each written once by one node and
read by later ones. It is one explicit typed object here rather than a dictionary that
accumulates keys, for three reasons that are not style:

* a slot read before its writer ran is a named error rather than a `KeyError` naming a
  string;
* the shape of the run is readable in one place, without following the chain;
* nothing can add a slot in passing, so the object cannot become the untyped bag that
  every stage learns to reach into.

The state is frozen and each stage returns a new one. That is what makes a stage a
function of what came before it, and it is what lets the chain be read as a sequence
rather than as a set of mutations in an order nobody wrote down.

**The input carries the run's configuration.** Dossier 10 §4 invariant 2: no module reads
ambient process configuration, so behaviour switches reach a run as explicit input. A run
is therefore reproducible from its recorded input and its ports alone — nothing in the
chain consults an environment variable, a settings object or a file the input does not
name.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from deepclare.assembly.inputs import DeclarantProfile, LineDraft
from deepclare.classification.features import ClassificationFeatures
from deepclare.classification.records import LineClassification
from deepclare.consistency.records import ConsistencyOutcome
from deepclare.description.context import (
    MAX_SIBLINGS,
    SIBLING_EXCERPT_CHARS,
    LineContext,
)
from deepclare.description.records import LineDescription
from deepclare.domain import Declaration, InvoiceRecord, LineEnrichment, ReviewItem
from deepclare.filing.writer import FiledDocument
from deepclare.intake.classifier import PageVerdict
from deepclare.intake.grouping import GroupedSubmission
from deepclare.intake.rasterizer import RenderedPage
from deepclare.intake.router import RoutedSubmission
from deepclare.intake.submission import SubmittedFile
from deepclare.reading.records import ConsignmentNoteReading, InvoiceReading
from deepclare.review.report import ReviewReport
from deepclare.run.errors import StateError


class RunOptions(BaseModel):
    """Every behaviour switch of one run, in one place.

    Each is a number or a flag the chain reads directly. Which *capabilities* a run has is
    a separate question and is answered by the ports, because a capability is an object
    and not a value.
    """

    model_config = ConfigDict(frozen=True)

    classification_features: ClassificationFeatures = ClassificationFeatures()
    """Read by whoever constructs the classifier port. Recorded here so a run's input
    states how code assignment was configured, which is otherwise unrecoverable."""

    max_siblings: int = Field(default=MAX_SIBLINGS, gt=0)
    sibling_excerpt_chars: int = Field(default=SIBLING_EXCERPT_CHARS, gt=0)


class RunInput(BaseModel):
    """Everything one run is asked to do, and nothing about how it will do it."""

    model_config = ConfigDict(frozen=True)

    files: tuple[SubmittedFile, ...] = Field(min_length=1)
    profile: DeclarantProfile = DeclarantProfile()
    """What no document carries: where the goods clear, who fills the form in, and the
    importing company on the runs where the documents do not name it."""

    options: RunOptions = RunOptions()


class RunState(BaseModel):
    """The slots of one run, written once each, in chain order.

    Every optional slot is `None` or empty until the stage that owns it has run. The
    `require_*` accessors exist so that reading one early names the stage that fills it.
    """

    model_config = ConfigDict(frozen=True)

    input: RunInput

    # --- intake ---------------------------------------------------------------
    routed: RoutedSubmission | None = None
    pages: tuple[RenderedPage, ...] = ()
    verdicts: tuple[PageVerdict, ...] = ()
    grouped: GroupedSubmission | None = None

    # --- reading --------------------------------------------------------------
    invoice_reading: InvoiceReading | None = None
    note_reading: ConsignmentNoteReading | None = None

    # --- per line -------------------------------------------------------------
    enrichments: tuple[LineEnrichment, ...] = ()
    contexts: tuple[LineContext, ...] = ()
    descriptions: tuple[LineDescription, ...] = ()
    classifications: tuple[LineClassification, ...] = ()
    drafts: tuple[LineDraft, ...] = ()

    # --- shipment -------------------------------------------------------------
    consistency: ConsistencyOutcome | None = None
    declaration: Declaration | None = None
    assembly_items: tuple[ReviewItem, ...] = ()
    filed: FiledDocument | None = None
    report: ReviewReport | None = None

    # --- the run's own account of itself --------------------------------------
    stages_run: tuple[str, ...] = ()
    stages_skipped: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    """One sentence per thing the run did that a reader of the summary would otherwise
    have to infer — a stage skipped, a best-effort pass abandoned, evidence not read."""

    run_items: tuple[ReviewItem, ...] = ()
    """Review items the orchestration itself raised. Only ever about what the run did or
    did not do; never about a value, which belongs to whichever module produced it."""

    def advance(self, **slots: object) -> Self:
        """The next state. Frozen, so a stage returns rather than mutates."""
        return self.model_copy(update=slots)

    def ran(self, stage: str, **slots: object) -> Self:
        return self.model_copy(update={**slots, "stages_run": (*self.stages_run, stage)})

    def skipped(self, stage: str, why: str) -> Self:
        return self.model_copy(
            update={
                "stages_skipped": (*self.stages_skipped, stage),
                "notes": (*self.notes, f"{stage}: skipped — {why}"),
            }
        )

    def noting(self, note: str) -> Self:
        return self.model_copy(update={"notes": (*self.notes, note)})

    # --- accessors that name the stage that should have filled the slot -------

    def require_routed(self) -> RoutedSubmission:
        return _require(self.routed, "routed submission", "intake")

    def require_grouped(self) -> GroupedSubmission:
        return _require(self.grouped, "grouped submission", "group pages")

    def require_invoice(self) -> InvoiceRecord:
        return _require(self.invoice_reading, "invoice record", "read documents").invoice

    def require_declaration(self) -> Declaration:
        return _require(self.declaration, "declaration", "assemble declaration")

    def require_filed(self) -> FiledDocument:
        return _require(self.filed, "filed document", "write filing")

    def require_report(self) -> ReviewReport:
        return _require(self.report, "review report", "build review report")

    # --- what the summary and the caller read ---------------------------------

    @property
    def goods_line_count(self) -> int:
        return len(self.drafts)

    @property
    def codes_assigned(self) -> int:
        return sum(1 for draft in self.drafts if draft.classification.code is not None)

    @property
    def codes_abstained(self) -> int:
        return sum(1 for draft in self.drafts if draft.classification.code is None)


def _require[T](value: T | None, what: str, stage: str) -> T:
    if value is None:
        raise StateError(
            f"the run has no {what} yet: it is written by the {stage!r} stage, which has "
            "not run. A chain whose stages are out of order is a defect in the chain."
        )
    return value
