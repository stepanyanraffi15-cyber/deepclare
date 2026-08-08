"""The declared graph: what it refuses to declare, and what a traversal actually does.

Every test here runs the real graph, the real nodes and the real prompt files against a
store and a model that answer from dictionaries. Nothing touches the network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deepclare.classification.features import ClassificationFeatures
from deepclare.classification import (
    ClassificationFeatures,
    Classifier,
    Edge,
    Graph,
    GraphDeclarationError,
    Node,
    NodeContext,
    build_graph,
)
from deepclare.classification.graph import END, ENTRY
from deepclare.classification.schemas import (
    PickCode,
    PickHeading,
    PreferSubheading,
    ShortlistChapters,
    VerifyCode,
)
from tests.classification_fakes import FakeModel, FakeStore, candidate, entry, line

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

PLASTIC_BAG = candidate("3923210000", 0.83, "sacks and bags of polymers of ethylene")
PLASTIC_OTHER = candidate("3923290000", 0.78, "of other plastics")
PLASTIC_ARTICLE = candidate("3926909000", 0.71, "other articles of plastics")


def store(search=None) -> FakeStore:
    return FakeStore(
        entries=[
            entry("39", "PLASTICS AND ARTICLES THEREOF"),
            entry("85", "ELECTRICAL MACHINERY AND EQUIPMENT"),
            entry("3923210000", "sacks and bags of polymers of ethylene", unit="шт"),
            entry("3923290000", "of other plastics"),
            entry("3926909000", "other articles of plastics"),
            entry("8536509000", "other switches"),
        ],
        headings={
            "3923": "Articles for the conveyance or packing of goods, of plastics:",
            "3926": "Other articles of plastics:",
            "8536": "Electrical apparatus for switching or protecting circuits:",
        },
        subheadings={
            "392321": "of polymers of ethylene:",
            "392329": "of other plastics:",
        },
        notes={"39": "Chapter 39 legal note, abbreviated for the test."},
        search=search or (lambda _q, _p, _l: [PLASTIC_BAG, PLASTIC_OTHER, PLASTIC_ARTICLE]),
    )


def classifier(fake_store, answers, **features) -> tuple[Classifier, FakeModel]:
    model = FakeModel(answers)
    return (
        Classifier(
            store=fake_store,
            model=model,
            prompts_dir=PROMPTS,
            features=ClassificationFeatures(**features),
        ),
        model,
    )


def steps_of(result) -> list[str]:
    return [step.node for step in result.steps]


CHAPTER_39 = ShortlistChapters(
    identity="a polyethylene bag", chapters=["39"], reasoning="it is a plastic article"
)
HEADING_3923 = PickHeading(
    headings=["3923"],
    search_text="plastics and articles thereof — articles for the conveyance or packing "
    "of goods — sacks and bags of polymers of ethylene",
    reasoning="it is packing ware",
)
CHOSE_THE_BAG = PickCode(
    identification="a bag of polyethylene for packing goods",
    material_decisive=False,
    material_assumed="",
    abstain=False,
    chosen_code="3923210000",
    llm_confidence=0.9,
    rationale="the polymer is stated and the article is a sack",
    missing_evidence="",
    legal_basis="GIR 1",
)


class TestDeclaration:
    def test_the_whole_graph_prints_without_running(self):
        printed = build_graph(
            NodeContext(
                store=None, model=None, prompts_dir=PROMPTS,
                features=ClassificationFeatures(),
            )
        ).describe()
        for node in ("C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7"):
            assert node in printed
        assert "C7    -> C1" in printed

    def test_an_edge_to_a_node_that_does_not_exist_is_refused(self):
        node = Node("A", "a", "a", lambda state: state)
        with pytest.raises(GraphDeclarationError, match="unknown node"):
            Graph("g", [node], [Edge(ENTRY, "A", "always"), Edge("A", "B", "always")])

    def test_a_node_whose_last_edge_is_conditional_is_refused(self):
        node = Node("A", "a", "a", lambda state: state)
        with pytest.raises(GraphDeclarationError, match="last edge"):
            Graph(
                "g",
                [node],
                [Edge(ENTRY, "A", "always"), Edge("A", END, "sometimes", lambda _s: True)],
            )

    def test_an_edge_declared_after_an_unconditional_one_is_refused(self):
        node = Node("A", "a", "a", lambda state: state)
        with pytest.raises(GraphDeclarationError, match="never be taken"):
            Graph(
                "g",
                [node],
                [
                    Edge(ENTRY, "A", "always"),
                    Edge("A", END, "always"),
                    Edge("A", "A", "also always"),
                ],
            )

    def test_a_node_nothing_reaches_is_refused(self):
        reached = Node("A", "a", "a", lambda state: state)
        orphan = Node("B", "b", "b", lambda state: state)
        with pytest.raises(GraphDeclarationError, match="cannot be reached"):
            Graph(
                "g",
                [reached, orphan],
                [
                    Edge(ENTRY, "A", "always"),
                    Edge("A", END, "always"),
                    Edge("B", END, "always"),
                ],
            )


class TestNormalNarrowing:
    def test_a_line_with_no_printed_code_narrows_then_retrieves_then_picks(self):
        subject, model = classifier(store(), [CHAPTER_39, HEADING_3923, CHOSE_THE_BAG])
        result = subject.classify(line())

        assert steps_of(result) == ["C1", "C2", "C4", "C5"]
        assert result.code is not None
        assert result.code.value == "3923210000"
        assert result.supplementary_unit == "шт"
        assert result.legal_basis == "GIR 1"
        assert result.candidates == (PLASTIC_BAG, PLASTIC_OTHER, PLASTIC_ARTICLE)
        assert model.remaining == 0

    def test_the_composite_confidence_is_computed_here_not_taken_from_the_model(self):
        subject, _ = classifier(store(), [CHAPTER_39, HEADING_3923, CHOSE_THE_BAG])
        result = subject.classify(line())
        # 0.4 x (0.83+1)/2 + 0.3 x 1/3 agreeing at six digits + 0.3 x 0.9
        assert result.confidence == pytest.approx(0.7360, abs=5e-5)
        assert result.confidence != CHOSE_THE_BAG.llm_confidence

    def test_the_final_pick_is_never_shown_the_sibling_lines(self):
        subject, model = classifier(store(), [CHAPTER_39, HEADING_3923, CHOSE_THE_BAG])
        subject.classify(
            line().model_copy(update={"sibling_names": ("A NEIGHBOURING PRODUCT",)})
        )
        by_name = {prompt.name: prompt.text for prompt in model.prompts}
        assert "A NEIGHBOURING PRODUCT" in by_name["shortlist_chapters"]
        assert "A NEIGHBOURING PRODUCT" not in by_name["pick_code"]

    def test_retrieval_is_scoped_to_the_chosen_headings_inside_the_store(self):
        subject_store = store()
        subject, _ = classifier(subject_store, [CHAPTER_39, HEADING_3923, CHOSE_THE_BAG])
        subject.classify(line())
        _query, prefixes, limit = subject_store.searches[0]
        assert prefixes == ["3923"]
        assert limit == ClassificationFeatures().candidate_limit


class TestDegradations:
    def test_a_shortlist_naming_no_real_chapter_degrades_to_an_unfiltered_search(self):
        nothing_real = ShortlistChapters(
            identity="unclear", chapters=["99", "zz"], reasoning="unsure"
        )
        subject_store = store()
        subject, model = classifier(subject_store, [nothing_real, CHOSE_THE_BAG])
        result = subject.classify(line())

        assert steps_of(result) == ["C1", "C2", "C4", "C5"]
        assert subject_store.searches[0][1] is None
        assert model.remaining == 0

    def test_an_empty_search_text_falls_back_to_the_deterministic_query(self):
        no_query = PickHeading(headings=["3923"], search_text="  ", reasoning="")
        subject_store = store()
        subject, _ = classifier(subject_store, [CHAPTER_39, no_query, CHOSE_THE_BAG])
        subject.classify(line(source_name="POLYETHYLENE SACK"))
        query = subject_store.searches[0][0]
        assert query.count(" — ") == 2
        assert query.endswith("POLYETHYLENE SACK")

    def test_retrieving_nothing_abstains_without_a_model_call(self):
        subject, model = classifier(
            store(search=lambda _q, _p, _l: []), [CHAPTER_39, HEADING_3923]
        )
        result = subject.classify(line())

        assert result.abstained
        assert result.confidence == 0.0
        assert "no commodity codes" in result.rationale
        assert result.resolving_evidence
        assert model.remaining == 0


class TestAbstention:
    def test_an_explicit_abstention_keeps_the_candidates_for_the_audit_trail(self):
        declined = PickCode(
            identification="a bare name with no material",
            material_decisive=True,
            material_assumed="",
            abstain=True,
            chosen_code="",
            llm_confidence=0.0,
            rationale="steel → 7326..., plastic → 3926...; the line does not say which",
            missing_evidence="state whether the body is steel or plastic",
            legal_basis="",
        )
        subject, _ = classifier(store(), [CHAPTER_39, HEADING_3923, declined])
        result = subject.classify(line())

        assert result.abstained
        assert result.candidates == (PLASTIC_BAG, PLASTIC_OTHER, PLASTIC_ARTICLE)
        assert result.material_decisive
        assert result.resolving_evidence == "state whether the body is steel or plastic"
        assert "steel" in result.rationale and "plastic" in result.rationale

    def test_a_code_the_model_invented_abstains_rather_than_being_substituted(self):
        invented = CHOSE_THE_BAG.model_copy(update={"chosen_code": "9999999999"})
        subject, _ = classifier(store(), [CHAPTER_39, HEADING_3923, invented])
        result = subject.classify(line())

        assert result.abstained
        assert "9999999999" in result.rationale
        assert result.candidates[0] == PLASTIC_BAG
        assert result.confidence == 0.0

    def test_a_blank_rationale_is_refused_rather_than_filled_in(self):
        silent = CHOSE_THE_BAG.model_copy(update={"rationale": "   "})
        subject, _ = classifier(store(), [CHAPTER_39, HEADING_3923, silent])
        with pytest.raises(Exception, match="no rationale"):
            subject.classify(line())


class TestPrintedCodeFastPath:
    def test_a_usable_printed_code_skips_both_narrowing_calls(self):
        subject, model = classifier(store(), [CHOSE_THE_BAG])
        result = subject.classify(line(printed_code="3923.21.00.00.19"))

        assert steps_of(result) == ["C0", "C4", "C5"]
        assert model.remaining == 0
        assert result.code.value == "3923210000"

    def test_a_printed_code_this_tree_cannot_use_takes_the_normal_route(self):
        subject, _ = classifier(store(), [CHAPTER_39, HEADING_3923, CHOSE_THE_BAG])
        result = subject.classify(line(printed_code="9999.99"))
        assert steps_of(result) == ["C1", "C2", "C4", "C5"]

    def test_a_dead_end_clears_the_scope_and_narrows_normally_exactly_once(self):
        only_the_other_heading = lambda _q, prefixes, _l: (  # noqa: E731
            [PLASTIC_ARTICLE] if prefixes == ["3926"] else []
        )
        other_heading = PickHeading(
            headings=["3926"], search_text="plastics — other articles", reasoning="x"
        )
        chose_the_article = CHOSE_THE_BAG.model_copy(
            update={"chosen_code": "3926909000"}
        )
        subject, model = classifier(
            store(search=only_the_other_heading),
            [CHAPTER_39, other_heading, chose_the_article],
        )
        result = subject.classify(line(printed_code="392321000019"))

        assert steps_of(result) == ["C0", "C4", "C5", "C7", "C1", "C2", "C4", "C5"]
        assert result.code.value == "3926909000"
        assert model.remaining == 0

    def test_a_second_dead_end_terminates_because_the_guard_is_the_cleared_slot(self):
        subject, model = classifier(
            store(search=lambda _q, _p, _l: []), [CHAPTER_39, HEADING_3923]
        )
        result = subject.classify(line(printed_code="392321000019"))

        assert steps_of(result) == ["C0", "C4", "C5", "C7", "C1", "C2", "C4", "C5"]
        assert steps_of(result).count("C7") == 1
        assert result.abstained
        assert model.remaining == 0


class TestOptionalNodes:
    def test_the_subheading_preference_marks_candidates_and_removes_none(self):
        prefers = PreferSubheading(subheadings=["392329"], reasoning="other plastics")
        subject_store = store()
        subject, model = classifier(
            subject_store,
            [CHAPTER_39, HEADING_3923, prefers, CHOSE_THE_BAG],
            subheading_preference=True,
        )
        result = subject.classify(line())

        assert steps_of(result) == ["C1", "C2", "C3", "C4", "C5"]
        assert subject_store.searches[0][1] == ["3923"]
        assert len(result.candidates) == 3
        pick_prompt = next(p.text for p in model.prompts if p.name == "pick_code")
        assert "matches a likely 6-digit subheading" in pick_prompt

    def test_a_veto_becomes_an_abstention_and_keeps_the_material_verdict(self):
        material = CHOSE_THE_BAG.model_copy(
            update={"material_decisive": True, "material_assumed": "polyethylene"}
        )
        rejected = VerifyCode(reason="this is packing ware, not a sack", correct=False)
        subject, _ = classifier(
            store(), [CHAPTER_39, HEADING_3923, material, rejected], verification=True
        )
        result = subject.classify(line())

        assert steps_of(result) == ["C1", "C2", "C4", "C5", "C6"]
        assert result.abstained
        assert result.supplementary_unit is None
        assert result.material_decisive
        assert result.material_assumed == "polyethylene"
        assert "3923210000" in result.rationale

    def test_a_confirmation_leaves_the_pick_alone(self):
        confirmed = VerifyCode(reason="the category matches", correct=True)
        subject, _ = classifier(
            store(), [CHAPTER_39, HEADING_3923, CHOSE_THE_BAG, confirmed], verification=True
        )
        result = subject.classify(line())
        assert result.code.value == "3923210000"
        assert result.supplementary_unit == "шт"
