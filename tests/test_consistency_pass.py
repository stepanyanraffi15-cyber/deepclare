"""The reconciliation pass: what it changes, what it refuses, and how it degrades.

Every test here runs against a queued fake model and a dictionary-backed reference store,
so the whole file runs with no network, no provider key and no reference artifact. That is
what makes it worth running on every change: the degradation contract — *this module is
never the reason a run fails* — is a claim about failure paths, and a test that needs a
provider to reach them would never be run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deepclare.classification import ExistenceGate
from deepclare.consistency import (
    ConsistencyError,
    DraftedLine,
    PassOutcome,
    Reconciler,
)
from deepclare.consistency.records import ConsistencyField
from deepclare.consistency.schemas import (
    ConformedLine,
    ConformLines,
    CritiqueIssue,
    CritiqueLines,
)
from deepclare.models import ModelTransportError
from tests.classification_fakes import FakeModel, FakeStore, entry

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

PIPE = "ՊՈԼԻՎԻՆԻԼՔԼՈՐԻԴԻ ԽՈՂՈՎԱԿ, ՆԱԽԱՏԵՍՎԱԾ Է ՋՐԱՄԱՏԱԿԱՐԱՐՄԱՆ ՀԱՄԱՐ"
LOOSE = "ԽՈՂՈՎԱԿ ՊԼԱՍՏՄԱՍՍԵ"

STORE = FakeStore(
    entries=[
        entry("3917231009", "rigid tubes of polymers of vinyl chloride", "-"),
        entry("3917320009", "other tubes, not reinforced", "-"),
        entry("3917400009", "fittings", "-"),
    ]
)


def drafted(
    line_id: str,
    *,
    source_name: str,
    description: str,
    segments: tuple[str, ...] = (),
    code: str | None = "3917231009",
    unit: str | None = None,
) -> DraftedLine:
    return DraftedLine(
        line_id=line_id,
        source_name=source_name,
        description=description,
        deterministic_segments=segments,
        code=code,
        supplementary_unit=unit,
    )


def family() -> list[DraftedLine]:
    """Three pipes of one family. Line 3 is worded unlike the other two and carries a
    different code."""
    return [
        drafted("1", source_name="PVC PIPE 32MM", description=f"{PIPE}, 32 ՄՄ"),
        drafted("2", source_name="PVC PIPE 40MM", description=f"{PIPE}, 40 ՄՄ"),
        drafted(
            "3",
            source_name="PVC PIPE 50MM",
            description=f"{LOOSE}, 50 ՄՄ",
            code="3917320009",
        ),
    ]


def critique(*issues: CritiqueIssue, notes: tuple[str, ...] = ()) -> CritiqueLines:
    return CritiqueLines(issues=list(issues), shipment_notes=list(notes))


def issue(
    line_id: str = "3",
    field: str = "description",
    problem: str = "Line 3 reads unlike lines 1 and 2 of the same pipe family.",
    suggested: str = "",
) -> CritiqueIssue:
    return CritiqueIssue(
        line_id=line_id, field=field, problem=problem, suggested_value=suggested
    )


def conformed(*rows: tuple[str, str, str]) -> ConformLines:
    return ConformLines(
        lines=[
            ConformedLine(line_id=line_id, description=text, code=code)
            for line_id, text, code in rows
        ]
    )


def reconciler(model: FakeModel) -> Reconciler:
    return Reconciler(
        existence_gate=ExistenceGate(STORE), model=model, prompts_dir=PROMPTS
    )


def unchanged(outcome, lines: list[DraftedLine]) -> bool:
    return [
        (line.line_id, line.description, line.code, line.supplementary_unit)
        for line in outcome.lines
    ] == [
        (line.line_id, line.description, line.code, line.supplementary_unit)
        for line in lines
    ]


class FailingModel:
    """A provider that is not there. The one failure mode every stage must survive."""

    def __init__(self, fail_on: int) -> None:
        self._calls = 0
        self._fail_on = fail_on
        self.answers = FakeModel([])

    def queue(self, *answers) -> None:
        self.answers = FakeModel(list(answers))

    def generate(self, **kwargs):
        self._calls += 1
        if self._calls == self._fail_on:
            raise ModelTransportError("the provider could not be reached")
        return self.answers.generate(**kwargs)


# --- nothing to do -----------------------------------------------------------


def test_one_line_is_consistent_with_itself_and_costs_no_call() -> None:
    lines = family()[:1]
    model = FakeModel([])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.outcome is PassOutcome.NOT_ATTEMPTED
    assert outcome.calls == ()
    assert unchanged(outcome, lines)


def test_a_clean_draft_costs_one_call_and_no_rewrite() -> None:
    lines = family()
    model = FakeModel([critique()])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.outcome is PassOutcome.NOTHING_TO_DO
    assert model.remaining == 0
    assert len(outcome.calls) == 1
    assert unchanged(outcome, lines)


def test_a_repeated_line_id_is_a_caller_defect_and_raises() -> None:
    lines = family() + [family()[0]]
    with pytest.raises(ConsistencyError, match="more than once"):
        reconciler(FakeModel([])).reconcile(lines)


# --- degradation -------------------------------------------------------------


def test_a_failed_critique_abandons_the_whole_pass() -> None:
    lines = family()
    model = FailingModel(fail_on=1)
    outcome = reconciler(model).reconcile(lines)

    assert outcome.outcome is PassOutcome.CRITIQUE_FAILED
    assert outcome.review_items == ()
    assert outcome.changes == ()
    assert unchanged(outcome, lines)


def test_a_failed_rewrite_keeps_the_flags_and_changes_nothing() -> None:
    lines = family()
    model = FailingModel(fail_on=2)
    model.queue(critique(issue()))
    outcome = reconciler(model).reconcile(lines)

    assert outcome.outcome is PassOutcome.REWRITE_FAILED
    assert [item.line_id for item in outcome.review_items] == ["3"]
    assert unchanged(outcome, lines)


def test_a_rewrite_that_omits_a_line_is_discarded_whole() -> None:
    lines = family()
    model = FakeModel([
        critique(issue()),
        conformed(("1", f"{PIPE}, 32 ՄՄ", ""), ("3", f"{PIPE}, 50 ՄՄ", "")),
    ])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.outcome is PassOutcome.REWRITE_DISCARDED
    assert "line(s) 2" in outcome.detail
    assert outcome.review_items  # the critique's flags survive
    assert unchanged(outcome, lines)


def test_a_rewrite_that_answers_twice_for_one_line_is_discarded_whole() -> None:
    lines = family()
    model = FakeModel([
        critique(issue()),
        conformed(
            ("1", f"{PIPE}, 32 ՄՄ", ""),
            ("2", f"{PIPE}, 40 ՄՄ", ""),
            ("3", f"{PIPE}, 50 ՄՄ", ""),
            ("3", f"{LOOSE}, 50 ՄՄ", ""),
        ),
    ])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.outcome is PassOutcome.REWRITE_DISCARDED
    assert unchanged(outcome, lines)


def test_a_rewrite_that_answers_for_goods_not_in_this_shipment_is_discarded_whole() -> None:
    lines = family()
    model = FakeModel([
        critique(issue()),
        conformed(
            ("1", f"{PIPE}, 32 ՄՄ", ""),
            ("2", f"{PIPE}, 40 ՄՄ", ""),
            ("3", f"{PIPE}, 50 ՄՄ", ""),
            ("9", f"{PIPE}, 90 ՄՄ", ""),
        ),
    ])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.outcome is PassOutcome.REWRITE_DISCARDED
    assert unchanged(outcome, lines)


# --- what it does when it works ----------------------------------------------


def test_a_line_is_conformed_to_its_siblings_and_flagged() -> None:
    lines = family()
    model = FakeModel([
        critique(issue()),
        conformed(
            ("1", f"{PIPE}, 32 ՄՄ", ""),
            ("2", f"{PIPE}, 40 ՄՄ", ""),
            ("3", f"{PIPE}, 50 ՄՄ", ""),
        ),
    ])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.outcome is PassOutcome.APPLIED
    assert outcome.changed_line_ids == ("3",)
    assert outcome.lines[2].description == f"{PIPE}, 50 ՄՄ"
    assert outcome.lines[2].changed_fields == (ConsistencyField.DESCRIPTION,)

    change = outcome.changes[0]
    assert change.transform.operation == "conform-description"
    assert change.transform.before == f"{LOOSE}, 50 ՄՄ"
    assert change.transform.reason.startswith("Line 3 reads unlike")

    item = next(one for one in outcome.review_items if one.line_id == "3")
    assert item.concept == "goods description"
    assert "Changed by cross-line review" in item.detail


def test_an_aligned_code_re_enters_the_existence_gate_and_drops_its_tariff_unit() -> None:
    lines = [
        drafted("1", source_name="PVC PIPE 32MM", description=f"{PIPE}, 32 ՄՄ"),
        drafted(
            "2",
            source_name="PVC PIPE 40MM",
            description=f"{PIPE}, 40 ՄՄ",
            code="3917320009",
            unit="ՄԵՏՐ",
        ),
    ]
    model = FakeModel([
        critique(issue(line_id="2", field="code", problem="Line 2 is the same pipe as "
                                                          "line 1 but carries a different code.")),
        conformed(
            ("1", f"{PIPE}, 32 ՄՄ", ""),
            ("2", f"{PIPE}, 40 ՄՄ", "3917231009"),
        ),
    ])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.lines[1].code == "3917231009"
    assert outcome.lines[1].supplementary_unit is None
    assert set(outcome.lines[1].changed_fields) == {
        ConsistencyField.CODE,
        ConsistencyField.SUPPLEMENTARY_UNIT,
    }
    concepts = {item.concept for item in outcome.review_items}
    assert concepts == {"commodity code", "supplementary quantity unit"}


def test_a_filed_eleven_digit_code_is_reduced_by_the_gate() -> None:
    lines = [
        drafted("1", source_name="PVC PIPE 32MM", description=f"{PIPE}, 32 ՄՄ"),
        drafted("2", source_name="PVC PIPE 40MM", description=f"{PIPE}, 40 ՄՄ",
                code="3917320009"),
    ]
    model = FakeModel([
        critique(issue(line_id="2", field="code")),
        conformed(("1", f"{PIPE}, 32 ՄՄ", ""), ("2", f"{PIPE}, 40 ՄՄ", "39172310090")),
    ])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.lines[1].code == "3917231009"


# --- what it refuses ---------------------------------------------------------


def test_an_empty_code_is_a_no_op_and_never_blanks_one() -> None:
    lines = family()
    model = FakeModel([
        critique(issue()),
        conformed(
            ("1", f"{PIPE}, 32 ՄՄ", ""),
            ("2", f"{PIPE}, 40 ՄՄ", ""),
            ("3", f"{PIPE}, 50 ՄՄ", ""),
        ),
    ])
    outcome = reconciler(model).reconcile(lines)

    assert [line.code for line in outcome.lines] == [
        "3917231009",
        "3917231009",
        "3917320009",
    ]


def test_a_code_that_is_not_in_the_nomenclature_is_refused_and_the_draft_stands() -> None:
    lines = family()
    model = FakeModel([
        critique(issue(line_id="3", field="code")),
        conformed(
            ("1", f"{PIPE}, 32 ՄՄ", ""),
            ("2", f"{PIPE}, 40 ՄՄ", ""),
            ("3", f"{LOOSE}, 50 ՄՄ", "9999999999"),
        ),
    ])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.lines[2].code == "3917320009"
    assert outcome.rejected[0].field is ConsistencyField.CODE
    assert "no entry of the current nomenclature" in outcome.rejected[0].reason


def test_an_abstention_is_never_filled_in_from_a_sibling() -> None:
    lines = [
        drafted("1", source_name="PVC PIPE 32MM", description=f"{PIPE}, 32 ՄՄ"),
        drafted("2", source_name="PVC PIPE 40MM", description=f"{PIPE}, 40 ՄՄ", code=None),
    ]
    model = FakeModel([
        critique(issue(line_id="2", field="code", problem="Line 2 has no code while the "
                                                          "identical line 1 does.")),
        conformed(("1", f"{PIPE}, 32 ՄՄ", ""), ("2", f"{PIPE}, 40 ՄՄ", "3917231009")),
    ])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.lines[1].code is None
    assert "abstained" in outcome.rejected[0].reason
    flagged = next(one for one in outcome.review_items if one.line_id == "2")
    assert flagged.concept == "commodity code"
    assert "Nothing was changed" in flagged.detail


def test_a_rewrite_that_drops_a_computed_segment_is_refused_per_line() -> None:
    lines = [
        drafted("1", source_name="PVC PIPE 32MM", description=f"{PIPE}, 32 ՄՄ, 500 ՄԵՏՐ",
                segments=("500 ՄԵՏՐ",)),
        drafted("2", source_name="PVC PIPE 40MM", description=f"{LOOSE}, 40 ՄՄ, 300 ՄԵՏՐ",
                segments=("300 ՄԵՏՐ",)),
    ]
    model = FakeModel([
        critique(issue(line_id="2")),
        conformed(
            ("1", f"{PIPE}, 32 ՄՄ, 500 ՄԵՏՐ", ""),
            ("2", f"{PIPE}, 40 ՄՄ", ""),
        ),
    ])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.lines[1].description == f"{LOOSE}, 40 ՄՄ, 300 ՄԵՏՐ"
    assert outcome.changes == ()
    assert "verbatim" in outcome.rejected[0].reason


def test_a_rewrite_that_would_merge_two_lines_is_refused() -> None:
    lines = [
        drafted("1", source_name="PVC PIPE 32MM", description=f"{PIPE}, 32 ՄՄ"),
        drafted("2", source_name="PVC PIPE 32MM WHITE", description=f"{LOOSE}, 32 ՄՄ"),
    ]
    model = FakeModel([
        critique(issue(line_id="2")),
        conformed(("1", f"{PIPE}, 32 ՄՄ", ""), ("2", f"{PIPE}, 32 ՄՄ", "")),
    ])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.lines[1].description == f"{LOOSE}, 32 ՄՄ"
    assert "cannot tell apart" in outcome.rejected[0].reason


# --- what reaches the model, and what comes back from it ---------------------


def test_the_critic_is_shown_the_segments_it_must_not_touch() -> None:
    lines = [
        drafted("1", source_name="PVC PIPE 32MM", description=f"{PIPE}, 32 ՄՄ, 500 ՄԵՏՐ",
                segments=("500 ՄԵՏՐ",)),
        drafted("2", source_name="PVC PIPE 40MM", description=f"{PIPE}, 40 ՄՄ"),
    ]
    model = FakeModel([critique()])
    reconciler(model).reconcile(lines)

    sent = model.prompts[0].text
    assert "must appear verbatim: 500 ՄԵՏՐ" in sent
    assert "PVC PIPE 32MM" in sent


def test_an_issue_against_goods_that_are_not_in_this_shipment_is_dropped() -> None:
    lines = family()
    model = FakeModel([critique(issue(line_id="9"))])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.outcome is PassOutcome.NOTHING_TO_DO
    assert outcome.review_items == ()


def test_a_shipment_level_note_becomes_a_shipment_level_review_item() -> None:
    lines = family()
    model = FakeModel([critique(notes=("Three lines of one family, three codes.",))])
    outcome = reconciler(model).reconcile(lines)

    assert outcome.shipment_notes == ("Three lines of one family, three codes.",)
    assert [item.line_id for item in outcome.review_items] == [None]
    assert outcome.review_items[0].concept == "cross-line consistency"


def test_every_review_item_is_keyed_by_a_domain_concept() -> None:
    """Never by an element name. A concept with an internal case boundary or a path
    separator is the filing contract leaking upward."""
    lines = family()
    model = FakeModel([
        critique(issue(), issue(line_id="3", field="code"), notes=("a note",)),
        conformed(
            ("1", f"{PIPE}, 32 ՄՄ", ""),
            ("2", f"{PIPE}, 40 ՄՄ", ""),
            ("3", f"{PIPE}, 50 ՄՄ", ""),
        ),
    ])
    outcome = reconciler(model).reconcile(lines)

    for item in outcome.review_items:
        assert " " in item.concept
        assert "/" not in item.concept
