"""The adapter that calls the generative provider.

Infrastructure, and only that. It knows how to send a prompt and hand back an object of
the shape the caller asked for. It knows nothing about declarations, goods lines,
commodity codes or any other domain concept, and nothing here may learn about them.

Three rules shape this module and none of them is a preference:

**No retry and no repair loop.** Every run-time model edge translates the first exception
into its stage's own error type and stops. There is no second attempt, no backoff, no
re-prompt on invalid output. A wrong value on a legal document is worse than a missing
one, and a re-prompt after a bad answer is a machine talking itself into an answer. Retry
belongs only to offline batch work, which must not half-finish; nothing on the run path
is offline batch work.

**Every decoding parameter is pinned and recorded.** Nothing is left to a provider
default, because a default is invisible, can change between provider releases, and no
measurement taken against one is reproducible. What was sent travels back on the result
so a run can say what produced a value.

**Prompts are files, never strings built in Python.** A prompt assembled at a call site
cannot be versioned, diffed, or named in the provenance of the value it wrote. The
client's signature enforces this: it accepts a rendered `Prompt`, not text.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from enum import StrEnum
from types import TracebackType
from typing import Any, Generic, Literal, Self, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from deepclare.config import Settings
from deepclare.prompting import Prompt


class ModelTier(StrEnum):
    """What a stage asks for. The model id behind each tier is configuration.

    The tiers are task shapes, not sizes: a boolean or label-emitting call needs no
    reasoning capacity, while a material or legal distinction does. Choosing the tier is
    the stage's decision; choosing the model that serves it is not.
    """

    CHEAP = "cheap"
    """Label-emitting calls: page classification, header reads, column labelling."""

    STANDARD = "standard"
    """Reading and writing calls: vision extraction, enrichment, description, narrowing,
    harmonization."""

    STRONG = "strong"
    """Calls that turn on a material or legal distinction: the final code pick, and
    verification."""


class ModelError(RuntimeError):
    """Base for every failure of a generative call.

    Stages catch this and translate it into their own error type. Nothing catches it to
    try again.
    """


class ModelTransportError(ModelError):
    """The provider could not be reached, or did not answer with the API's envelope."""


class ModelRefusedError(ModelError):
    """The provider answered but produced no usable content.

    Blocked, filtered, or stopped early against the output-token ceiling. Distinct from
    a malformed answer: nothing was said, so there is nothing to parse.
    """


class ModelOutputError(ModelError):
    """The provider said something that is not the shape that was requested.

    Raised instead of returning a dict, an untyped object, or a partially-populated one.
    """


class Decoding(BaseModel):
    """Every decoding parameter the provider accepts, each pinned to an explicit value.

    Nothing is omitted so as to inherit a provider default. The candidate count is fixed
    at one because the client returns exactly one object; it is not a knob.
    """

    model_config = ConfigDict(frozen=True)

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    top_k: int = Field(default=1, ge=1)
    candidate_count: Literal[1] = 1
    max_output_tokens: int = Field(gt=0)
    seed: int = Field(default=1, ge=1)
    """Fixed rather than meaningful: the value is arbitrary, holding it constant
    is not."""


class PageImage(BaseModel):
    """One rendered page, sent inline with the prompt.

    The caller rasterizes; this module encodes. Bytes rather than a path because the
    client never touches the filesystem for content.
    """

    model_config = ConfigDict(frozen=True)

    media_type: str = Field(min_length=1, description="e.g. 'image/png'")
    content: bytes = Field(min_length=1)


class TokenUsage(BaseModel):
    """What the call cost, as the provider reported it.

    Every field is optional because the provider reports usage as a courtesy, not as a
    guarantee. Reasoning tokens are counted separately from output tokens and are billed;
    a call whose reasoning dwarfs its answer is the signal that a tier is mismatched to
    the task.
    """

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None


class ModelCall(BaseModel):
    """The account of one call: what was asked, of what, under which settings, at what
    cost.

    This is what lets a run report what produced a value. `model_id` is what was
    requested and `model_version` is what the provider says served it; they can differ
    when an id points at a moving alias.
    """

    # The provider's own word for this is "model"; these names shadow nothing on
    # BaseModel, so the namespace guard is switched off rather than the fields renamed.
    model_config = ConfigDict(frozen=True, protected_namespaces=())

    tier: ModelTier
    model_id: str
    model_version: str | None = None
    prompt_name: str
    prompt_version: str
    decoding: Decoding
    usage: TokenUsage
    page_image_count: int = Field(default=0, ge=0)
    response_id: str | None = None


T = TypeVar("T", bound=BaseModel)


class ModelResult(BaseModel, Generic[T]):
    """A validated object and the account of the call that produced it."""

    model_config = ConfigDict(frozen=True)

    value: T
    call: ModelCall


class GenerativeModel:
    """Sends prompts to the provider and returns validated objects.

    One instance per process is enough; it holds the HTTP connection pool. Construct
    it from settings and pass it to the stages that need it — it reads no environment
    of its own.
    """

    def __init__(
        self, settings: Settings, http_client: httpx.Client | None = None
    ) -> None:
        self._api_base = settings.genai_api_base
        self._api_key = settings.google_api_key
        self._model_by_tier = {
            ModelTier.CHEAP: settings.genai_model_cheap,
            ModelTier.STANDARD: settings.genai_model_standard,
            ModelTier.STRONG: settings.genai_model_strong,
        }
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
        """Send text and return an instance of `output`, or raise."""
        return self._call(
            tier=tier, prompt=prompt, pages=(), output=output, decoding=decoding
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
        """Send page images with the text and return an instance of `output`, or raise."""
        if not pages:
            raise ValueError("generate_from_pages needs at least one page image")
        return self._call(
            tier=tier, prompt=prompt, pages=pages, output=output, decoding=decoding
        )

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

    def _call(
        self,
        *,
        tier: ModelTier,
        prompt: Prompt,
        pages: Sequence[PageImage],
        output: type[T],
        decoding: Decoding | None,
    ) -> ModelResult[T]:
        model_id = self._model_by_tier[tier]
        decoding_used = decoding or self._decoding
        payload = self._post(
            model_id,
            _request_body(
                prompt=prompt, pages=pages, output=output, decoding=decoding_used
            ),
        )
        text = _answer_text(payload, model_id)
        value = _validate(text, output, model_id)
        return ModelResult[output](
            value=value,
            call=ModelCall(
                tier=tier,
                model_id=model_id,
                model_version=payload.get("modelVersion"),
                prompt_name=prompt.name,
                prompt_version=prompt.version,
                decoding=decoding_used,
                usage=_usage(payload),
                page_image_count=len(pages),
                response_id=payload.get("responseId"),
            ),
        )

    def _post(self, model_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """One request. Any failure raises; nothing here tries a second time.

        The key travels in a header rather than the query string so it cannot end up in a
        proxy log or an exception's URL.
        """
        try:
            response = self._http.post(
                f"{self._api_base}/models/{model_id}:generateContent",
                headers={
                    "x-goog-api-key": self._api_key,
                    "content-type": "application/json",
                },
                json=body,
            )
        except httpx.RequestError as exc:
            raise ModelTransportError(
                f"could not reach the provider for {model_id}: {exc}"
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
                f"provider returned a non-JSON body for {model_id}: "
                f"{_excerpt(response.text)}"
            ) from exc
        if not isinstance(payload, dict):
            raise ModelTransportError(
                f"provider returned {type(payload).__name__} rather than a response "
                f"object for {model_id}"
            )
        return payload


def _request_body(
    *,
    prompt: Prompt,
    pages: Sequence[PageImage],
    output: type[BaseModel],
    decoding: Decoding,
) -> dict[str, Any]:
    """Images precede the instruction: a model reads a page better when the page came
    first.
    """
    parts: list[dict[str, Any]] = [
        {
            "inline_data": {
                "mime_type": page.media_type,
                "data": base64.b64encode(page.content).decode("ascii"),
            }
        }
        for page in pages
    ]
    parts.append({"text": prompt.text})
    return {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": decoding.temperature,
            "topP": decoding.top_p,
            "topK": decoding.top_k,
            "candidateCount": decoding.candidate_count,
            "maxOutputTokens": decoding.max_output_tokens,
            "seed": decoding.seed,
            "responseMimeType": "application/json",
            "responseJsonSchema": output.model_json_schema(),
        },
    }


def _answer_text(payload: dict[str, Any], model_id: str) -> str:
    """The model's answer, or a named error saying why there is none."""
    block_reason = (payload.get("promptFeedback") or {}).get("blockReason")
    if block_reason:
        raise ModelRefusedError(f"{model_id} refused the prompt: {block_reason}")

    candidates = payload.get("candidates") or []
    if not candidates:
        raise ModelRefusedError(f"{model_id} returned no candidates")

    candidate = candidates[0]
    finish_reason = candidate.get("finishReason") or "unset"
    parts = (candidate.get("content") or {}).get("parts") or []
    # A reasoning model returns its private thinking as parts flagged `thought`; those
    # are not the answer and must not be concatenated into it.
    spoken = [
        part["text"] for part in parts if "text" in part and not part.get("thought")
    ]

    if finish_reason != "STOP":
        raise ModelRefusedError(
            f"{model_id} stopped with finishReason={finish_reason}; the answer is "
            f"incomplete and is not being parsed"
        )
    if not spoken:
        raise ModelRefusedError(f"{model_id} returned no text")
    return "".join(spoken)


def _validate(text: str, output: type[T], model_id: str) -> T:
    """Parse and validate, or raise. A dict never leaves this function."""
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise ModelOutputError(
            f"{model_id} returned text that is not JSON: {_excerpt(text)}"
        ) from exc
    try:
        return output.model_validate(parsed)
    except ValidationError as exc:
        raise ModelOutputError(
            f"{model_id} returned JSON that is not a valid {output.__name__}: {exc}"
        ) from exc


def _usage(payload: dict[str, Any]) -> TokenUsage:
    reported = payload.get("usageMetadata") or {}
    return TokenUsage(
        prompt_tokens=reported.get("promptTokenCount"),
        output_tokens=reported.get("candidatesTokenCount"),
        reasoning_tokens=reported.get("thoughtsTokenCount"),
        total_tokens=reported.get("totalTokenCount"),
    )


def _excerpt(text: str, limit: int = 400) -> str:
    """Bound what a provider body can add to an exception message."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[:limit]}…"
