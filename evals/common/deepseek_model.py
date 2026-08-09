"""A DeepSeek-backed stand-in for GenerativeModel, for measurement only.

This lives in tests/ deliberately. Changing which model serves which call is an
architectural decision and `.claude/skills/architecture-review` gates it; running a
comparison to find out whether it is worth proposing is not. Nothing under src/ is
touched, and the product still ships on Gemini.

WHAT DIFFERS FROM THE GEMINI PATH, and why it matters for reading the results:

* **Schema enforcement.** Gemini is handed `responseJsonSchema` and constrains decoding
  to it. DeepSeek via OpenRouter rejects `response_format: json_schema` outright
  ("This response_format type is unavailable now"), so the best available is
  `json_object` plus the schema written into the prompt. The model is *asked* rather
  than *forced*, so malformed output is a real failure mode here and is not on Gemini.
  ModelOutputError therefore measures something slightly different on each provider.

* **No images.** DeepSeek V4 is text-only; sending an image returns
  `404 No endpoints found that support image input`. generate_from_pages raises rather
  than silently dropping the pages.

* **Reasoning is on by default** at effort=high, and those tokens are billed as output
  and count against max_tokens. A ceiling too low truncates mid-JSON, which surfaces as
  ModelOutputError rather than as a transport failure.
"""

from __future__ import annotations

import json
import re
from types import TracebackType
from typing import Any, Sequence, TypeVar

import httpx
from pydantic import BaseModel
from typing_extensions import Self

from deepclare.config import Settings
from deepclare.models import (
    Decoding,
    ModelCall,
    ModelOutputError,
    ModelRefusedError,
    ModelResult,
    ModelTier,
    ModelTransportError,
    PageImage,
    TokenUsage,
    _excerpt,
    _validate,
)
from deepclare.prompting import Prompt

T = TypeVar("T", bound=BaseModel)

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"

# Flash for the label-emitting and writing calls, pro for the one that turns on a
# material distinction — the same shape as the Gemini tier assignment.
DEFAULT_TIERS = {
    ModelTier.CHEAP: "deepseek/deepseek-v4-flash",
    ModelTier.STANDARD: "deepseek/deepseek-v4-flash",
    ModelTier.STRONG: "deepseek/deepseek-v4-pro",
}

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


class DeepSeekModel:
    """Same surface as GenerativeModel: generate() -> ModelResult[T], or raise."""

    def __init__(
        self,
        settings: Settings,
        api_key: str,
        *,
        tiers: dict[ModelTier, str] | None = None,
        reasoning_tiers: frozenset[ModelTier] = frozenset({ModelTier.STRONG}),
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model_by_tier = tiers or DEFAULT_TIERS
        # Measured at 24-way concurrency on a ~800-token prompt: reasoning costs 21x
        # more and runs 12x slower per call. It is worth it on the tier that decides a
        # material distinction and not on menu-narrowing or description writing.
        self._reasoning_tiers = reasoning_tiers
        self._decoding = Decoding(max_output_tokens=settings.genai_max_output_tokens)
        self._http = http_client or httpx.Client(timeout=settings.genai_timeout_seconds)
        self._owns_http_client = http_client is None

    def generate(
        self,
        *,
        tier: ModelTier,
        prompt: Prompt,
        output: type[T],
        decoding: Decoding | None = None,
    ) -> ModelResult[T]:
        model_id = self._model_by_tier[tier]
        used = decoding or self._decoding
        payload = self._post(model_id, self._body(prompt, output, used, tier))

        choice = (payload.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        if not text.strip():
            finish = choice.get("finish_reason")
            raise ModelRefusedError(
                f"{model_id} returned no content (finish_reason={finish!r}). "
                "With reasoning on, an exhausted token ceiling shows up exactly like this."
            )
        value = _validate(_FENCE.sub("", text).strip(), output, model_id)

        return ModelResult[output](
            value=value,
            call=ModelCall(
                tier=tier,
                model_id=model_id,
                model_version=payload.get("model"),
                prompt_name=prompt.name,
                prompt_version=prompt.version,
                decoding=used,
                usage=_usage(payload),
                page_image_count=0,
                response_id=payload.get("id"),
            ),
        )

    def generate_from_pages(
        self,
        *,
        tier: ModelTier,
        prompt: Prompt,
        pages: Sequence[PageImage],
        output: type[T],
        decoding: Decoding | None = None,
    ) -> ModelResult[T]:
        raise NotImplementedError(
            "DeepSeek V4 is text-only; the provider answers 404 'No endpoints found that "
            "support image input'. Vision stages must stay on Gemini."
        )

    def _body(self, prompt: Prompt, output: type[BaseModel], decoding: Decoding,
              tier: ModelTier) -> dict[str, Any]:
        schema = json.dumps(output.model_json_schema(), ensure_ascii=False)
        instruction = (
            f"{prompt.text}\n\n"
            "Return a single JSON object and nothing else — no prose, no code fence. "
            "It must validate against this JSON Schema:\n"
            f"{schema}"
        )
        body: dict[str, Any] = {
            "model": self._model_by_tier[ModelTier.STRONG],  # replaced by caller below
            "messages": [{"role": "user", "content": instruction}],
            "temperature": decoding.temperature,
            "top_p": decoding.top_p,
            "max_tokens": decoding.max_output_tokens,
            "seed": decoding.seed,
            "response_format": {"type": "json_object"},
        }
        if tier not in self._reasoning_tiers:
            body["reasoning"] = {"enabled": False}
        return body

    def _post(self, model_id: str, body: dict[str, Any]) -> dict[str, Any]:
        body = {**body, "model": model_id}
        try:
            response = self._http.post(
                OPENROUTER,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "content-type": "application/json",
                },
                json=body,
            )
        except httpx.RequestError as exc:
            raise ModelTransportError(
                f"could not reach OpenRouter for {model_id}: {exc}"
            ) from exc
        if response.status_code != httpx.codes.OK:
            raise ModelTransportError(
                f"provider returned {response.status_code} for {model_id}: "
                f"{_excerpt(response.text)}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ModelTransportError(
                f"{model_id} returned a non-JSON body: {_excerpt(response.text)}"
            ) from exc
        if "error" in payload:
            raise ModelTransportError(
                f"{model_id} returned an error: {_excerpt(json.dumps(payload['error']))}"
            )
        return payload

    def close(self) -> None:
        if self._owns_http_client:
            self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _usage(payload: dict[str, Any]) -> TokenUsage:
    reported = payload.get("usage") or {}
    details = reported.get("completion_tokens_details") or {}
    return TokenUsage(
        prompt_tokens=reported.get("prompt_tokens"),
        output_tokens=reported.get("completion_tokens"),
        reasoning_tokens=details.get("reasoning_tokens"),
        total_tokens=reported.get("total_tokens"),
    )
