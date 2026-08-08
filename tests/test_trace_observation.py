"""M17 — the observation layer. No network, no model, no dataset.

Four groups, one per invariant the module decomposition states for M17: read-only with
respect to the run, version pinning that supports attribution, controllable capture
volume, and retention that nothing automates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

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
    AttributionVerdict,
    CaptureLevel,
    CapturePolicy,
    CodePins,
    ConfigurationPins,
    DataPins,
    EnvironmentPins,
    IdentityClass,
    IdentityValue,
    JsonlTraceSink,
    MemoryTraceSink,
    ModelPins,
    NodeOutcome,
    Pin,
    PromptPin,
    Redactor,
    RetentionPolicy,
    Retrieval,
    RunManifest,
    StageModel,
    TraceError,
    TraceRecorder,
    compare_manifests,
    identities_in,
    identity_leaks,
    new_run_id,
    read_trace_file,
)

RUN_ID = "run-20260809T000000Z-deadbeef"
CASE_ID = "case-000000000001"


# --- fixtures built from the shapes the producers actually emit ---------------


def extracted(document: str = "upload-1.pdf") -> Provenance:
    return Provenance(
        origin=ValueOrigin.EXTRACTED, source_document_id=document, stage="reading"
    )


def traced(value: str) -> Traced[str]:
    return Traced[str](value=value, provenance=extracted())


def invoice() -> InvoiceRecord:
    return InvoiceRecord(
        source_document_id="upload-1.pdf",
        role=DocumentRole.INVOICE,
        invoice_number=traced("INV-2026-0041"),
        seller=Party(
            name=traced("ARDSHIN TRADING LLC"),
            address=traced("14 Komitas Avenue, Yerevan"),
            tax_code=traced("02845517"),
        ),
        buyer=Party(name=traced("NORTHWIND IMPORTS OJSC"), tax_code=traced("77341902")),
        goods_lines=(
            InvoiceGoodsLine(
                line_id="1",
                description=traced("PORTLAND CEMENT CEM I 42.5 N"),
                quantity=Traced[Decimal](value=Decimal("1200"), provenance=extracted()),
            ),
        ),
    )


def call(prompt_name: str = "pick_code", tier: ModelTier = ModelTier.STRONG) -> ModelCall:
    return ModelCall(
        tier=tier,
        model_id="gemini-2.5-pro",
        model_version="gemini-2.5-pro-002",
        prompt_name=prompt_name,
        prompt_version="3",
        decoding=Decoding(max_output_tokens=8192),
        usage=TokenUsage(
            prompt_tokens=4100, output_tokens=180, reasoning_tokens=900, total_tokens=5180
        ),
    )


def candidates() -> tuple[Candidate, ...]:
    return tuple(
        Candidate(
            code=code,
            similarity=score,
            entry=Entry(code=code, level=5, name_en=name, path_en=f"cement — {name}"),
        )
        for code, score, name in (
            ("2523290000", 0.6951, "other portland cement"),
            ("2523210000", 0.6902, "white cement"),
            ("2523100000", 0.6738, "cement clinkers"),
        )
    )


def manifest(**overrides: object) -> RunManifest:
    base = {
        "run_id": RUN_ID,
        "created_at": datetime(2026, 8, 9, tzinfo=UTC),
        "data": DataPins(
            nomenclature_vintage="2026-06-15T18:56:51.923392+00:00",
            embedding_model="models/gemini-embedding-001",
            embedding_dimensions=768,
            canonical_text_structure_version="chapter-heading-leaf/1",
            index_build_id="qdrant_exim/14332",
            nomenclature_source="exim.src.am id-enumeration crawl",
            code_lists=(Pin(name="countries", value="2026-06-15"),),
        ),
        "models": ModelPins(
            stages=(
                StageModel(
                    stage="classification",
                    tier="strong",
                    model_id="gemini-2.5-pro",
                    decoding=Decoding(max_output_tokens=8192),
                ),
            )
        ),
        "prompts": (PromptPin(name="pick_code", version="3", stage="classification"),),
        "configuration": ConfigurationPins.from_policy(
            CapturePolicy(), settings=(Pin(name="candidate_limit", value="30"),)
        ),
        "code": CodePins(build_identifier="0000000"),
        "environment": EnvironmentPins(seeds=(Pin(name="decoding.seed", value="1"),)),
    }
    base.update(overrides)
    return RunManifest(**base)  # type: ignore[arg-type]


def recorder(
    policy: CapturePolicy | None = None,
    sink: MemoryTraceSink | None = None,
    identities: tuple[IdentityValue, ...] = (),
) -> tuple[TraceRecorder, MemoryTraceSink]:
    used_sink = sink or MemoryTraceSink()
    return (
        TraceRecorder(
            run_id=RUN_ID,
            case_id=CASE_ID,
            manifest=manifest(),
            capture=policy or CapturePolicy(),
            retention=RetentionPolicy(declared_by="test"),
            sink=used_sink,
            identities=identities,
        ),
        used_sink,
    )


# --- read-only with respect to the run ---------------------------------------


def test_every_recorder_method_a_run_calls_returns_none() -> None:
    """The structural guarantee: there is no value a run could branch on."""
    trace_recorder, _ = recorder()
    with trace_recorder.stage("classification") as bound:
        assert bound is None
        with trace_recorder.node("C5 pick", line_id="1") as draft:
            assert draft.decided("picked 2523290000") is None
            assert draft.model_call(call()) is None
            assert draft.exited({"code": "2523290000"}) is None
            assert draft.superseded(slot="printed_prefix", previous="252329", reason="reset") is None
    assert trace_recorder.note("one goods line") is None
    assert trace_recorder.finish() is None


def test_a_failing_node_is_recorded_and_the_exception_still_propagates() -> None:
    trace_recorder, sink = recorder()
    with pytest.raises(ValueError, match="retrieval died"):
        with trace_recorder.stage("classification"):
            with trace_recorder.node("C4 retrieve", line_id="1"):
                raise ValueError("retrieval died")
    assert len(sink.records) == 1
    assert sink.records[0].outcome is NodeOutcome.FAILED
    assert "retrieval died" in (sink.records[0].error or "")


@pytest.mark.parametrize("level", list(CaptureLevel))
def test_a_node_outside_any_stage_is_refused_at_every_level(level: CaptureLevel) -> None:
    """Including at `off`. A defect that appears only when tracing is turned up is a
    behaviour that varies on tracing."""
    trace_recorder, _ = recorder(CapturePolicy(level=level))
    with pytest.raises(TraceError, match="outside any stage"):
        with trace_recorder.node("C5 pick"):
            pass


def test_a_manifest_for_another_run_is_refused() -> None:
    with pytest.raises(TraceError, match="explains the wrong run"):
        TraceRecorder(
            run_id=new_run_id(),
            case_id=CASE_ID,
            manifest=manifest(),
            capture=CapturePolicy(),
            retention=RetentionPolicy(declared_by="test"),
            sink=MemoryTraceSink(),
        )


def test_the_two_abstentions_stay_distinguishable() -> None:
    trace_recorder, sink = recorder()
    with trace_recorder.stage("classification"):
        with trace_recorder.node("C4 retrieve", line_id="1") as draft:
            draft.abstained(AbstentionKind.NO_CANDIDATES, "the scope retrieved nothing")
        with trace_recorder.node("C5 pick", line_id="2") as draft:
            draft.abstained(AbstentionKind.NONE_CHOSEN, "material split, wood or plastic")
    kinds = [record.abstention for record in sink.records]
    assert kinds == [AbstentionKind.NO_CANDIDATES, AbstentionKind.NONE_CHOSEN]
    assert all(record.outcome is NodeOutcome.ABSTAINED for record in sink.records)


def test_a_superseded_slot_survives_the_loop_guard() -> None:
    trace_recorder, sink = recorder()
    with trace_recorder.stage("classification"):
        with trace_recorder.node("C7 reset", line_id="1") as draft:
            draft.superseded(
                slot="printed_prefix",
                previous="852990",
                reason="dead end; cleared so the entry branch cannot retake the fast path",
            )
    assert sink.records[0].superseded[0].previous == "852990"


def test_sequence_numbers_are_monotonic_and_a_line_journey_is_retrievable() -> None:
    trace_recorder, _ = recorder()
    with trace_recorder.stage("classification"):
        for line in ("1", "2", "1"):
            with trace_recorder.node("C5 pick", line_id=line) as draft:
                draft.decided(f"line {line}")
    trace = trace_recorder.trace()
    assert [node.sequence for node in trace.nodes] == [1, 2, 3]
    assert [node.sequence for node in trace.line("1")] == [1, 3]


# --- capture volume -----------------------------------------------------------


def test_capture_off_records_nothing_at_all() -> None:
    trace_recorder, sink = recorder(CapturePolicy(level=CaptureLevel.OFF))
    with trace_recorder.stage("reading"):
        with trace_recorder.node("A6 read", line_id="1") as draft:
            draft.decided("read 60 goods lines")
            draft.captured(prompt="whatever", response="whatever")
    assert sink.records == []
    assert trace_recorder.trace().nodes == ()


def test_records_level_keeps_the_account_and_no_document_content() -> None:
    trace_recorder, sink = recorder(CapturePolicy(level=CaptureLevel.RECORDS))
    with trace_recorder.stage("classification"):
        with trace_recorder.node("C5 pick", line_id="1") as draft:
            draft.model_call(call())
            draft.exited({"code": "2523290000"})
            draft.captured(prompt="ARDSHIN TRADING LLC …", response="{}")
    record = sink.records[0]
    assert record.call is not None and record.call.usage.total_tokens == 5180
    assert record.exit_state is None
    assert record.payload is None


def test_states_level_keeps_state_but_not_the_prompt() -> None:
    trace_recorder, sink = recorder(CapturePolicy(level=CaptureLevel.STATES))
    with trace_recorder.stage("classification"):
        with trace_recorder.node("C5 pick", entry_state={"query": "cement"}) as draft:
            draft.exited({"code": "2523290000"})
            draft.captured(prompt="…", response="…")
    record = sink.records[0]
    assert record.entry_state == {"query": "cement"}
    assert record.exit_state == {"code": "2523290000"}
    assert record.payload is None


def test_payload_level_keeps_both_and_honours_the_truncation_cap() -> None:
    trace_recorder, sink = recorder(
        CapturePolicy(level=CaptureLevel.PAYLOADS, truncation_chars=10)
    )
    with trace_recorder.stage("classification"):
        with trace_recorder.node("C5 pick") as draft:
            draft.captured(prompt="x" * 50, response="y" * 5)
    payload = sink.records[0].payload
    assert payload is not None
    assert payload.prompt == "x" * 10
    assert payload.response == "y" * 5
    assert payload.truncated is True


def test_truncation_can_be_disabled() -> None:
    policy = CapturePolicy(level=CaptureLevel.PAYLOADS, truncation_chars=None)
    trace_recorder, sink = recorder(policy)
    with trace_recorder.stage("classification"):
        with trace_recorder.node("C5 pick") as draft:
            draft.captured(prompt="x" * 50_000)
    payload = sink.records[0].payload
    assert payload is not None and payload.prompt is not None
    assert len(payload.prompt) == 50_000
    assert payload.truncated is False


def test_sampling_drops_content_but_never_the_node_record() -> None:
    policy = CapturePolicy(level=CaptureLevel.PAYLOADS, sampling_rate=0.0)
    trace_recorder, sink = recorder(policy)
    with trace_recorder.stage("classification"):
        with trace_recorder.node("C5 pick", entry_state={"query": "cement"}) as draft:
            draft.decided("picked 2523290000")
            draft.captured(prompt="secret", response="{}")
    record = sink.records[0]
    assert record.sampled is False
    assert record.entry_state is None and record.payload is None
    assert record.decision == "picked 2523290000"


def test_sampling_is_deterministic_in_the_run_and_the_sequence() -> None:
    policy = CapturePolicy(sampling_rate=0.5)
    first = [policy.samples(run_id=RUN_ID, sequence=n) for n in range(1, 40)]
    second = [policy.samples(run_id=RUN_ID, sequence=n) for n in range(1, 40)]
    assert first == second
    assert any(first) and not all(first)


# --- redaction ----------------------------------------------------------------


def test_no_identity_class_reaches_the_trace() -> None:
    """Dossier 08 §16.3's required proof, on a rendered prompt and a captured state."""
    record = invoice()
    identities = identities_in(record)
    assert {identity.klass for identity in identities} == {
        IdentityClass.ORGANIZATION_NAME,
        IdentityClass.POSTAL_ADDRESS,
        IdentityClass.TAX_IDENTIFIER,
    }

    prompt = (
        "Seller: ARDSHIN TRADING LLC, 14 Komitas Avenue, Yerevan, TIN 02845517. "
        "Buyer: NORTHWIND IMPORTS OJSC (77341902). Contact ops@ardshin-trading.am, "
        "+374 10 555 123. Goods: PORTLAND CEMENT CEM I 42.5 N, code 2523290000."
    )
    trace_recorder, sink = recorder(
        CapturePolicy(level=CaptureLevel.PAYLOADS, truncation_chars=None),
        identities=tuple(identities),
    )
    assert identity_leaks(prompt, identities), "the fixture must leak before it is masked"

    with trace_recorder.stage("classification"):
        with trace_recorder.node("C5 pick", entry_state={"invoice": record}) as draft:
            draft.decided("picked 2523290000 for ARDSHIN TRADING LLC's cement")
            draft.captured(prompt=prompt, response='{"code": "2523290000"}')

    assert identity_leaks(sink.records[0], identities) == ()
    payload = sink.records[0].payload
    assert payload is not None and payload.prompt is not None
    assert "[redacted:organization_name]" in payload.prompt
    assert "[redacted:contact]" in payload.prompt
    assert "2523290000" in payload.prompt, "a trace that masks commodity codes explains nothing"


def test_identities_learned_late_do_not_mask_what_was_already_written() -> None:
    """The limitation, stated as a test: nothing here rewrites a record.

    It also proves the leak check has teeth over a whole run trace, not only over one
    record — a prompt captured before `learn_identities` really does still carry the name.
    """
    identities = identities_in(invoice())
    policy = CapturePolicy(level=CaptureLevel.PAYLOADS, truncation_chars=None)

    trace_recorder, _ = recorder(policy)
    with trace_recorder.stage("description"):
        with trace_recorder.node("A17 write") as draft:
            draft.captured(prompt="Seller: ARDSHIN TRADING LLC")
    assert identity_leaks(trace_recorder.trace(), identities) == ("ARDSHIN TRADING LLC",)

    trace_recorder, _ = recorder(policy)
    trace_recorder.learn_identities(identities)
    with trace_recorder.stage("description"):
        with trace_recorder.node("A17 write") as draft:
            draft.captured(prompt="Seller: ARDSHIN TRADING LLC")
    assert identity_leaks(trace_recorder.trace(), identities) == ()


def test_the_field_mask_replaces_the_value_and_keeps_the_provenance() -> None:
    masked = Redactor().mask(Party(name=traced("ARDSHIN TRADING LLC")))
    assert masked["name"]["value"] == "[redacted:organization_name]"
    assert masked["name"]["provenance"]["source_document_id"] == "upload-1.pdf"


def test_the_pattern_backstop_catches_what_no_field_named() -> None:
    masked = Redactor().mask_text(
        "wire to AM04ATMB1234567890123456, ask finance@example.com or +374 10 555 123"
    )
    assert "AM04ATMB1234567890123456" not in masked
    assert "finance@example.com" not in masked
    assert "[redacted:bank_detail]" in masked
    assert "[redacted:contact]" in masked


def test_redaction_is_not_optional_at_any_level() -> None:
    """There is no policy, flag or argument that turns the mask off."""
    for level in CaptureLevel:
        policy = CapturePolicy(level=level)
        assert "redaction always on" in policy.statement()
    assert not any("redact" in field for field in CapturePolicy.model_fields)


# --- version pinning and attribution -----------------------------------------


def test_the_manifest_names_what_it_could_not_pin() -> None:
    thin = manifest(
        data=DataPins(
            nomenclature_vintage=UNPINNED,
            embedding_model="models/gemini-embedding-001",
            embedding_dimensions=768,
            canonical_text_structure_version=UNPINNED,
        ),
        code=CodePins(build_identifier=UNPINNED),
    )
    unpinned = thin.unpinned()
    assert "data.nomenclature_vintage" in unpinned
    assert "data.canonical_text_structure_version" in unpinned
    assert "data.index_build_id" in unpinned
    assert "code.build_identifier" in unpinned
    assert "prompts[pick_code].content_hash" in unpinned


def test_identical_manifests_compare_identical() -> None:
    assert compare_manifests(manifest(), manifest()).verdict is AttributionVerdict.IDENTICAL


def test_one_axis_apart_is_attributable() -> None:
    other = manifest(
        models=ModelPins(
            stages=(
                StageModel(
                    stage="classification",
                    tier="strong",
                    model_id="gemini-3.6-flash",
                    decoding=Decoding(max_output_tokens=8192),
                ),
            )
        )
    )
    comparison = compare_manifests(manifest(), other)
    assert comparison.verdict is AttributionVerdict.SINGLE_AXIS
    assert comparison.attributable_to == "models"


def test_a_data_change_and_a_model_change_together_are_a_compound_change() -> None:
    other = manifest(
        data=DataPins(
            nomenclature_vintage="2027-01-01T00:00:00+00:00",
            embedding_model="models/gemini-embedding-001",
            embedding_dimensions=768,
            canonical_text_structure_version="chapter-heading-leaf/1",
            index_build_id="qdrant_exim/14400",
            nomenclature_source="exim.src.am id-enumeration crawl",
            code_lists=(Pin(name="countries", value="2027-01-01"),),
        ),
        models=ModelPins(
            stages=(
                StageModel(
                    stage="classification",
                    tier="strong",
                    model_id="gemini-3.6-flash",
                    decoding=Decoding(max_output_tokens=8192),
                ),
            )
        ),
    )
    comparison = compare_manifests(manifest(), other)
    assert comparison.verdict is AttributionVerdict.COMPOUND
    assert comparison.attributable_to is None
    assert set(comparison.differing_axes) == {"data", "models"}


def test_the_run_identifier_is_not_an_axis() -> None:
    """Two runs of the same build must be able to compare as identical."""
    other = manifest(run_id="run-20260810T000000Z-cafebabe")
    assert compare_manifests(manifest(), other).verdict is AttributionVerdict.IDENTICAL


def test_pin_drift_names_a_model_that_answered_but_was_not_pinned() -> None:
    trace_recorder, _ = recorder()
    with trace_recorder.stage("description"):
        with trace_recorder.node("A17 write", line_id="1") as draft:
            draft.model_call(call(prompt_name="write_description", tier=ModelTier.STANDARD))
    drift = trace_recorder.trace().pin_drift()
    assert any("description" in item for item in drift)
    assert any("write_description" in item for item in drift)


def test_observed_models_and_prompts_are_read_off_the_calls() -> None:
    trace_recorder, _ = recorder()
    with trace_recorder.stage("classification"):
        with trace_recorder.node("C5 pick") as draft:
            draft.model_call(call())
        with trace_recorder.node("C5 pick") as draft:
            draft.model_call(call())
    trace = trace_recorder.trace()
    assert [model.model_id for model in trace.observed_models()] == ["gemini-2.5-pro"]
    assert [prompt.name for prompt in trace.observed_prompts()] == ["pick_code"]


# --- retrieval capture --------------------------------------------------------


def test_the_full_candidate_list_is_kept_with_the_rank_of_the_correct_answer() -> None:
    retrieval = Retrieval.from_candidates(
        query="cement — portland cement",
        candidates=candidates(),
        scope="p4=2523",
        chosen_code="2523290000",
        known_correct_code="2523100000",
        dropped_unknown_codes=2,
    )
    assert [alternative.rank for alternative in retrieval.alternatives] == [1, 2, 3]
    assert retrieval.alternatives[0].chosen is True
    assert retrieval.correct_rank == 3
    assert retrieval.dropped_unknown_codes == 2


def test_a_correct_answer_that_was_never_retrieved_has_no_rank() -> None:
    retrieval = Retrieval.from_candidates(
        query="cement", candidates=candidates(), known_correct_code="6810910000"
    )
    assert retrieval.known_correct_code == "6810910000"
    assert retrieval.correct_rank is None


# --- append-only sinks and retention -----------------------------------------


def test_the_sink_appends_and_never_truncates(tmp_path) -> None:
    path = tmp_path / "trace.jsonl"
    for decision in ("first run", "second run"):
        sink = JsonlTraceSink(path)
        trace_recorder = TraceRecorder(
            run_id=RUN_ID,
            case_id=CASE_ID,
            manifest=manifest(),
            capture=CapturePolicy(),
            retention=RetentionPolicy(declared_by="test"),
            sink=sink,
        )
        with trace_recorder.stage("run"):
            with trace_recorder.node("chain") as draft:
                draft.decided(decision)
        sink.close()
    records = read_trace_file(path)
    assert [record.decision for record in records] == ["first run", "second run"]


def test_nothing_in_the_package_deletes_a_trace_or_an_artifact() -> None:
    import deepclare.trace as package

    forbidden = ("delete", "prune", "expire", "purge", "rotate", "truncate_file")
    exported = {name.lower() for name in package.__all__}
    assert not any(word in name for name in exported for word in forbidden)
    assert not hasattr(ArtifactStore, "delete")


def test_an_artifact_store_refuses_to_overwrite(tmp_path) -> None:
    store = ArtifactStore(
        root=tmp_path, manifest=manifest(), retention=RetentionPolicy(declared_by="test")
    )
    reference = store.retain_text(ArtifactKind.EMITTED_DOCUMENT, "declaration.xml", "<x/>")
    assert reference.manifest_fingerprint == manifest().fingerprint()
    assert (tmp_path / RUN_ID / "manifest.json").exists()
    with pytest.raises(TraceError, match="deletion under another name"):
        store.retain_text(ArtifactKind.EMITTED_DOCUMENT, "declaration.xml", "<y/>")


def test_the_retention_policy_enforces_nothing() -> None:
    policy = RetentionPolicy(declared_by="the operator", window_days=90)
    assert "explicit human action only" in policy.statement()
    assert not hasattr(policy, "expired")
