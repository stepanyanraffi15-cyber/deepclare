"""Building the vector collection from the tree — the half a checkout cannot contain.

Part of M3 (Reference Data Build). The metadata artifact is rebuildable from the
authority in minutes and costs nothing; the vectors are 14,332 embedding calls, so they
are normally copied rather than rebuilt. This exists so that a clone with neither can
reach a working state without anyone hand-carrying a 113 MB file.

THE SYMMETRY CONTRACT — the reason this module and the query side must be read together:

The text embedded here and the text a search is phrased in have to be the same shape, or
the two land in different regions of the space and retrieval quietly degrades. The shape
is an English, broad-to-specific, em-dash-separated noun phrase:

    <chapter text> — <heading text> — <leaf text>

Leaf names are elliptical — roughly three in ten are literally "other" — so the chapter
and heading are prepended to anchor them. Measured against the collection built this way:
a query in this form scores 0.84 against the correct leaf where a plain English phrase
for the same goods scores 0.65.

Change this function and every vector is invalid. That is not a figure of speech: the
collection must be rebuilt, and until it is, every search is comparing against text that
no longer exists.
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from deepclare.reference.tree import TreeEntry

logger = logging.getLogger(__name__)

EMBED_BATCH = 100
LEAF_LEVEL = 5
VECTOR_DISTANCE = "Cosine"


def embedding_text(entry: TreeEntry, chapter: str, heading: str) -> str:
    """The canonical indexed form. The query side must mirror this exactly."""
    leaf = entry.name_en or entry.name_hy or entry.name_ru or entry.code
    parts = [p.strip().rstrip(":").strip() for p in (chapter, heading, leaf) if p]
    return " — ".join(dict.fromkeys(parts))


def payload_for(entry: TreeEntry) -> dict[str, object]:
    """What a point carries besides its vector.

    The prefixes are separate fields so a search can be scoped inside the store rather
    than by filtering results after the fact. The names and paths are here so that a
    retrieved code arrives already meaning something, without a second lookup.
    """
    code = entry.code
    payload: dict[str, object] = {
        "code": code,
        "level": entry.level,
        "p2": code[:2],
        "p4": code[:4],
        "p6": code[:6],
        "p8": code[:8],
    }
    for language in ("en", "hy", "ru"):
        if name := getattr(entry, f"name_{language}", None):
            payload[f"name_{language}"] = name
    for language in ("en", "hy"):
        if path := entry.path(language):
            payload[f"path_{language}"] = path
    if entry.supplementary_unit:
        payload["supplementary_unit"] = entry.supplementary_unit
    return payload


def build_index(
    *,
    entries: Sequence[TreeEntry],
    embed_documents: "EmbedBatch",
    qdrant_client: object,
    collection: str,
    dimensions: int,
    recreate: bool = False,
) -> int:
    """Embed every entry and write the collection. Returns the number of points.

    `embed_documents` takes a batch of strings and returns their vectors, in order. It
    is a parameter so this module holds no provider knowledge and can be exercised
    without one.
    """
    from qdrant_client import models as qmodels

    by_code = {entry.code: entry for entry in entries}

    def title(code: str) -> str:
        found = by_code.get(code)
        return (found.name_en or found.name_hy or "") if found else ""

    texts = [
        embedding_text(entry, title(entry.code[:2]), title(entry.code[:4]))
        for entry in entries
    ]

    if recreate:
        qdrant_client.recreate_collection(  # type: ignore[attr-defined]
            collection_name=collection,
            vectors_config=qmodels.VectorParams(
                size=dimensions, distance=qmodels.Distance.COSINE
            ),
        )
        logger.info("recreated collection %s at %d dimensions", collection, dimensions)

    written = 0
    for start in range(0, len(entries), EMBED_BATCH):
        chunk = entries[start : start + EMBED_BATCH]
        vectors = embed_documents(texts[start : start + EMBED_BATCH])
        if len(vectors) != len(chunk):
            raise RuntimeError(
                f"embedder returned {len(vectors)} vectors for {len(chunk)} entries; "
                f"refusing to write a collection whose points may be misaligned"
            )
        qdrant_client.upsert(  # type: ignore[attr-defined]
            collection_name=collection,
            points=[
                qmodels.PointStruct(
                    id=start + offset,
                    vector=vector,
                    payload=payload_for(entry),
                )
                for offset, (entry, vector) in enumerate(zip(chunk, vectors))
            ],
            wait=True,
        )
        written += len(chunk)
        if written % 2000 < EMBED_BATCH:
            logger.info("embedded %d/%d entries", written, len(entries))

    logger.info("collection %s built: %d points", collection, written)
    return written


class EmbedBatch:
    """Structural type for the callable `build_index` takes. Any function of
    `list[str] -> list[list[float]]` satisfies it."""

    def __call__(self, texts: Iterable[str]) -> list[list[float]]:  # pragma: no cover
        raise NotImplementedError
