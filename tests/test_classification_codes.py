"""Reading code-shaped text, and the confidence blend. No network, no artifact."""

from __future__ import annotations

import pytest

from deepclare.classification.codes import (
    digits_of,
    harmonized_prefix,
    is_filler,
    leaf_form,
    national_suffix,
    normalize_at,
    normalize_chapter,
)
from deepclare.classification.confidence import (
    agreement,
    below_review_gate,
    composite_confidence,
    normalized_similarity,
)
from tests.classification_fakes import candidate


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("8536.50.90 00", "8536509000"),
        ("HS 3923", "3923"),
        ("", ""),
        (None, ""),
    ],
)
def test_only_the_digits_survive(printed, expected):
    assert digits_of(printed) == expected


def test_a_run_of_zeros_is_a_filler_not_a_code():
    assert is_filler("00000000000")
    assert not is_filler("0000000001")
    assert not is_filler("")


class TestHarmonizedPrefix:
    def test_takes_the_first_six_digits_of_a_foreign_national_code(self):
        assert harmonized_prefix("8536.50.90.00.00") == "853650"

    def test_refuses_a_code_that_never_reaches_the_harmonized_level(self):
        assert harmonized_prefix("3923") is None

    def test_refuses_a_filler(self):
        assert harmonized_prefix("00000000000") is None

    def test_refuses_nothing_at_all(self):
        assert harmonized_prefix(None) is None


class TestLeafForm:
    def test_ten_digits_pass_through(self):
        assert leaf_form("3923210000") == "3923210000"

    def test_the_filed_eleven_digit_form_reduces_to_its_leaf(self):
        assert leaf_form("39232100000") == "3923210000"

    def test_a_short_stub_is_not_a_code_that_can_be_filed(self):
        assert leaf_form("392321") is None

    def test_letters_are_not_a_code(self):
        assert leaf_form("39232100AB") is None

    def test_a_filler_is_not_a_code(self):
        assert leaf_form("00000000000") is None


def test_the_national_suffix_is_only_read_from_an_eleven_digit_form():
    assert national_suffix("39232100001") == "1"
    assert national_suffix("39232100000") == "0"
    assert national_suffix("3923210000") is None


class TestChapterNormalization:
    def test_a_single_digit_is_left_padded(self):
        assert normalize_chapter("5") == "05"

    def test_a_longer_code_is_truncated_to_its_chapter(self):
        assert normalize_chapter("392690") == "39"

    def test_punctuation_is_ignored(self):
        assert normalize_chapter("ch. 39") == "39"

    def test_nothing_numeric_is_no_chapter(self):
        assert normalize_chapter("plastics") is None


class TestFixedWidthNormalization:
    def test_a_heading_answer_is_truncated_not_padded(self):
        assert normalize_at("392690", 4) == "3926"

    def test_a_short_answer_names_no_heading(self):
        assert normalize_at("392", 4) is None


class TestCompositeConfidence:
    def test_cosine_is_mapped_from_minus_one_to_one_before_it_is_blended(self):
        assert normalized_similarity(-1.0) == 0.0
        assert normalized_similarity(0.0) == 0.5
        assert normalized_similarity(1.0) == 1.0

    def test_agreement_is_the_share_sharing_the_prefix(self):
        candidates = [
            candidate("3923210000", 0.9),
            candidate("3923290000", 0.8),
            candidate("3926909000", 0.7),
            candidate("3926901000", 0.6),
        ]
        assert agreement(candidates, "3923210000", 6) == 0.25
        assert agreement(candidates, "3923210000", 4) == 0.5

    def test_nothing_agrees_with_a_pick_that_had_no_candidates(self):
        assert agreement([], "3923210000", 6) == 0.0

    def test_the_three_signals_blend_in_the_specified_proportions(self):
        candidates = [candidate("3923210000", 0.8), candidate("3926909000", 0.5)]
        # normalized similarity 0.9, agreement at six digits 0.5, self-report 0.6
        expected = round(0.4 * 0.9 + 0.3 * 0.5 + 0.3 * 0.6, 4)
        assert (
            composite_confidence(
                similarity=0.8,
                candidates=candidates,
                code="3923210000",
                self_report=0.6,
            )
            == expected
        )

    def test_a_perfect_agreement_and_a_perfect_self_report_still_answer_below_one(self):
        # A cosine of 1.0 is the only way to reach 1.0, and no real retrieval returns it.
        candidates = [candidate("3923210000", 0.85)]
        assert composite_confidence(
            similarity=0.85, candidates=candidates, code="3923210000", self_report=1.0
        ) < 1.0


class TestReviewGate:
    def test_low_confidence_alone_flags_the_line(self):
        assert below_review_gate(
            confidence=0.69,
            heading_agreement=1.0,
            confidence_floor=0.7,
            heading_agreement_floor=0.5,
        )

    def test_a_candidate_list_that_does_not_corroborate_the_heading_flags_it(self):
        assert below_review_gate(
            confidence=0.95,
            heading_agreement=0.2,
            confidence_floor=0.7,
            heading_agreement_floor=0.5,
        )

    def test_a_confident_corroborated_pick_passes(self):
        assert not below_review_gate(
            confidence=0.7,
            heading_agreement=0.5,
            confidence_floor=0.7,
            heading_agreement_floor=0.5,
        )
