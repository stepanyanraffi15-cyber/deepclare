"""Build a trace from a realistic run and print it. No network, no model, no dataset.

The records below are the shapes the pipeline actually emits — the `ModelCall` the model
adapter returns, the `Candidate` list the reference store returns, the printed-code fast
path taking a dead end and having its prefix cleared by the reset node, an abstention on a
material split — assembled through the recorder exactly as an orchestrator would assemble
them, and printed with the pinned versions at the top.

Three things it demonstrates that the unit tests state one at a time:

* the pinned versions, the axis fingerprints, and the list of what this build cannot pin;
* redaction on a rendered prompt that really does contain a seller, an address, a tax
  code, an email and a phone number, with the commodity codes left intact;
* the attribution rule applied to two later runs — one a single-axis change, one a
  compound change that licenses no claim at all.

Run it: .venv/bin/python tests/check_trace_report.py
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from deepclare.domain import (
    DocumentRole,
    InvoiceGoodsLine,
    InvoiceRecord,
    Party,
    Provenance,
    Traced,
    ValueOrigin,
)
from deepclare.models import Decoding, ModelCall, ModelTier, TokenUsage
from deepclare.reference.store import Candidate, Entry
from deepclare.trace import (
    UNPINNED,
    AbstentionKind,
    ArtifactKind,
    ArtifactStore,
    CaptureLevel,
    CapturePolicy,
    CodePins,
    ConfigurationPins,
    DataPins,
    EnvironmentPins,
    ModelPins,
    Pin,
    PromptPin,
    RetentionPolicy,
    Retrieval,
    RunManifest,
    StageModel,
    TraceRecorder,
    compare_manifests,
    identities_in,
    identity_leaks,
    new_case_id,
    new_run_id,
    render_trace,
)
from deepclare.trace.sink import JsonlTraceSink

# The vintage and the embedding pairing are the ones the installed reference artifact
# declares. Written out here rather than read, because this script must run with no
# dataset present.
NOMENCLATURE_VINTAGE = "2026-06-15T18:56:51.923392+00:00"
EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768

DECODING = Decoding(max_output_tokens=8192)


def extracted() -> Provenance:
    return Provenance(
        origin=ValueOrigin.EXTRACTED,
        source_document_id="upload-1-invoice.pdf",
        source_document_role="invoice",
        stage="reading",
    )


def traced(value: str) -> Traced[str]:
    return Traced[str](value=value, provenance=extracted())


def invoice() -> InvoiceRecord:
    return InvoiceRecord(
        source_document_id="upload-1-invoice.pdf",
        role=DocumentRole.INVOICE,
        invoice_number=traced("INV-2026-0041"),
        invoice_date=traced("12.03.2026"),
        currency=traced("EUR"),
        seller=Party(
            name=traced("ARDSHIN TRADING LLC"),
            address=traced("14 Komitas Avenue, Yerevan 0051"),
            tax_code=traced("02845517"),
        ),
        buyer=Party(
            name=traced("NORTHWIND IMPORTS OJSC"),
            address=traced("3 Tigran Mets Street, Yerevan 0005"),
            tax_code=traced("77341902"),
        ),
        goods_lines=(
            InvoiceGoodsLine(
                line_id="1",
                description=traced("TERMINAL BLOCK 4 MM"),
                quantity=Traced[Decimal](value=Decimal("500"), provenance=extracted()),
                printed_customs_code=traced("8536.90.10.00.00"),
            ),
            InvoiceGoodsLine(
                line_id="2",
                description=traced("CLOTHES HANGERS, 42 CM"),
                quantity=Traced[Decimal](value=Decimal("1200"), provenance=extracted()),
            ),
        ),
    )


def model_call(
    *,
    tier: ModelTier,
    model_id: str,
    prompt_name: str,
    prompt_version: str,
    prompt_tokens: int,
    output_tokens: int,
    reasoning_tokens: int = 0,
    pages: int = 0,
) -> ModelCall:
    return ModelCall(
        tier=tier,
        model_id=model_id,
        model_version=f"{model_id}-002",
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        decoding=DECODING,
        usage=TokenUsage(
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=prompt_tokens + output_tokens + reasoning_tokens,
        ),
        page_image_count=pages,
    )


def candidates(rows: tuple[tuple[str, float, str], ...]) -> tuple[Candidate, ...]:
    """`rows` are (code, similarity, taxonomic path), as the store returns them."""
    return tuple(
        Candidate(
            code=code,
            similarity=score,
            entry=Entry(
                code=code, level=5, name_en=path.split(" › ")[-1], path_en=path
            ),
        )
        for code, score, path in rows
    )


def run_manifest(run_id: str, policy: CapturePolicy) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        created_at=datetime.now(UTC),
        data=DataPins(
            nomenclature_vintage=NOMENCLATURE_VINTAGE,
            embedding_model=EMBEDDING_MODEL,
            embedding_dimensions=EMBEDDING_DIMENSIONS,
            canonical_text_structure_version="chapter-heading-leaf/1",
            index_build_id="qdrant_exim/14332",
            nomenclature_source="exim.src.am ԱՏԳ ԱԱ tree (id-enumeration crawl)",
            code_lists=(
                Pin(name="countries", value=UNPINNED),
                Pin(name="units", value=UNPINNED),
            ),
        ),
        models=ModelPins(
            stages=(
                StageModel(stage="intake", tier="cheap", model_id="gemini-3.5-flash-lite", decoding=DECODING),
                StageModel(stage="reading", tier="standard", model_id="gemini-3.6-flash", decoding=DECODING),
                StageModel(stage="description", tier="standard", model_id="gemini-3.6-flash", decoding=DECODING),
                StageModel(stage="classification", tier="standard", model_id="gemini-3.6-flash", decoding=DECODING),
                StageModel(stage="classification", tier="strong", model_id="gemini-2.5-pro", decoding=DECODING),
            )
        ),
        prompts=(
            PromptPin(name="classify_page_type", version="1", stage="intake"),
            PromptPin(name="read_invoice", version="1", stage="reading"),
            PromptPin(name="write_description", version="1", stage="description"),
            PromptPin(name="shortlist_chapters", version="1", stage="classification"),
            PromptPin(name="pick_heading", version="1", stage="classification"),
            PromptPin(name="pick_code", version="1", stage="classification"),
        ),
        configuration=ConfigurationPins.from_policy(
            policy,
            settings=(
                Pin(name="candidate_limit", value="30"),
                Pin(name="review_below_confidence", value="0.7"),
                Pin(name="review_below_heading_agreement", value="0.5"),
                Pin(name="printed_code_fast_path", value="on"),
                Pin(name="subheading_preference", value="off"),
                Pin(name="verification", value="off"),
            ),
        ),
        code=CodePins(build_identifier=UNPINNED),
        environment=EnvironmentPins(
            seeds=(Pin(name="decoding.seed", value="1"),),
            notes=("temperature 0, top_p 1, top_k 1 on every stage",),
        ),
    )


def record_run(recorder: TraceRecorder, record: InvoiceRecord) -> None:
    """Everything an orchestrator would tell the trace, in the order it would tell it."""

    with recorder.stage("intake"):
        with recorder.node("A2 route", entry_state={"files": 2}) as draft:
            draft.decided("2 documents: 1 invoice (pdf, 2 pages), 1 catalogue (workbook)")
            draft.exited({"page_bearing": 1, "page_less": 1})
        with recorder.node("A4 page classify") as draft:
            draft.model_call(
                model_call(
                    tier=ModelTier.CHEAP,
                    model_id="gemini-3.5-flash-lite",
                    prompt_name="classify_page_type",
                    prompt_version="1",
                    prompt_tokens=1820,
                    output_tokens=42,
                    pages=2,
                )
            )
            draft.decided("page 1 invoice, page 2 consignment_note")
        with recorder.node("A5 group pages") as draft:
            draft.decided("invoice 1 page, consignment note 1 page, 1 page-less document")

    with recorder.stage("reading"):
        with recorder.node("A6 read invoice") as draft:
            draft.model_call(
                model_call(
                    tier=ModelTier.STANDARD,
                    model_id="gemini-3.6-flash",
                    prompt_name="read_invoice",
                    prompt_version="1",
                    prompt_tokens=6210,
                    output_tokens=1380,
                    pages=1,
                )
            )
            draft.decided("2 goods lines, seller and buyer blocks read, currency EUR")
            draft.exited({"invoice": record})
        # The identities are known only once a document has been read. Everything
        # captured from here on is masked against them.
        recorder.learn_identities(identities_in(record))
        with recorder.node("A14 evidence enrich") as draft:
            draft.degraded("no evidence enricher configured; the catalogue is carried unread")

    with recorder.stage("description"):
        for line_id, name, armenian in (
            ("1", "TERMINAL BLOCK 4 MM", "ՀԱՂՈՐԴԻՉ ՍԵՂՄԻՉ, 4 ՄՄ"),
            ("2", "CLOTHES HANGERS, 42 CM", "ՀԱԳՈՒՍՏԻ ԿԱԽԻՉ"),
        ):
            with recorder.node("A17 write description", line_id=line_id) as draft:
                draft.model_call(
                    model_call(
                        tier=ModelTier.STANDARD,
                        model_id="gemini-3.6-flash",
                        prompt_name="write_description",
                        prompt_version="1",
                        prompt_tokens=2940,
                        output_tokens=210,
                    )
                )
                draft.decided(f"{name} → {armenian}")
                draft.captured(
                    prompt=(
                        "Invoice INV-2026-0041 of 12.03.2026. Seller ARDSHIN TRADING LLC, "
                        "14 Komitas Avenue, Yerevan 0051, tax code 02845517, "
                        "ops@ardshin-trading.am, +374 10 555 123. Buyer NORTHWIND IMPORTS "
                        f"OJSC, tax code 77341902. Goods line: {name}. Write the Armenian "
                        "description that will be filed."
                    ),
                    response=f'{{"filed_text": "{armenian}", "completeness": "high"}}',
                )

    with recorder.stage("classification"):
        # Line 1 — printed code on the invoice, fast path, dead end, reset, full narrowing.
        with recorder.node("C0 printed code", line_id="1") as draft:
            draft.decided("invoice prints 8536.90.10.00.00 → prefix 853690")
            draft.exited({"printed_prefix": "853690"})
        with recorder.node("C4 retrieve", line_id="1") as draft:
            draft.retrieved(
                Retrieval.from_candidates(
                    query="electrical apparatus — terminal block 4 mm",
                    scope="p6=853690",
                    candidates=(),
                )
            )
            draft.abstained(
                AbstentionKind.NO_CANDIDATES,
                "the 6-digit scope 853690 retrieved nothing at any widening rung",
            )
        with recorder.node("C7 reset", line_id="1") as draft:
            draft.superseded(
                slot="printed_prefix",
                previous="853690",
                reason="dead end; cleared so the entry branch cannot retake the fast path",
            )
            draft.decided("printed prefix cleared, one retry through full narrowing")
        with recorder.node("C1 shortlist chapters", line_id="1") as draft:
            draft.model_call(
                model_call(
                    tier=ModelTier.STANDARD,
                    model_id="gemini-3.6-flash",
                    prompt_name="shortlist_chapters",
                    prompt_version="1",
                    prompt_tokens=5100,
                    output_tokens=64,
                )
            )
            draft.decided("chapters 85, 39")
        with recorder.node("C2 pick heading", line_id="1") as draft:
            draft.model_call(
                model_call(
                    tier=ModelTier.STANDARD,
                    model_id="gemini-3.6-flash",
                    prompt_name="pick_heading",
                    prompt_version="1",
                    prompt_tokens=7300,
                    output_tokens=96,
                )
            )
            draft.decided("headings 8536, 8535; query 'terminal block for wire connection'")
        with recorder.node("C4 retrieve", line_id="1", attempt=2) as draft:
            draft.retrieved(
                Retrieval.from_candidates(
                    query="electrical apparatus — terminal block for wire connection",
                    scope="p4 in (8536, 8535)",
                    candidates=candidates(
                        (
                            ("8536901000", 0.8412, "electrical apparatus › connections for wires and cables › terminal blocks"),
                            ("8536909000", 0.7788, "electrical apparatus › connections for wires and cables › other"),
                            ("8536500600", 0.7215, "electrical apparatus › other switches › electronic switches"),
                            ("8535900000", 0.6904, "electrical apparatus › for a voltage exceeding 1000 V › other"),
                        )
                    ),
                    chosen_code="8536901000",
                    dropped_unknown_codes=0,
                )
            )
            draft.decided("30 requested, 4 in scope")
        with recorder.node("C5 pick code", line_id="1") as draft:
            draft.model_call(
                model_call(
                    tier=ModelTier.STRONG,
                    model_id="gemini-2.5-pro",
                    prompt_name="pick_code",
                    prompt_version="1",
                    prompt_tokens=9840,
                    output_tokens=240,
                    reasoning_tokens=1460,
                )
            )
            draft.decided("8536901000, composite confidence 0.9525, no review flag")
            draft.exited({"code": "8536901000", "needs_review": False})

        # Line 2 — the material split the specification records as unsolvable from input.
        with recorder.node("C1 shortlist chapters", line_id="2") as draft:
            draft.model_call(
                model_call(
                    tier=ModelTier.STANDARD,
                    model_id="gemini-3.6-flash",
                    prompt_name="shortlist_chapters",
                    prompt_version="1",
                    prompt_tokens=5100,
                    output_tokens=58,
                )
            )
            draft.decided("chapters 39, 44")
        with recorder.node("C4 retrieve", line_id="2") as draft:
            draft.retrieved(
                Retrieval.from_candidates(
                    query="articles of plastics — clothes hangers",
                    scope="p2 in (39, 44)",
                    candidates=candidates(
                        (
                            ("3924900009", 0.7402, "plastics › household articles › other"),
                            ("4421100000", 0.7311, "wood articles › clothes hangers"),
                            ("3926909709", 0.6980, "plastics › other articles › other"),
                        )
                    ),
                )
            )
            draft.decided("3 candidates across two chapters")
        with recorder.node("C5 pick code", line_id="2") as draft:
            draft.model_call(
                model_call(
                    tier=ModelTier.STRONG,
                    model_id="gemini-2.5-pro",
                    prompt_name="pick_code",
                    prompt_version="1",
                    prompt_tokens=9120,
                    output_tokens=310,
                    reasoning_tokens=2100,
                )
            )
            draft.abstained(
                AbstentionKind.NONE_CHOSEN,
                "material decisive: wood is 4421100000, plastic is 3924900009; the line "
                "states no material. Resolving evidence: state the material of the hangers.",
            )

    with recorder.stage("assembly"):
        with recorder.node("A24 assemble") as draft:
            draft.decided("2 goods items, 1 code assigned, 1 abstention, 4 review items")
        with recorder.node("A25 consistency") as draft:
            draft.degraded("no reconciler configured; lines are filed as drafted")

    with recorder.stage("filing"):
        with recorder.node("A26 write filing") as draft:
            draft.decided("document written; conforms=True filable=False (unconfirmed names)")

    recorder.note("1 of 2 goods lines received a commodity code")
    recorder.note("the catalogue was carried but not read — no evidence enricher configured")


def main() -> None:
    run_id = new_run_id()
    case_id = new_case_id()
    policy = CapturePolicy(level=CaptureLevel.PAYLOADS, truncation_chars=240)
    retention = RetentionPolicy(declared_by="check_trace_report.py")
    manifest = run_manifest(run_id, policy)
    record = invoice()

    workspace = Path(tempfile.mkdtemp(prefix="deepclare-trace-"))
    store = ArtifactStore(root=workspace, manifest=manifest, retention=retention)
    sink = JsonlTraceSink(workspace / run_id / "nodes.jsonl")

    recorder = TraceRecorder(
        run_id=run_id,
        case_id=case_id,
        manifest=manifest,
        capture=policy,
        retention=retention,
        sink=sink,
    )
    record_run(recorder, record)
    recorder.artifact(
        store.retain_text(ArtifactKind.INPUT_DOCUMENT, "invoice.txt", "…as received…")
    )
    recorder.artifact(
        store.retain_text(
            ArtifactKind.STRUCTURED_EXTRACTION, "invoice.json", record.model_dump_json()
        )
    )
    recorder.artifact(
        store.retain_text(ArtifactKind.EMITTED_DOCUMENT, "declaration.xml", "<ESADout/>")
    )
    recorder.finish()
    sink.close()

    trace = recorder.trace()
    print(render_trace(trace))

    print("=" * 100)
    print("REDACTION — proof, not assertion")
    print("=" * 100)
    identities = identities_in(record)
    print(f"  identity strings this run handled : {len(identities)}")
    for identity in identities:
        print(f"    {identity.klass.value:<20} {identity.text}")
    leaks = identity_leaks(trace, identities)
    print(f"  identity strings still in the trace: {len(leaks)}  {leaks}")
    print(f"  and in the trace file on disk     : {len(identity_leaks(sink.path.read_text(encoding='utf-8'), identities))}")

    print()
    print("=" * 100)
    print("ATTRIBUTION — dossier 08 §14.2 applied to two later runs")
    print("=" * 100)
    later = run_manifest(new_run_id(), policy)
    swapped_model = later.model_copy(
        update={
            "models": ModelPins(
                stages=tuple(
                    stage.model_copy(update={"model_id": "gemini-3.6-pro"})
                    if stage.tier == "strong"
                    else stage
                    for stage in later.models.stages
                )
            )
        }
    )
    print(f"  model swap only        : {compare_manifests(manifest, swapped_model).statement()}")

    swapped_both = swapped_model.model_copy(
        update={
            "data": swapped_model.data.model_copy(
                update={"nomenclature_vintage": "2027-01-10T00:00:00+00:00"}
            )
        }
    )
    print(f"  model swap + new tree  : {compare_manifests(manifest, swapped_both).statement()}")
    print(f"  same build twice       : {compare_manifests(manifest, later).statement()}")

    print()
    print(f"artifacts and trace file: {store.directory}")


if __name__ == "__main__":
    main()
