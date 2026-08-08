"""What the writer sends, and what it refuses to hand back.

The provider is a stub transport here: the checks are on the request that would have gone
out and on the record built from an answer. Nothing in this file touches the network.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from deepclare.config import Settings
from deepclare.description import (
    DescriptionCompleteness,
    DescriptionError,
    DescriptionWriter,
    LineContext,
    ProductKind,
    WriteDescription,
    description_from_answer,
)
from deepclare.domain import SourceLanguage, ValueOrigin
from deepclare.models import Decoding, GenerativeModel, ModelCall, ModelTier, TokenUsage

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

CALL = ModelCall(
    tier=ModelTier.STANDARD,
    model_id="a-model",
    prompt_name="write_description",
    prompt_version="1",
    decoding=Decoding(max_output_tokens=1024),
    usage=TokenUsage(),
)


def context(**fields: object) -> LineContext:
    defaults: dict[str, object] = {
        "line_id": "1",
        "goods_name": "CABLE NYY-J 3X2.5MM2",
        "source_language": SourceLanguage.ENGLISH_LATIN,
    }
    return LineContext(**(defaults | fields))


def answer(**fields: object) -> WriteDescription:
    defaults: dict[str, object] = {
        "description": "ՄԱԼՈՒԽ, ՆԱԽԱՏԵՍՎԱԾ Է ԷԼԵԿՏՐԱԿԱՆ ՀՈՍԱՆՔԻ ՀԱՂՈՐԴՄԱՆ ՀԱՄԱՐ",
        "search_term": "ԷԼԵԿՏՐԱԿԱՆ ՄԱԼՈՒԽ",
        "product_kind": "length",
        "completeness": "high",
    }
    return WriteDescription(**(defaults | fields))


def settings(prompts_dir: Path) -> Settings:
    return Settings(
        google_api_key="not-a-real-key",
        genai_api_base="https://example.invalid/v1beta",
        genai_model_cheap="cheap",
        genai_model_standard="standard",
        genai_model_strong="strong",
        genai_max_output_tokens=1024,
        genai_timeout_seconds=30.0,
        prompts_dir=prompts_dir,
        qdrant_path=prompts_dir,
        qdrant_collection="codes",
        reference_dir=prompts_dir,
        reference_snapshot_dir=prompts_dir,
        nomenclature_api_base="https://example.invalid",
        nomenclature_max_node_id=1,
        nomenclature_crawl_workers=1,
    )


def writer_over(
    sent: list[httpx.Request], reply: WriteDescription | None = None
) -> DescriptionWriter:
    """A writer whose provider answers `reply` and records what it was asked."""
    body = (reply or answer()).model_dump_json()

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": body}]}, "finishReason": "STOP"}
                ],
                "modelVersion": "standard-001",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    return DescriptionWriter(GenerativeModel(settings(PROMPTS), client), PROMPTS)


def prompt_text(request: httpx.Request) -> str:
    parts = json.loads(request.content)["contents"][0]["parts"]
    return "".join(part["text"] for part in parts if "text" in part)


def test_the_line_and_its_context_reach_the_prompt() -> None:
    sent: list[httpx.Request] = []
    writer_over(sent).write(
        context(
            goods_name="RAY TAŞIYICI",
            source_language=SourceLanguage.TURKISH,
            unit="PCS",
            unit_price=Decimal("2.40"),
            trade_name="MKR 2,5",
            material="polyamide",
            grounding_facts=("Use: DIN rail mounting",),
            sibling_names=("TERMINAL BLOCK 2.5MM", "ENCODER E50S8"),
        )
    )
    text = prompt_text(sent[0])
    for expected in (
        "RAY TAŞIYICI",
        "turkish",
        "PCS",
        "2.40",
        "MKR 2,5",
        "polyamide",
        "- Use: DIN rail mounting",
        "- TERMINAL BLOCK 2.5MM",
        "- ENCODER E50S8",
    ):
        assert expected in text


def test_absence_is_stated_rather_than_omitted() -> None:
    sent: list[httpx.Request] = []
    writer_over(sent).write(context())
    text = prompt_text(sent[0])
    assert text.count("unknown") >= 4, "unit, price, brand and material are all absent"
    assert "(none)" in text, "the empty fact and sibling blocks are stated"


def test_the_commodity_code_cannot_reach_the_call() -> None:
    """The withheld things are withheld by construction, not by instruction."""
    assert "printed_customs_code" not in LineContext.model_fields
    assert "quantity" not in LineContext.model_fields


def test_no_page_image_is_sent() -> None:
    sent: list[httpx.Request] = []
    writer_over(sent).write(context())
    parts = json.loads(sent[0].content)["contents"][0]["parts"]
    assert all("inline_data" not in part for part in parts)


def test_a_provider_failure_becomes_one_description_error_and_no_second_call() -> None:
    calls: list[httpx.Request] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503, text="upstream unavailable")

    client = httpx.Client(transport=httpx.MockTransport(refuse))
    writer = DescriptionWriter(GenerativeModel(settings(PROMPTS), client), PROMPTS)
    with pytest.raises(DescriptionError, match="line 1"):
        writer.write(context())
    assert len(calls) == 1, "there is no retry on a run-time model call"


def test_the_written_values_carry_the_prompt_that_wrote_them() -> None:
    written = description_from_answer(answer(), context(), CALL)
    assert written.line_id == "1"
    assert written.product_kind.value is ProductKind.LENGTH
    assert written.completeness is DescriptionCompleteness.HIGH
    for value in (written.text, written.search_term, written.product_kind):
        assert value.provenance.origin is ValueOrigin.GENERATED
        assert value.provenance.stage == "description"
        assert value.provenance.prompt_name == "write_description"
        assert value.provenance.prompt_version == "1"


def test_a_generated_value_states_how_far_to_trust_it() -> None:
    for completeness, expected in (("high", 0.9), ("medium", 0.6), ("low", 0.3)):
        written = description_from_answer(
            answer(completeness=completeness), context(), CALL
        )
        assert written.text.confidence.derivation == expected


def test_surrounding_whitespace_is_dropped() -> None:
    written = description_from_answer(
        answer(description="  ՄԱԼՈՒԽ NYY-J  \n"), context(), CALL
    )
    assert written.text.value == "ՄԱԼՈՒԽ NYY-J"


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_a_blank_description_is_not_a_description(blank: str) -> None:
    with pytest.raises(DescriptionError, match="came back empty"):
        description_from_answer(answer(description=blank), context(), CALL)


def test_text_in_another_script_is_refused() -> None:
    """The declaration is filed in Armenian; Latin text is not a description."""
    with pytest.raises(DescriptionError, match="no Armenian text"):
        description_from_answer(
            answer(description="CABLE NYY-J, for electrical current"), context(), CALL
        )


def test_a_search_term_in_another_script_is_refused() -> None:
    with pytest.raises(DescriptionError, match="search term"):
        description_from_answer(answer(search_term="electrical cable"), context(), CALL)


def test_a_figure_no_document_states_is_refused() -> None:
    with pytest.raises(DescriptionError, match="'1000'"):
        description_from_answer(
            answer(description="ՄԱԼՈՒԽ NYY-J, ԼԱՐՈՒՄԸ ՄԻՆՉԵՎ 1000 Վ"), context(), CALL
        )


def test_figures_the_documents_state_are_kept() -> None:
    written = description_from_answer(
        answer(description="ՄԱԼՈՒԽ NYY-J 3X2.5MM2, ՊՂՆՁՅԱ"),
        context(goods_name="CABLE NYY-J 3X2.5MM2"),
        CALL,
    )
    assert "3X2.5MM2" in written.text.value


def test_a_figure_from_a_stated_fact_is_kept() -> None:
    written = description_from_answer(
        answer(description="ՑԵԼՅՈՒԼՈԶԱՅԻՆ ԵԹԵՐ, 99% ՀԻԴՐՕՔՍԻՊՐՈՊԻԼ ՄԵԹԻԼՑԵԼՅՈՒԼՈԶԱ"),
        context(goods_name="GMC 3112D", grounding_facts=("HPMC 99% stated on label",)),
        CALL,
    )
    assert "99%" in written.text.value


def test_a_separator_written_differently_is_not_an_invention() -> None:
    written = description_from_answer(
        answer(description="ՑԵՄԵՆՏ CEM I 42,5 N"),
        context(goods_name="CEMENT CEM I 42.5 N"),
        CALL,
    )
    assert "42,5" in written.text.value


def test_the_price_is_not_a_document_figure() -> None:
    """Copying the price into the filed text is one of the ways a figure gets invented."""
    with pytest.raises(DescriptionError, match="'25'"):
        description_from_answer(
            answer(description="ԱՎՏՈՄԱՏ ԱՆՋԱՏԻՉ, ԳԻՆԸ 25"),
            context(goods_name="CIRCUIT BREAKER", unit_price=Decimal("25")),
            CALL,
        )


def test_the_prompt_is_the_one_the_writer_names() -> None:
    """The bound schema and the prompt reach the model together; the schema's fields are
    the four the prompt's output contract describes."""
    sent: list[httpx.Request] = []
    writer_over(sent).write(context())
    body = json.loads(sent[0].content)
    schema = body["generationConfig"]["responseJsonSchema"]
    assert set(schema["required"]) == {
        "description",
        "search_term",
        "product_kind",
        "completeness",
    }
    assert all(
        "description" not in property_schema
        for property_schema in schema["properties"].values()
    ), "a schema field description is prompt text and belongs in the prompt file"
    assert "description" not in schema, "so is a schema-level one"
