"""The two layers around the graph: the existence gate and the vendor catalogue.

No network. The gate and the catalogue layer are pure functions of a store lookup, which
is what makes it reasonable to run the gate on every code that leaves the module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deepclare.classification import (
    CATALOGUE_CONFIDENCE,
    Classifier,
    ExistenceGate,
    LineClassification,
    VendorCatalogueLayer,
)
from deepclare.classification.records import CODE_ASSIGNMENT_LAYER, VENDOR_CATALOGUE_LAYER
from deepclare.classification.schemas import PickCode, PickHeading, ShortlistChapters
from deepclare.domain import Confidence, Provenance, Traced, ValueOrigin
from tests.classification_fakes import FakeModel, FakeStore, candidate, entry, line

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

GENERATED = Provenance(
    origin=ValueOrigin.GENERATED,
    stage="classification",
    prompt_name="pick_code",
    prompt_version="1",
)


def store() -> FakeStore:
    return FakeStore(
        entries=[
            entry("39", "PLASTICS AND ARTICLES THEREOF"),
            entry("3923210000", "sacks and bags of polymers of ethylene", unit="шт"),
            entry("3926909000", "other articles of plastics"),
        ],
        headings={"3923": "Articles for the conveyance or packing of goods:"},
        search=lambda _q, _p, _l: [candidate("3923210000", 0.83)],
    )


def classified(code: str | None, **overrides) -> LineClassification:
    traced = (
        None
        if code is None
        else Traced[str](
            value=code, provenance=GENERATED, confidence=Confidence(derivation=0.82)
        )
    )
    fields = {
        "line_id": "1",
        "code": traced,
        "needs_review": False,
        "rationale": "the polymer is stated and the article is a sack",
        "supplementary_unit": "шт",
        "candidates": (candidate("3923210000", 0.83),),
        "decided_by": CODE_ASSIGNMENT_LAYER,
    }
    return LineClassification(**{**fields, **overrides})


class TestExistenceGate:
    def test_a_code_of_the_current_tree_passes_untouched(self):
        subject = classified("3923210000")
        assert ExistenceGate(store()).check(subject) == subject

    def test_an_abstention_passes_untouched(self):
        subject = classified(None, rationale="no candidate fits", needs_review=True)
        assert ExistenceGate(store()).check(subject) == subject

    @pytest.mark.parametrize(
        ("code", "because"),
        [
            ("00000000000", "run of zeros"),
            ("3923", "digits long"),
            ("392321000000", "digits long"),
            ("9999999999", "no entry of the current nomenclature"),
        ],
    )
    def test_a_code_this_tree_does_not_have_is_stripped_with_its_reason(self, code, because):
        result = ExistenceGate(store()).check(classified(code))
        assert result.abstained
        assert because in result.rationale
        assert code in result.rationale

    def test_stripping_clears_the_confidence_and_the_supplementary_unit(self):
        result = ExistenceGate(store()).check(classified("9999999999"))
        assert result.confidence == 0.0
        assert result.supplementary_unit is None
        assert result.needs_review

    def test_stripping_takes_only_the_code_and_keeps_the_rest(self):
        subject = classified(
            "9999999999", material_decisive=True, material_assumed="steel"
        )
        result = ExistenceGate(store()).check(subject)
        assert result.candidates == subject.candidates
        assert result.material_decisive
        assert result.material_assumed == "steel"
        assert result.steps == subject.steps

    def test_the_rewritten_rationale_keeps_what_it_replaced(self):
        result = ExistenceGate(store()).check(classified("9999999999"))
        assert "the polymer is stated and the article is a sack" in result.rationale

    def test_the_filed_eleven_digit_form_is_accepted_and_reduced_to_its_leaf(self):
        result = ExistenceGate(store()).check(classified("39232100000"))
        assert result.code.value == "3923210000"
        assert result.code.provenance.transforms[-1].before == "39232100000"
        assert not result.needs_review

    def test_a_non_zero_national_digit_is_reduced_but_flagged_because_zero_is_appended(self):
        result = ExistenceGate(store()).check(classified("39232100001"))
        assert result.code.value == "3923210000"
        assert result.needs_review
        assert "39232100001" in result.rationale
        assert "not the code supplied" in result.rationale


class TestVendorCatalogueLayer:
    def test_a_ten_digit_catalogue_code_of_this_tree_short_circuits(self):
        result = VendorCatalogueLayer(store()).decide(
            line(catalogue_code="3923210000")
        )
        assert result is not None
        assert result.code.value == "3923210000"
        assert result.confidence == CATALOGUE_CONFIDENCE
        assert result.supplementary_unit == "шт"
        assert result.decided_by == VENDOR_CATALOGUE_LAYER

    def test_it_is_always_flagged_for_review_even_at_its_own_confidence(self):
        result = VendorCatalogueLayer(store()).decide(line(catalogue_code="3923210000"))
        assert result.needs_review
        assert CATALOGUE_CONFIDENCE >= 0.7  # the gate alone would not have flagged it

    def test_an_eleven_digit_catalogue_code_is_reduced_and_records_the_reduction(self):
        result = VendorCatalogueLayer(store()).decide(line(catalogue_code="39232100000"))
        assert result.code.value == "3923210000"
        assert result.code.provenance.transforms[-1].before == "39232100000"

    @pytest.mark.parametrize("printed", ["392321", "39232100", "9999999999", "abcdefghij"])
    def test_anything_else_delegates_the_line_inward(self, printed):
        assert VendorCatalogueLayer(store()).decide(line(catalogue_code=printed)) is None

    def test_a_line_with_no_catalogue_code_delegates_inward(self):
        assert VendorCatalogueLayer(store()).decide(line()) is None

    def test_no_model_is_called_and_no_candidates_are_produced(self):
        result = VendorCatalogueLayer(store()).decide(line(catalogue_code="3923210000"))
        assert result.calls == ()
        assert result.candidates == ()


class TestTheStack:
    def test_the_catalogue_layer_decides_before_the_graph_runs(self):
        model = FakeModel([])
        subject = Classifier(store=store(), model=model, prompts_dir=PROMPTS)
        result = subject.classify(line(catalogue_code="3923210000"))
        assert result.decided_by == VENDOR_CATALOGUE_LAYER
        assert result.calls == ()

    def test_a_catalogue_code_this_tree_does_not_have_falls_through_to_the_graph(self):
        chose = PickCode(
            identification="a bag",
            material_decisive=False,
            material_assumed="",
            abstain=False,
            chosen_code="3923210000",
            llm_confidence=0.9,
            rationale="it is a sack of polyethylene",
            missing_evidence="",
            legal_basis="",
        )
        model = FakeModel(
            [
                ShortlistChapters(identity="a bag", chapters=["39"], reasoning="plastic"),
                PickHeading(headings=["3923"], search_text="a — b — c", reasoning="x"),
                chose,
            ]
        )
        subject = Classifier(store=store(), model=model, prompts_dir=PROMPTS)
        result = subject.classify(line(catalogue_code="9999999999"))
        assert result.decided_by == CODE_ASSIGNMENT_LAYER
        assert result.code.value == "3923210000"

    def test_the_gate_runs_on_the_return_from_the_catalogue_layer_too(self):
        # A tree the catalogue layer accepted from and the gate no longer knows: the
        # layers are independent, and the gate is the one that is unconditional.
        accepting = store()
        rejecting = FakeStore(entries=[entry("39", "PLASTICS")])
        decided = VendorCatalogueLayer(accepting).decide(line(catalogue_code="3923210000"))
        result = ExistenceGate(rejecting).check(decided)
        assert result.abstained
        assert result.supplementary_unit is None
