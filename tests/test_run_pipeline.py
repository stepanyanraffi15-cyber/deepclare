"""The outer chain, exercised end to end with fake ports. Nothing here calls a provider.

Every capability the chain uses is injected, which is what makes this possible: the fakes
below are ordinary objects satisfying the same protocols the real adapters do, and the
chain cannot tell the difference because it never asks.

What is tested is the orchestration and nothing else — the branch conditions, the
completeness contract, the write-back of a cross-line change, and the fact that a
best-effort stage failing leaves a filable declaration. The stages' own rules are tested
in their own modules and are not restated here.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from deepclare.assembly.tables import load_tables
from deepclare.classification.records import LineClassification
from deepclare.consistency.records import (
    ConsistencyField,
    ConsistencyOutcome,
    LineChange,
    PassOutcome,
    ReconciledLine,
    untouched,
)
from deepclare.description.records import (
    DescriptionCompleteness,
    LineDescription,
    ProductKind,
)
from deepclare.domain import (
    Confidence,
    DocumentRegion,
    DocumentRole,
    InvoiceGoodsLine,
    InvoiceRecord,
    PageClass,
    Party,
    Provenance,
    Traced,
    Transform,
    ValueOrigin,
)
from deepclare.intake.classifier import PageVerdict
from deepclare.intake.submission import SubmittedFile
from deepclare.models import Decoding, ModelCall, ModelTier, TokenUsage
from deepclare.reading.records import InvoiceReading
from deepclare.run import ContractError, Ports, RunInput, RunState, execute
from deepclare.run.pipeline import CHAIN

TABLES_DIR = Path(__file__).resolve().parents[1] / "reference_data"

CALL = ModelCall(
    tier=ModelTier.STANDARD,
    model_id="fake",
    prompt_name="fake_prompt",
    prompt_version="1",
    decoding=Decoding(max_output_tokens=100),
    usage=TokenUsage(),
)

GOODS = (
    ("1", "PLASTIC STORAGE BOX 40X60 CM", "3923101000"),
    ("2", "POLYETHYLENE BOTTLE 1 L", "3923301000"),
    ("3", "PP WOVEN SACK 50 KG", None),
)


# --- the values the fakes hand back ---------------------------------------------------


def _extracted() -> Provenance:
    return Provenance(
        origin=ValueOrigin.EXTRACTED,
        source_document_id="doc1",
        source_document_role="invoice",
        region=DocumentRegion(page_number=1),
        stage="reading",
    )


def _generated(stage: str, prompt: str) -> Provenance:
    return Provenance(
        origin=ValueOrigin.GENERATED, stage=stage, prompt_name=prompt, prompt_version="1"
    )


def read(value: object) -> Traced:
    return Traced(
        value=value, provenance=_extracted(), confidence=Confidence(extraction=0.9)
    )


def invoice_record() -> InvoiceRecord:
    return InvoiceRecord(
        source_document_id="doc1",
        goods_lines=tuple(
            InvoiceGoodsLine(
                line_id=line_id,
                description=read(name),
                quantity=read(Decimal("100")),
                unit=read("PCS"),
                total_price=read(Decimal("500.00")),
                package_count=read(Decimal("10")),
                package_type=read("CARTON"),
                net_weight=read(Decimal("120")),
                weight_unit=read("KG"),
                printed_customs_code=read(code) if code else None,
            )
            for line_id, name, code in GOODS
        ),
        invoice_number=read("NV-1"),
        currency=read("EUR"),
        origin_country=read("NORWAY"),
        seller=Party(name=read("NORDVEK PLASTICS LLC")),
        buyer=Party(name=read("ARARAT IMPORT LLC"), tax_code=read("01234567")),
        total_amount=read(Decimal("1500.00")),
    )


def description_for(line_id: str, text: str = "") -> LineDescription:
    provenance = _generated("description", "write_description")
    confidence = Confidence(derivation=0.9)
    return LineDescription(
        line_id=line_id,
        text=Traced(
            value=text or f"ԱՊՐԱՆՔ ԹԻՎ {line_id}",
            provenance=provenance,
            confidence=confidence,
        ),
        search_term=Traced(
            value="ԱՊՐԱՆՔ", provenance=provenance, confidence=confidence
        ),
        product_kind=Traced(
            value=ProductKind.PIECE, provenance=provenance, confidence=confidence
        ),
        completeness=DescriptionCompleteness.HIGH,
        call=CALL,
    )


def classification_for(line_id: str, code: str | None) -> LineClassification:
    if code is None:
        return LineClassification(
            line_id=line_id,
            rationale="Candidates split on the weave and nothing states it.",
            resolving_evidence="The weave of the sack.",
            decided_by="code assignment graph",
        )
    return LineClassification(
        line_id=line_id,
        code=Traced(
            value=code,
            provenance=_generated("classification", "pick_code"),
            confidence=Confidence(derivation=0.82),
        ),
        needs_review=False,
        rationale="Retrieved and picked.",
        supplementary_unit="шт",
        decided_by="code assignment graph",
    )


# --- the fakes ------------------------------------------------------------------------


class FakeReader:
    def __init__(self, invoice: InvoiceRecord | None = None) -> None:
        self.invoice = invoice or invoice_record()
        self.notes_read = 0

    def read_invoice(self, document):
        return InvoiceReading(invoice=self.invoice, call=CALL)

    def read_consignment_note(self, document):  # pragma: no cover - not reached here
        self.notes_read += 1
        raise AssertionError("this submission carries no consignment note")


class FakeWriter:
    def __init__(self, skip: str | None = None) -> None:
        self.skip = skip
        self.written: list[str] = []

    def write(self, context):
        self.written.append(context.line_id)
        if context.line_id == self.skip:
            return description_for("1")  # the wrong line id, on purpose
        return description_for(context.line_id)


class FakeClassifier:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def classify(self, line):
        self.seen.append(line.line_id)
        code = dict((line_id, code) for line_id, _, code in GOODS)[line.line_id]
        return classification_for(line.line_id, code)


class FakePageClassifier:
    def __init__(self) -> None:
        self.calls = 0

    def classify(self, pages):
        self.calls += 1
        return [
            PageVerdict(page=position, page_type=PageClass.INVOICE)
            for position in range(1, len(pages) + 1)
        ]


class RecodingReconciler:
    """Changes line 2's code and description, exactly as the real pass reports one."""

    NEW_CODE = "3923290000"
    NEW_TEXT = "ԱՊՐԱՆՔ ԹԻՎ 2, ՀԱՄԱՁԱՅՆԵՑՎԱԾ"

    def reconcile(self, lines):
        changes = (
            LineChange(
                line_id="2",
                field=ConsistencyField.DESCRIPTION,
                transform=Transform(
                    operation="conform-description",
                    before=lines[1].description,
                    after=self.NEW_TEXT,
                    reason="the other lines of this shipment word it this way",
                ),
            ),
            LineChange(
                line_id="2",
                field=ConsistencyField.CODE,
                transform=Transform(
                    operation="align-code",
                    before=lines[1].code or "",
                    after=self.NEW_CODE,
                    reason="the sibling lines carry this code for the same goods",
                ),
            ),
            LineChange(
                line_id="2",
                field=ConsistencyField.SUPPLEMENTARY_UNIT,
                transform=Transform(
                    operation="clear-supplementary-unit",
                    before="шт",
                    after="",
                    reason="the commodity code changed",
                ),
            ),
        )
        return ConsistencyOutcome(
            outcome=PassOutcome.APPLIED,
            detail="one line changed",
            lines=tuple(
                ReconciledLine(
                    line_id=line.line_id,
                    description=self.NEW_TEXT if line.line_id == "2" else line.description,
                    code=self.NEW_CODE if line.line_id == "2" else line.code,
                    supplementary_unit=None
                    if line.line_id == "2"
                    else line.supplementary_unit,
                    changed_fields=(
                        (ConsistencyField.DESCRIPTION, ConsistencyField.CODE)
                        if line.line_id == "2"
                        else ()
                    ),
                )
                for line in lines
            ),
            changes=changes,
        )


class FailingReconciler:
    """The critique call did not land: every line comes back exactly as it went in."""

    def reconcile(self, lines):
        return untouched(
            lines,
            outcome=PassOutcome.CRITIQUE_FAILED,
            detail="the critique call did not land, so the whole pass was abandoned.",
        )


# --- fixtures -------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tables():
    return load_tables(TABLES_DIR)


@pytest.fixture
def submission() -> RunInput:
    """A one-page PDF is enough: the reader is faked and never looks at the image."""
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )
    return RunInput(
        files=(
            SubmittedFile(
                file_name="invoice.pdf", content=pdf, declared_role=DocumentRole.INVOICE
            ),
        )
    )


def ports_with(tables, **overrides) -> Ports:
    defaults = dict(
        reader=FakeReader(),
        classifier=FakeClassifier(),
        description_writer=FakeWriter(),
        tables=tables,
        page_classifier=FakePageClassifier(),
        reconciler=None,
    )
    return Ports(**(defaults | overrides))


# --- the chain runs -------------------------------------------------------------------


def test_the_chain_produces_a_declaration_and_a_report(tables, submission):
    ports = ports_with(tables)
    state = execute(submission, ports)

    assert state.goods_line_count == 3
    assert state.codes_assigned == 2
    assert state.codes_abstained == 1
    assert state.require_filed().xml.startswith("<?xml")
    assert state.require_filed().conformance.filable
    assert state.require_report().total_items > 0


def test_every_stage_that_ran_is_named_in_order(tables, submission):
    state = execute(submission, ports_with(tables))
    assert list(state.stages_run) == [
        node.name for node in CHAIN if node.name not in state.stages_skipped
    ]


def test_the_abstained_line_files_no_code_and_says_why(tables, submission):
    state = execute(submission, ports_with(tables))
    item = next(
        item
        for item in state.require_report().groups
        for entry in item.entries
        for item in (entry.item,)
        if item.line_id == "3" and item.concept == "line commodity code"
    )
    assert "The weave of the sack." == item.remedy
    third = next(g for g in state.require_declaration().goods if g.line_id == "3")
    assert third.commodity_code is None


# --- the branches ---------------------------------------------------------------------


def test_without_a_page_classifier_the_stage_is_skipped_and_pages_keep_their_role(
    tables, submission
):
    ports = ports_with(tables, page_classifier=None)
    state = execute(submission, ports)

    assert "classify pages" in state.stages_skipped
    assert state.verdicts == ()
    # The grouper's own rule then places the page on its file's declared role.
    assert state.require_grouped().invoice.pages[0].classification.assigned_role is (
        DocumentRole.INVOICE
    )
    assert state.goods_line_count == 3


def test_a_page_classifier_is_called_once_for_the_whole_batch(tables, submission):
    classifier = FakePageClassifier()
    execute(submission, ports_with(tables, page_classifier=classifier))
    assert classifier.calls == 1


def test_without_a_reconciler_the_drafted_lines_pass_through_untouched(
    tables, submission
):
    state = execute(submission, ports_with(tables))
    assert "reconcile lines" in state.stages_skipped
    assert state.consistency is None
    assert [d.description.text.value for d in state.drafts] == [
        "ԱՊՐԱՆՔ ԹԻՎ 1",
        "ԱՊՐԱՆՔ ԹԻՎ 2",
        "ԱՊՐԱՆՔ ԹԻՎ 3",
    ]


# --- the best-effort stage ------------------------------------------------------------


def test_a_reconciliation_change_reaches_the_filed_document(tables, submission):
    state = execute(submission, ports_with(tables, reconciler=RecodingReconciler()))

    second = next(d for d in state.drafts if d.line_id == "2")
    assert second.description.text.value == RecodingReconciler.NEW_TEXT
    assert second.classification.code is not None
    assert second.classification.code.value == RecodingReconciler.NEW_CODE
    assert second.classification.supplementary_unit is None
    assert second.classification.needs_review

    # The chain is append-only: the change is a transform on the value's own chain, so a
    # filed value still walks back to the ink.
    operations = [
        transform.operation
        for transform in second.classification.code.provenance.transforms
    ]
    assert "align-code" in operations

    filed = next(g for g in state.require_declaration().goods if g.line_id == "2")
    assert filed.commodity_code is not None
    assert filed.commodity_code.value.startswith(RecodingReconciler.NEW_CODE)


def test_a_failed_critique_leaves_the_lines_alone_and_the_run_succeeds(
    tables, submission
):
    state = execute(submission, ports_with(tables, reconciler=FailingReconciler()))

    assert state.consistency is not None
    assert state.consistency.outcome is PassOutcome.CRITIQUE_FAILED
    assert [d.description.text.value for d in state.drafts] == [
        "ԱՊՐԱՆՔ ԹԻՎ 1",
        "ԱՊՐԱՆՔ ԹԻՎ 2",
        "ԱՊՐԱՆՔ ԹԻՎ 3",
    ]
    assert state.require_filed().conformance.filable


# --- the completeness contract --------------------------------------------------------


def test_a_missing_per_line_result_names_the_line_rather_than_failing_a_lookup(
    tables, submission
):
    # The writer answers for line 1 twice and never for line 3.
    ports = ports_with(tables, description_writer=FakeWriter(skip="3"))
    with pytest.raises(ContractError) as raised:
        execute(submission, ports)

    message = str(raised.value)
    assert "3" in message
    assert "PP WOVEN SACK 50 KG" in message
    assert "write descriptions" in message


def test_a_result_keyed_to_a_line_that_does_not_exist_is_refused():
    """A batch-answering stage can key a result to nothing; this is where that is caught.

    Not reachable through the writer port, which is called once per line and so can only
    ever produce a gap. It is checked because the specification's own A17 sends its misses
    "in one order-preserving batch", and a batch can answer for a line nobody asked about.
    """
    from deepclare.run.stages import _one_result_per_line

    with pytest.raises(ContractError) as raised:
        _one_result_per_line(
            invoice_record(),
            [description_for(line_id) for line_id in ("1", "2", "3", "4")],
            "description",
            "write descriptions",
        )
    assert "4" in str(raised.value)


def test_one_line_answered_twice_is_refused():
    from deepclare.run.stages import _one_result_per_line

    with pytest.raises(ContractError) as raised:
        _one_result_per_line(
            invoice_record(),
            [description_for(line_id) for line_id in ("1", "2", "3", "3")],
            "description",
            "write descriptions",
        )
    assert "more than once" in str(raised.value)


def test_a_missing_classification_names_the_line_at_the_completeness_guard(
    tables, submission
):
    class ForgetfulClassifier(FakeClassifier):
        def classify(self, line):
            answered = super().classify(line)
            return answered if line.line_id != "3" else classification_for("2", None)

    with pytest.raises(ContractError) as raised:
        execute(submission, ports_with(tables, classifier=ForgetfulClassifier()))

    message = str(raised.value)
    assert "PP WOVEN SACK 50 KG" in message
    assert "classify lines" in message


def test_a_state_slot_read_before_its_stage_names_the_stage(submission):
    from deepclare.run import StateError

    with pytest.raises(StateError) as raised:
        RunState(input=submission).require_declaration()
    assert "assemble declaration" in str(raised.value)
