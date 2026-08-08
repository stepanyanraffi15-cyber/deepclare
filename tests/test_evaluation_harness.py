"""The harness measures things, and it measures the right things.

The self-scoring test is the load-bearing one: a case's own ground truth scored against
itself must be perfect on every metric, and anything less is a defect in the harness
rather than a finding about the product. The tests around it are the other half of the
same statement — a harness that always returns 1.0 would pass the first test and be
worthless, so each of these degrades one thing about the produced declaration and asserts
that exactly the corresponding number moves.

No network, no model, no settings: the manifest is constructed here with explicit values
rather than read from an environment a test has no business depending on.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deepclare.evaluation.cases import CaseInputs, discover_cases, select
from deepclare.evaluation.harness import score_corpus
from deepclare.evaluation.manifest import Production, RunManifest
from deepclare.evaluation.producers import ProductionFailed, emitted_file
from deepclare.evaluation.scorer import bind_scorer, scorer_root
from deepclare.prompting import prompt_identities

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "evalkit" / "corpus"

CASE_WITH_14_LINES = "oneToOne/case-001"
CASE_WITH_5_UNRESOLVABLE_OF_6 = "oneToOne/case-031"

CODE_ELEMENT = re.compile(r"(<\w+:GoodsTNVEDCode>)(\d+)(</\w+:GoodsTNVEDCode>)")
NET_WEIGHT_ELEMENT = re.compile(r"(<\w+:NetWeightQuantity>)([\d.]+)(</\w+:NetWeightQuantity>)")
GOODS_BLOCK = re.compile(r"[ \t]*<(\w+):ESADout_CUGoods>.*?</\1:ESADout_CUGoods>\n", re.DOTALL)


@pytest.fixture(scope="module")
def scorer():
    return bind_scorer(scorer_root(CORPUS))


@pytest.fixture(scope="module")
def corpus_cases() -> list[CaseInputs]:
    return discover_cases(CORPUS)


def case_named(cases: list[CaseInputs], name: str) -> CaseInputs:
    return next(case for case in cases if case.name == name)


def a_manifest() -> RunManifest:
    return RunManifest(
        scored_at=datetime(2026, 1, 1, tzinfo=UTC),
        code_build="testing",
        production=Production.PRE_EMITTED,
        producer="a test",
        corpus_dir=str(CORPUS),
        scorer_dir=str(CORPUS.parent),
        model_ids={"cheap": "c", "standard": "s", "strong": "S"},
        decoding={"temperature": 0.0, "seed": 1},
        prompts=(),
        nomenclature_vintage="2026-06-15",
        nomenclature_dir="nowhere",
        embedding_model="an-embedder",
        embedding_dimensions=768,
        retrieval_depth=30,
        classification_features={"candidate_limit": 30},
        scoring_thresholds={"chrf_min": 0.6},
    )


def run(cases: list[CaseInputs], produce, scorer):
    return score_corpus(
        selection=select(cases, None),
        produce=produce,
        scorer=scorer,
        manifest=a_manifest(),
    )


def truth_of(case: CaseInputs) -> str:
    return case.ground_truth_xml.read_text(encoding="utf-8")


# --- the self-check ---------------------------------------------------------


def test_ground_truth_scored_against_itself_is_perfect(corpus_cases, scorer):
    ten = select(corpus_cases, 10).cases
    report = score_corpus(
        selection=select(list(ten), None),
        produce=emitted_file("ground_truth.xml"),
        scorer=scorer,
        manifest=a_manifest(),
    )

    assert report.complete
    totals = report.aggregates
    assert totals.cases_scored == 10
    assert totals.cases_passed == 10
    assert totals.alignment.invented == 0
    assert totals.alignment.missed == 0
    assert totals.alignment.precision == 1.0
    assert totals.alignment.recall == 1.0
    assert totals.alignment.f1 == 1.0
    assert totals.lines_passed == totals.alignment.matched

    codes = totals.code_all_labels
    assert codes.exact == codes.lines
    assert codes.abstained == 0
    for level in (2, 4, 6, 8, 10):
        assert codes.agreement_at[level] == 1.0

    for field, exact in totals.numeric.exact.items():
        assert exact == totals.numeric.lines, field
    assert totals.description.mean_chrf == 1.0
    assert totals.description.exact == totals.description.lines


# --- each degradation moves exactly its own number --------------------------


def test_blanking_one_code_costs_coverage_and_agreement(corpus_cases, scorer):
    case = case_named(corpus_cases, CASE_WITH_14_LINES)

    def produce(_: CaseInputs) -> str:
        return CODE_ELEMENT.sub(r"\1\3", truth_of(case), count=1)

    report = run([case], produce, scorer)
    codes = report.aggregates.code_all_labels

    assert codes.lines == 14
    assert codes.abstained == 1
    assert codes.emitted == 13
    assert codes.exact == 13
    assert codes.coverage == pytest.approx(13 / 14)
    assert codes.accuracy == pytest.approx(13 / 14)
    assert codes.precision == 1.0, "the answered lines were all right; only coverage fell"
    for level in (2, 4, 6, 8, 10):
        assert codes.agreement_at[level] == pytest.approx(13 / 14)
    assert report.aggregates.alignment.f1 == 1.0, "the line is still produced, just uncoded"


def test_a_wrong_code_agrees_down_to_where_it_diverges(corpus_cases, scorer):
    case = case_named(corpus_cases, CASE_WITH_14_LINES)

    def produce(_: CaseInputs) -> str:
        # Same chapter, same heading, different sixth digit onward.
        return CODE_ELEMENT.sub(
            lambda m: f"{m.group(1)}{m.group(2)[:5]}99999{m.group(2)[10]}{m.group(3)}",
            truth_of(case),
            count=1,
        )

    codes = run([case], produce, scorer).aggregates.code_all_labels
    assert codes.exact == 13
    assert codes.agreement_at[2] == 1.0
    assert codes.agreement_at[4] == 1.0
    assert codes.agreement_at[6] == pytest.approx(13 / 14)
    assert codes.agreement_at[10] == pytest.approx(13 / 14)


def test_dropping_a_line_costs_recall_and_not_precision(corpus_cases, scorer):
    case = case_named(corpus_cases, CASE_WITH_14_LINES)

    def produce(_: CaseInputs) -> str:
        return GOODS_BLOCK.sub("", truth_of(case), count=1)

    alignment = run([case], produce, scorer).aggregates.alignment
    assert alignment.matched == 13
    assert alignment.missed == 1
    assert alignment.invented == 0
    assert alignment.precision == 1.0
    assert alignment.recall == pytest.approx(13 / 14)


def test_a_wrong_weight_is_caught_on_that_field_alone(corpus_cases, scorer):
    case = case_named(corpus_cases, CASE_WITH_14_LINES)

    def produce(_: CaseInputs) -> str:
        return NET_WEIGHT_ELEMENT.sub(
            lambda m: f"{m.group(1)}{float(m.group(2)) + 5}{m.group(3)}",
            truth_of(case),
            count=1,
        )

    numeric = run([case], produce, scorer).aggregates.numeric
    assert numeric.exact["net_weight"] == 13
    assert numeric.exact["gross_weight"] == 14
    assert numeric.exact["quantity"] == 14


# --- the labels that name a code which does not exist -----------------------


def test_abstaining_on_an_impossible_label_leaves_the_attributable_number_clean(
    corpus_cases, scorer
):
    case = case_named(corpus_cases, CASE_WITH_5_UNRESOLVABLE_OF_6)

    def produce(_: CaseInputs) -> str:
        return CODE_ELEMENT.sub(
            lambda m: f"{m.group(1)}{m.group(3)}"
            if m.group(2) in {"39069090090", "39100000090"}
            else m.group(0),
            truth_of(case),
        )

    totals = run([case], produce, scorer).aggregates

    assert totals.unresolvable.matched_lines == 5
    assert totals.unresolvable.abstained == 5
    assert totals.unresolvable.answered_anyway == 0

    assert totals.code_attributable.lines == 1
    assert totals.code_attributable.exact == 1
    assert totals.code_attributable.accuracy == 1.0, (
        "correct behaviour on an impossible label must not depress the number"
    )

    assert totals.code_all_labels.lines == 6
    assert totals.code_all_labels.accuracy == pytest.approx(1 / 6)


def test_answering_an_impossible_label_is_counted_as_answering(corpus_cases, scorer):
    case = case_named(corpus_cases, CASE_WITH_5_UNRESOLVABLE_OF_6)
    report = run([case], emitted_file("ground_truth.xml"), scorer)

    assert report.aggregates.unresolvable.matched_lines == 5
    assert report.aggregates.unresolvable.abstained == 0
    assert report.aggregates.unresolvable.answered_anyway == 5


# --- a case that produces nothing is reported, never dropped ----------------


def test_a_failed_case_is_named_and_the_run_is_not_complete(corpus_cases, scorer):
    good = case_named(corpus_cases, CASE_WITH_14_LINES)
    missing = case_named(corpus_cases, "oneToOne/case-002")

    report = run([good, missing], emitted_file("declaration.xml"), scorer)

    assert not report.complete
    assert report.aggregates.cases_scored == 0
    assert {failure.name for failure in report.failures} == {good.name, missing.name}
    assert all(failure.error_type == "ProductionFailed" for failure in report.failures)


def test_a_producer_failure_does_not_lose_the_cases_that_worked(corpus_cases, scorer):
    good = case_named(corpus_cases, CASE_WITH_14_LINES)
    bad = case_named(corpus_cases, "oneToOne/case-003")
    truth = emitted_file("ground_truth.xml")

    def produce(case: CaseInputs) -> str:
        if case.name == bad.name:
            raise ProductionFailed("the pipeline gave up on this one")
        return truth(case)

    report = run([good, bad], produce, scorer)

    assert report.aggregates.cases_scored == 1
    assert report.aggregates.cases_passed == 1
    assert len(report.failures) == 1
    assert not report.complete


# --- selection and pinning --------------------------------------------------


def test_selection_is_a_reproducible_prefix_that_says_it_is_biased(corpus_cases):
    selection = select(corpus_cases, 4)
    assert len(selection.cases) == 4
    assert selection.available == len(corpus_cases)
    assert [case.name for case in selection.cases] == [
        case.name for case in corpus_cases[:4]
    ]
    assert "biased" in selection.rule

    everything = select(corpus_cases, None)
    assert len(everything.cases) == len(corpus_cases)


def test_a_case_carries_the_input_documents_a_producer_would_read(corpus_cases):
    case = case_named(corpus_cases, CASE_WITH_14_LINES)
    assert case.invoice_pdf is not None and case.invoice_pdf.exists()
    assert case.invoice_workbook is not None and case.invoice_workbook.exists()
    assert case.consignment_note_pdf is not None and case.consignment_note_pdf.exists()
    atoms = case.atoms()
    assert atoms is not None and len(atoms) == 14


def test_prompt_identities_pin_both_the_declared_version_and_the_bytes():
    identities = prompt_identities(REPO / "prompts")
    assert identities, "the prompt directory has prompts in it"
    names = [identity.name for identity in identities]
    assert names == sorted(names)
    assert "README" not in names
    for identity in identities:
        assert identity.version
        assert len(identity.content_sha256) == 64
