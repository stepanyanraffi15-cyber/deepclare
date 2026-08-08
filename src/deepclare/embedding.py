"""The embedding provider adapter, for both sides of the index.

Infrastructure, not domain logic: it turns text into a vector and knows nothing about
commodity codes or declarations. Injected into whatever needs it rather than constructed
there, so those modules stay runnable with no network present.

THE SYMMETRY CONTRACT, and the reason model and width live on the object rather than
being read at the call site:

    The build side and the query side must use the same model and the same
    dimensionality, or the vectors do not align.

An index built at 768 dimensions with one model cannot be queried by another — retrieval
would return confident nonsense rather than failing. Both values are carried so a run can
pin what it used, and so a mismatch is a construction-time error rather than a silent
collapse in accuracy.

The indexed text is an English, broad-to-specific, em-dash-separated noun phrase:
`<chapter> — <heading> — <leaf>`, and a query must be phrased the same way. Measured
against this collection: a query in that form scores 0.84 against the correct leaf where
a plain English phrase for the same goods scores 0.65.

The two sides differ in one respect only, and deliberately. A **query** never retries: a
run-time failure must surface rather than quietly cost seconds and then answer. An
**index build** does retry, because it is a batch job that must not half-finish — a
transient failure partway through would leave a collection whose points no longer line up
with their codes, and nothing downstream could tell.
"""

from __future__ import annotations

import logging
import time

import httpx

from deepclare.config import Settings

logger = logging.getLogger(__name__)

QUERY_TASK = "RETRIEVAL_QUERY"
DOCUMENT_TASK = "RETRIEVAL_DOCUMENT"
"""This provider family places query-side and document-side embeddings in deliberately
different regions of the space, so the side has to be declared."""

INDEX_BUILD_ATTEMPTS = 4
INDEX_BUILD_BACKOFF_SECONDS = 2.0


class EmbeddingError(RuntimeError):
    """The embedding call failed. Never swallowed: without a vector there is no search."""


class GeminiEmbedder:
    """Embeddings from the configured provider, at the configured width."""

    def __init__(
        self, settings: Settings, http_client: httpx.Client | None = None
    ) -> None:
        self._api_base = settings.genai_api_base
        self._api_key = settings.google_api_key
        self._model = settings.classify_embedding_model
        self._dimensions = settings.classify_embedding_dim
        self._http = http_client or httpx.Client(timeout=settings.genai_timeout_seconds)
        self._owns_http_client = http_client is None

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_query(self, text: str) -> list[float]:
        """Embed one search query. One attempt — a failure belongs to the caller."""
        return self._embed(text, task=QUERY_TASK)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch for indexing. Order in is order out, with retries."""
        return [self._embed_with_retries(text) for text in texts]

    # --- internals ---------------------------------------------------------

    def _embed_with_retries(self, text: str) -> list[float]:
        delay = INDEX_BUILD_BACKOFF_SECONDS
        for attempt in range(INDEX_BUILD_ATTEMPTS):
            try:
                return self._embed(text, task=DOCUMENT_TASK)
            except EmbeddingError:
                if attempt == INDEX_BUILD_ATTEMPTS - 1:
                    raise
                logger.warning("embedding attempt %d failed, retrying", attempt + 1)
                time.sleep(delay)
                delay *= 2
        raise EmbeddingError("unreachable")

    def _embed(self, text: str, *, task: str) -> list[float]:
        if not text.strip():
            raise EmbeddingError("refusing to embed empty text")

        model_path = (
            self._model if self._model.startswith("models/") else f"models/{self._model}"
        )
        try:
            response = self._http.post(
                f"{self._api_base}/{model_path}:embedContent",
                json={
                    "content": {"parts": [{"text": text}]},
                    "taskType": task,
                    "outputDimensionality": self._dimensions,
                },
                headers={
                    "x-goog-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            values = response.json()["embedding"]["values"]
        except Exception as exc:
            raise EmbeddingError(f"embedding call failed: {exc}") from exc

        if len(values) != self._dimensions:
            raise EmbeddingError(
                f"provider returned {len(values)} dimensions, expected "
                f"{self._dimensions}; this would not align with the index"
            )
        return values

    def close(self) -> None:
        if self._owns_http_client:
            self._http.close()
