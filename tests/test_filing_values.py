"""How values are written down. Dossier 03 §6, one rule per test."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from deepclare.filing.errors import UnrepresentableValue
from deepclare.filing.values import (
    boolean_text,
    code_text,
    date_text,
    decimal_text,
    integer_text,
    truncated_text,
)


@pytest.mark.parametrize(
    ("value", "written"),
    [
        ("0", "0"),
        ("0.00", "0"),
        ("12.50", "12.5"),
        ("12.000", "12"),
        ("100", "100"),
        ("1250.50", "1250.5"),
        ("1234567.89", "1234567.89"),
        ("0.10", "0.1"),
        ("1E+3", "1000"),
    ],
)
def test_numbers_carry_no_trailing_zeros_and_no_exponent(value: str, written: str) -> None:
    assert decimal_text(Decimal(value)) == written


def test_an_integral_value_is_written_without_a_decimal_point() -> None:
    assert "." not in decimal_text(Decimal("6000.00"))


def test_a_negative_number_is_refused_rather_than_written() -> None:
    with pytest.raises(UnrepresentableValue):
        decimal_text(Decimal("-1"))


def test_a_non_finite_number_is_refused() -> None:
    with pytest.raises(UnrepresentableValue):
        decimal_text(Decimal("NaN"))


def test_a_negative_count_is_refused() -> None:
    with pytest.raises(UnrepresentableValue):
        integer_text(-1)


def test_dates_are_iso_with_no_time_and_no_zone() -> None:
    assert date_text(date(2026, 3, 4)) == "2026-03-04"


def test_the_container_indicator_is_lowercase() -> None:
    assert (boolean_text(True), boolean_text(False)) == ("true", "false")


def test_a_padded_code_keeps_its_leading_zeros() -> None:
    assert code_text("055") == "055"
    assert code_text("000") == "000"


def test_a_code_that_lost_its_padding_to_an_integer_is_not_repaired() -> None:
    # Nothing can recover the width once it is gone; the point of the check is that a
    # code arrives as the string it was written as, so the failure is visible upstream.
    assert code_text("55") == "55"


def test_an_empty_or_whitespace_bearing_code_is_refused() -> None:
    with pytest.raises(UnrepresentableValue):
        code_text("")
    with pytest.raises(UnrepresentableValue):
        code_text(" 166 ")


def test_a_short_text_is_left_alone() -> None:
    assert truncated_text("ԵՐԵՎԱՆ", 50) == ("ԵՐԵՎԱՆ", False)


def test_an_over_long_text_is_cut_and_says_so() -> None:
    written, was_cut = truncated_text("Ա" * 60, 50)
    assert (len(written), was_cut) == (50, True)


def test_a_cut_landing_on_a_space_leaves_no_trailing_whitespace() -> None:
    written, _ = truncated_text("A" * 49 + " BBBB", 50)
    assert written == "A" * 49
