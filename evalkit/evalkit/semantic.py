"""Optional semantic tier — bring-your-own embedding model.

The core scorers are deterministic and dependency-free. Semantic similarity
(catching valid paraphrases that surface metrics miss) needs a model, so it is
kept behind a Protocol: the competition repo wires whatever it already has (a
multilingual sentence-transformer, or an embeddings API) without the core taking
a dependency. When no embedder is supplied, this tier is simply off.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    def similarity(self, a: str, b: str) -> float:
        """Cosine similarity in [0, 1] of two texts' embeddings."""
        ...


def mean_cosine(pairs: list[tuple[str, str]], embedder: Embedder | None) -> float | None:
    """Mean similarity over (hyp, ref) description pairs, or None if no embedder."""
    if embedder is None or not pairs:
        return None
    return sum(embedder.similarity(h, r) for h, r in pairs) / len(pairs)
