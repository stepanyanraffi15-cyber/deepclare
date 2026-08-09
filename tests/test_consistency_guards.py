"""The rewrite guardrails, and the input contract they depend on.

Every one of these is a rule the rewrite prompt also states. The point of testing them
here is that the prompt is a request: the specification records both losses below —
restyling away a computed figure, and erasing the token that tells two members of a
product family apart — as measured behaviour of a model that had been asked not to.

No network, no provider, no reference data.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from deepclare.consistency import DraftedLine
from deepclare.consistency.guards import (
    collapsed_lines,
    dropped_number_tokens,
    refusal_for_description,
)

FAMILY = "ՊՈՂՊԱՏԵ ՊՏՈՒՏԱԿ, ՄԵՏՐԻԿ ՊԱՐՈՒՅՐՈՎ"


def drafted(
    line_id: str = "1",
    *,
    source_name: str = "STEEL BOLT M8X40",
    description: str = f"{FAMILY}, M8X40, 500 ՀԱՏ",
    segments: tuple[str, ...] = ("500 ՀԱՏ",),
    code: str | None = "7318159009",
) -> DraftedLine:
    return DraftedLine(
        line_id=line_id,
        source_name=source_name,
        description=description,
        deterministic_segments=segments,
        code=code,
    )


# --- the input contract ------------------------------------------------------


def test_a_segment_that_is_not_in_the_text_is_refused_at_construction() -> None:
    """A guardrail that can never pass would refuse every rewrite of that line."""
    with pytest.raises(ValidationError, match="not in the description"):
        drafted(segments=("900 ՀԱՏ",))


def test_a_blank_segment_is_refused_at_construction() -> None:
    with pytest.raises(ValidationError, match="blank"):
        drafted(segments=("   ",))


# --- what a description rewrite may not do -----------------------------------


def test_a_conforming_rewrite_is_accepted() -> None:
    line = drafted()
    assert refusal_for_description(line, f"{FAMILY}, ՑԻՆԿԱՊԱՏ, M8X40, 500 ՀԱՏ") is None


def test_an_empty_rewrite_is_refused() -> None:
    assert "no text" in (refusal_for_description(drafted(), "   ") or "")


def test_a_rewrite_in_another_script_is_refused() -> None:
    refusal = refusal_for_description(drafted(), "STEEL BOLT M8X40, 500 pcs")
    assert refusal is not None
    assert "no Armenian" in refusal


def test_a_rewrite_that_does_not_reproduce_a_computed_segment_is_refused() -> None:
    """The quantity phrase is arithmetic. A model rewording it is a model writing a
    figure, which is the one thing this module must never do."""
    refusal = refusal_for_description(drafted(), f"{FAMILY}, M8X40, ՀԱՏ 500")
    assert refusal is not None
    assert "'500 ՀԱՏ'" in refusal
    assert "verbatim" in refusal


def test_a_rewrite_that_drops_the_lines_own_size_is_refused() -> None:
    refusal = refusal_for_description(drafted(), f"{FAMILY}, 500 ՀԱՏ")
    assert refusal is not None
    assert "'8'" in refusal or "'40'" in refusal


def test_a_figure_the_draft_already_left_out_is_not_this_passs_to_restore() -> None:
    """`40` is on the invoice and not in the drafted text, so a rewrite that also omits
    it has dropped nothing."""
    line = drafted(description=f"{FAMILY}, 500 ՀԱՏ")
    assert dropped_number_tokens(line, f"{FAMILY}, ՑԻՆԿԱՊԱՏ, 500 ՀԱՏ") == ()


def test_the_token_check_is_blind_to_the_decimal_separator() -> None:
    line = drafted(
        source_name="STEEL BOLT M8X40, 42.5 MM",
        description=f"{FAMILY}, M8X40, 42.5 ՄՄ, 500 ՀԱՏ",
    )
    assert dropped_number_tokens(line, f"{FAMILY}, M8X40, 42,5 ՄՄ, 500 ՀԱՏ") == ()


# --- what a rewrite may not do to the set of lines ---------------------------


def test_a_rewrite_that_merges_two_distinct_lines_is_named() -> None:
    drafted_texts = {"1": "ՊՏՈՒՏԱԿ M8X40", "2": "ԱՄՐԱԿ M8X60"}
    resulting = {"1": "ՊՏՈՒՏԱԿ M8X40", "2": "ՊՏՈՒՏԱԿ M8X40"}
    assert collapsed_lines(drafted_texts, resulting) == {"2"}


def test_lines_that_already_read_alike_are_left_alone() -> None:
    """Two lines of identical goods may legitimately carry identical text; the guard is
    about a rewrite *merging* two lines, not about equality."""
    drafted_texts = {"1": "ՊՏՈՒՏԱԿ", "2": "ՊՏՈՒՏԱԿ"}
    assert collapsed_lines(drafted_texts, dict(drafted_texts)) == frozenset()


def test_only_the_lines_the_rewrite_moved_are_named() -> None:
    """Reverting them always resolves the collision, because the drafts differed."""
    drafted_texts = {"1": "A", "2": "B", "3": "C"}
    resulting = {"1": "A", "2": "A", "3": "C"}
    assert collapsed_lines(drafted_texts, resulting) == {"2"}
