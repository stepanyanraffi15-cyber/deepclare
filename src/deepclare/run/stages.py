"""The nodes of the outer chain, each a function of the state before it.

Every stage takes the state and the ports and returns the next state. None of them
constructs a provider, opens a store, reads an environment variable or asks a human
anything: dossier 02 §1 is explicit that there is no interactive node and no wait state
anywhere in the topology, so every uncertainty a stage meets becomes a review item and the
run continues.

Two stages are worth reading before the rest.

`guard_completeness` is A19, and it is the reason the chain can zip by line id at all.
Every per-line stage promises one result per input line keyed by the caller-assigned id;
this is where that promise is checked, once, naming the line — because the alternative is
a `KeyError` on a dictionary two stages later, at which point nobody can tell whether a
description, a classification or a goods line went missing.

`reconcile_lines` is A21/A22, and it can never sink a run. The reconciler's own contract
returns every line it was given on every failure path, and this stage adds nothing that
could raise: a change it cannot apply is a contract violation of the reconciler, and a
pass that did not run leaves the drafts exactly as they were drafted.
"""

from __future__ import annotations

from collections.abc import Sequence

from deepclare.assembly.declaration import assemble_declaration as _assemble
from deepclare.assembly.inputs import AssemblyInput, LineDraft
from deepclare.classification.line import build_classification_lines
from deepclare.classification.records import LineClassification
from deepclare.consistency.records import (
    STAGE as CONSISTENCY_STAGE,
    ConsistencyField,
    ConsistencyOutcome,
    DraftedLine,
    LineChange,
)
from deepclare.description.context import build_line_contexts
from deepclare.description.records import LineDescription
from deepclare.domain import InvoiceRecord, LineEnrichment, ReviewItem, ReviewKind
from deepclare.filing.writer import write_declaration
from deepclare.intake.gate import check_submission
from deepclare.intake.grouping import group_pages as _group_pages
from deepclare.intake.rasterizer import rasterize_documents
from deepclare.intake.router import route_documents
from deepclare.review.report import build_report
from deepclare.run.conditions import (
    CONSIGNMENT_NOTE_PRESENT,
    EVIDENCE_CAN_BE_READ,
    INVOICE_HAS_PAGES,
    RECONCILER_CONFIGURED,
)
from deepclare.run.errors import ContractError, RunError
from deepclare.run.ports import Ports
from deepclare.run.reporting import reported_values
from deepclare.run.state import RunState

STAGE = "run"
"""What the orchestration names as its producing stage on the few items it raises."""


# --- intake ---------------------------------------------------------------------------


def intake(state: RunState, ports: Ports) -> RunState:
    """A1 and A2. Structural rules on names and roles, then three buckets from the bytes.

    Both refuse rather than degrade: a submission with no invoice, two invoices or two
    consignment notes is a bad-input condition that never self-heals, and drafting
    something from it would be drafting a different shipment.
    """
    check_submission(state.input.files)
    return state.ran("intake", routed=route_documents(state.input.files))


def rasterize(state: RunState, ports: Ports) -> RunState:
    """A3. Every page of every page-bearing document, at 200 DPI, in document order.

    The batch order is `documents_in_order()` and a page-type verdict counts positions
    over this batch, which is why one function defines it and nothing recomputes it.
    """
    routed = state.require_routed()
    pages = rasterize_documents(routed.page_bearing_documents())
    if not pages:
        raise RunError(
            f"{routed.invoice.file_name} rendered no pages. A page-bearing invoice that "
            "yields nothing to read cannot be drafted from, and an empty batch would "
            "reach grouping as a submission with no invoice page."
        )
    return state.ran("rasterize", pages=pages)


def classify_pages(state: RunState, ports: Ports) -> RunState:
    """A4. One call, all pages at once.

    Gated on a classifier being configured, so it is never reached without one. The
    verdicts are not padded, deduplicated or range-checked here: the port promises no
    completeness and the grouper is built to survive all three gaps — which is the same
    reason a missing classifier is a skip rather than a failure.
    """
    if ports.page_classifier is None:
        raise RunError(
            "page classification ran with no classifier configured; the chain gates this "
            "stage on one, so reaching it without one is a defect in the chain."
        )
    verdicts = tuple(ports.page_classifier.classify(state.pages))
    return state.ran("classify pages", verdicts=verdicts)


def group_pages(state: RunState, ports: Ports) -> RunState:
    """A5. Pages become logical documents; no page is ever dropped.

    Raises when no page reads as an invoice. Failing loudly beats filing a declaration
    with no goods on it, and that is the one place where missing is worse than wrong.
    """
    grouped = _group_pages(state.require_routed(), state.pages, state.verdicts)
    return state.ran("group pages", grouped=grouped)


# --- reading --------------------------------------------------------------------------


def read_documents(state: RunState, ports: Ports) -> RunState:
    """A6. One vision call per page group; the consignment note only if there is one.

    A page-less invoice takes the workbook path instead, which is a different reader on a
    different input — structured data rather than an image — and arrives as its own port.
    """
    if not INVOICE_HAS_PAGES.holds(state, ports):
        invoice = state.require_routed().invoice
        if ports.workbook_reader is None:
            raise RunError(
                f"{invoice.file_name} is a {invoice.file_format} invoice and no workbook "
                "reader was injected. A workbook has no pages, so vision never sees it "
                "and there is nothing to draft goods from."
            )
        return state.ran(
            "read documents",
            invoice_reading=ports.workbook_reader.read_invoice(invoice),
        )

    grouped = state.require_grouped()
    invoice_reading = ports.reader.read_invoice(grouped.invoice)
    if not CONSIGNMENT_NOTE_PRESENT.holds(state, ports):
        return state.ran(
            "read documents", invoice_reading=invoice_reading
        ).noting("no page grouped as a consignment note; none was read")

    assert grouped.consignment_note is not None  # narrowed by the branch above
    return state.ran(
        "read documents",
        invoice_reading=invoice_reading,
        note_reading=ports.reader.read_consignment_note(grouped.consignment_note),
    )


def gate_goods_lines(state: RunState, ports: Ports) -> RunState:
    """A12. The goods gate, and the contract the whole chain joins on.

    Reading assigns each goods row its 1-based positional id and refuses an invoice with
    no rows, so both halves of this gate are already true when it runs. It is checked
    anyway, here, because every later stage keys on those ids: an invoice whose ids were
    not `1..n` in printed order would reassemble lines under the wrong goods, and that is
    a failure no review item can describe.
    """
    invoice = state.require_invoice()
    if not invoice.goods_lines:
        raise RunError(
            "the invoice yielded zero goods lines. A declaration with no goods is not a "
            "lesser draft but a different document."
        )

    expected = [str(position) for position in range(1, len(invoice.goods_lines) + 1)]
    actual = [line.line_id for line in invoice.goods_lines]
    if actual != expected:
        raise ContractError(
            f"the invoice's goods lines are keyed {actual} and must be keyed {expected} "
            "in printed order. Every stage after this one joins on that id, and a gap or "
            "a reordering would attach one line's description to another's goods."
        )
    return state.ran("goods gate")


# --- per line -------------------------------------------------------------------------


def enrich_evidence(state: RunState, ports: Ports) -> RunState:
    """A14. Fills gaps from supporting documents, and never overrides an invoice value."""
    grouped = state.grouped
    if not EVIDENCE_CAN_BE_READ.holds(state, ports):
        if grouped is None or not grouped.supporting_evidence:
            return state.skipped("enrich evidence", "no supporting document was grouped")
        return state.skipped(
            "enrich evidence", "no evidence enricher is configured"
        ).advance(run_items=(*state.run_items, _evidence_not_read(grouped)))

    assert grouped is not None and ports.evidence_enricher is not None  # per the branch
    invoice = state.require_invoice()
    enrichments = tuple(
        ports.evidence_enricher.enrich(
            grouped.supporting_evidence,
            [line.line_id for line in invoice.goods_lines],
        )
    )
    return state.ran("enrich evidence", enrichments=enrichments)


def build_contexts(state: RunState, ports: Ports) -> RunState:
    """A15. The deterministic per-line context: script, siblings, grounding facts.

    No model call, and four things are withheld rather than forbidden — the printed code,
    the quantities, the dimensions and the totals. A figure a model cannot see is a figure
    it cannot write into text where arithmetic will append the real one.
    """
    contexts = build_line_contexts(
        state.require_invoice(),
        state.enrichments,
        max_siblings=state.input.options.max_siblings,
        sibling_excerpt_chars=state.input.options.sibling_excerpt_chars,
    )
    return state.ran("build line contexts", contexts=contexts)


def write_descriptions(state: RunState, ports: Ports) -> RunState:
    """A17. One call per line, in printed order.

    The lines are independent by contract — nothing about another line's outcome reaches
    the call — so the order is the invoice's only because the output has to come back in
    it. There is no retry: the first failure ends the run rather than talking the machine
    into an answer about a legal document.

    The batch's completeness is checked here rather than at A19, and that is deliberate:
    classification's own input builder refuses a line with no description, so a guard
    placed after it could never fire on this collection and would be unreachable code
    dressed as a contract. Checked here it names the stage that broke the promise.
    """
    descriptions = tuple(ports.description_writer.write(c) for c in state.contexts)
    _one_result_per_line(
        state.require_invoice(), descriptions, "description", "write descriptions"
    )
    return state.ran("write descriptions", descriptions=descriptions)


def classify_lines(state: RunState, ports: Ports) -> RunState:
    """A18. The layer stack, once per line, each traversal independent of the others."""
    lines = build_classification_lines(
        state.require_invoice(), state.descriptions, state.enrichments
    )
    classifications = tuple(ports.classifier.classify(line) for line in lines)
    return state.ran("classify lines", classifications=classifications)


def guard_completeness(state: RunState, ports: Ports) -> RunState:
    """A19. One result per input line, keyed by its id, or the run stops naming the line.

    This is the whole reason the stage exists, and it is stated in dossier 02 §5.1: the
    naming id and the classification id are the same id by contract, and A19 enforces that
    contract so a breach is a clear error here rather than a cryptic lookup failure during
    reassembly.

    Its subject is the classifications. The descriptions were checked the moment they were
    produced, for the reason given at `write_descriptions`; the promise is the same one and
    it is enforced by the same function.
    """
    _one_result_per_line(
        state.require_invoice(), state.classifications, "classification", "classify lines"
    )
    return state.ran("completeness guard")


def assemble_lines(state: RunState, ports: Ports) -> RunState:
    """A20. Zip by line id, strict.

    By position in the specification; by id here, which is the same thing once A19 has
    passed and is the safer of the two to write down.
    """
    invoice = state.require_invoice()
    descriptions = {d.line_id: d for d in state.descriptions}
    classifications = {c.line_id: c for c in state.classifications}
    enrichments = {e.line_id: e for e in state.enrichments}

    drafts = tuple(
        LineDraft(
            line=line,
            description=descriptions[line.line_id],
            classification=classifications[line.line_id],
            enrichment=enrichments.get(line.line_id),
        )
        for line in invoice.goods_lines
    )
    return state.ran("assemble lines", drafts=drafts)


# --- cross-line reconciliation --------------------------------------------------------


def reconcile_lines(state: RunState, ports: Ports) -> RunState:
    """A21 and A22. Best-effort: it improves consistency and never sinks a run.

    What it is given is the **naming** text, before the deterministic size and quantity
    segments are appended to it downstream. The specification hands it the fully assembled
    filed string and names the segments so a guardrail can check they came back verbatim;
    here they do not exist yet, so the guardrail has no subject and needs none — a segment
    that was never shown to the model cannot be dropped by it. It is the same defence the
    rest of this system uses, applied one stage earlier: a prohibition backed by omission
    cannot be violated.
    """
    if not RECONCILER_CONFIGURED.holds(state, ports) or ports.reconciler is None:
        return state.skipped("reconcile lines", RECONCILER_CONFIGURED.when_false)

    outcome = ports.reconciler.reconcile(_drafted(state.drafts))
    drafts = tuple(
        _apply_changes(draft, outcome) for draft in state.drafts
    )
    _check_reconciliation_landed(drafts, outcome)
    return state.ran(
        "reconcile lines", drafts=drafts, consistency=outcome
    ).noting(f"cross-line consistency: {outcome.outcome.value} — {outcome.detail}")


def _drafted(drafts: Sequence[LineDraft]) -> tuple[DraftedLine, ...]:
    return tuple(
        DraftedLine(
            line_id=draft.line_id,
            source_name=draft.line.description.value,
            description=draft.description.text.value,
            code=draft.classification.code.value
            if draft.classification.code is not None
            else None,
            supplementary_unit=draft.classification.supplementary_unit,
        )
        for draft in drafts
    )


def _apply_changes(draft: LineDraft, outcome: ConsistencyOutcome) -> LineDraft:
    """Fold this line's changes into the draft, each as a transform on the value's chain.

    The reconciler hands back a `Transform` per change precisely so the caller can append
    it, which keeps a filed value walkable back to the ink through every hand that touched
    it. Nothing here invents provenance or a confidence: the value keeps the account its
    producer attached and gains one more link.
    """
    changes = [c for c in outcome.changes if c.line_id == draft.line_id]
    if not changes:
        return draft

    description = draft.description
    classification = draft.classification
    for change in changes:
        if change.field is ConsistencyField.DESCRIPTION:
            description = description.model_copy(
                update={
                    "text": description.text.with_transform(
                        change.transform, change.transform.after
                    )
                }
            )
        elif change.field is ConsistencyField.CODE:
            classification = _recoded(classification, change)
        elif change.field is ConsistencyField.SUPPLEMENTARY_UNIT:
            classification = classification.model_copy(
                update={"supplementary_unit": None}
            )
    return draft.model_copy(
        update={"description": description, "classification": classification}
    )


def _recoded(
    classification: LineClassification, change: LineChange
) -> LineClassification:
    if classification.code is None:
        raise ContractError(
            f"line {change.line_id}: cross-line reconciliation returned a code change on "
            "a line that has no code. Its own contract refuses to fill an abstention, so "
            "this is a breach of that contract rather than a degradation to absorb."
        )
    return classification.model_copy(
        update={
            "code": classification.code.with_transform(
                change.transform, change.transform.after
            ),
            "needs_review": True,
            "decided_by": CONSISTENCY_STAGE,
            "rationale": (
                f"{classification.rationale} Cross-line reconciliation then changed the "
                f"code to {change.transform.after}: {change.transform.reason}"
            ),
        }
    )


def _check_reconciliation_landed(
    drafts: Sequence[LineDraft], outcome: ConsistencyOutcome
) -> None:
    """The applied drafts must say what the outcome says they say.

    The reconciler reports its result twice — once as the final line, once as the change
    that produced it — and this run applies the second. Two reports that disagree would
    file one and print the other, so they are checked against each other rather than
    trusted to agree.
    """
    reconciled = {line.line_id: line for line in outcome.lines}
    if len(reconciled) != len(drafts):
        raise ContractError(
            f"cross-line reconciliation returned {len(reconciled)} line(s) for "
            f"{len(drafts)} drafted line(s). Every input line comes back, changed or not."
        )
    for draft in drafts:
        line = reconciled.get(draft.line_id)
        if line is None:
            raise ContractError(
                f"cross-line reconciliation returned no line {draft.line_id}. Every "
                "input line comes back, changed or not."
            )
        code = draft.classification.code.value if draft.classification.code else None
        if line.description != draft.description.text.value or line.code != code:
            raise ContractError(
                f"line {draft.line_id}: the reconciled line and the changes it reported "
                "disagree. One of them would be filed and the other printed."
            )


# --- assembly, filing, review ---------------------------------------------------------


def assemble_declaration(state: RunState, ports: Ports) -> RunState:
    """A23, first half. Every cross-field rule: units, weights, quantities, totals, text.

    No value is ever a hard failure here: an unknown, inferred or defaulted value is
    omitted or defaulted and a typed review item is emitted in its place.
    """
    note = state.note_reading.consignment_note if state.note_reading else None
    submission = AssemblyInput(
        invoice=state.require_invoice(),
        lines=state.drafts,
        consignment_note=note,
        profile=state.input.profile,
    )
    declaration, items = _assemble(submission, ports.tables)
    return state.ran(
        "assemble declaration", declaration=declaration, assembly_items=items
    )


def write_filing(state: RunState, ports: Ports) -> RunState:
    """A23, second half. The one module that knows the filed format writes it.

    Conformance is checked before the document leaves, never discovered on filing: the
    portal's three failure signals are opaque and name no field.
    """
    return state.ran("write filing", filed=write_declaration(state.require_declaration()))


def build_review_report(state: RunState, ports: Ports) -> RunState:
    """A24. Everything a human must look at, grouped by line and ordered by consequence.

    Nothing is computed here. Every item was raised by the module that met the
    uncertainty, and every value carries the provenance and confidence its producer
    attached.
    """
    filed = state.require_filed()
    consistency_items = state.consistency.review_items if state.consistency else ()
    items = (
        *state.assembly_items,
        *filed.review_items,
        *consistency_items,
        *state.run_items,
    )
    report = build_report(items, reported_values(state.require_declaration()))
    return state.ran("build review report", report=report)


# --- helpers --------------------------------------------------------------------------


def _one_result_per_line(
    invoice: InvoiceRecord,
    results: Sequence[LineDescription] | Sequence[LineClassification],
    what: str,
    stage: str,
) -> None:
    produced = {result.line_id for result in results}
    expected = {line.line_id for line in invoice.goods_lines}

    missing = sorted(expected - produced, key=int)
    if missing:
        named = ", ".join(
            f"{line.line_id} ({line.description.value!r})"
            for line in invoice.goods_lines
            if line.line_id in set(missing)
        )
        raise ContractError(
            f"the {stage!r} stage returned no {what} for goods line(s) {named}. Every "
            f"input line must have a result keyed by its id: filing a declaration that "
            f"silently drops a line files a different shipment."
        )

    unexpected = sorted(produced - expected)
    if unexpected:
        raise ContractError(
            f"the {stage!r} stage returned a {what} for line id(s) "
            f"{', '.join(unexpected)}, which this invoice does not have. A result keyed "
            "to nothing would attach to whichever line the join happened to reach."
        )
    if len(results) != len(expected):
        raise ContractError(
            f"the {stage!r} stage returned {len(results)} {what}(s) for "
            f"{len(expected)} goods line(s): a line id was answered more than once, and "
            "the last answer would silently win."
        )


def _evidence_not_read(grouped) -> ReviewItem:
    """Supporting documents were accepted and nobody read them. The operator is told.

    Dossier 02 §1: the run never asks a question, so every uncertainty leaves as an item.
    A catalogue or specification sheet that reached the run and was not consulted is
    exactly such an uncertainty — the descriptions and the codes were drafted without it.
    """
    names = ", ".join(
        page.rendered.source_document_id
        for document in grouped.supporting_evidence
        for page in document.pages[:1]
    )
    return ReviewItem(
        kind=ReviewKind.NEEDS_REVIEW,
        concept="supporting evidence",
        detail=(
            f"{len(grouped.supporting_evidence)} supporting document(s) ({names}) were "
            "submitted and were not read: no evidence enricher is configured in this "
            "build. Every description and every code was drafted from the invoice alone, "
            "so anything only the catalogue or specification states is missing from them."
        ),
        remedy="Check the drafted lines against the supporting documents by hand.",
    )


__all__ = [
    "STAGE",
    "assemble_declaration",
    "assemble_lines",
    "build_contexts",
    "build_review_report",
    "classify_lines",
    "classify_pages",
    "enrich_evidence",
    "gate_goods_lines",
    "group_pages",
    "guard_completeness",
    "intake",
    "rasterize",
    "read_documents",
    "reconcile_lines",
    "write_descriptions",
    "write_filing",
]
