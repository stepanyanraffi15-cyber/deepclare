"""Publish the built tree: an entries artifact, and enriched payloads on the vectors.

Part of M3 (Reference Data Build).

The vector collection stores one point per filable code, and its payload previously held
the code and its digit prefixes and nothing else — no names in any language, no
supplementary unit, no ancestry. Retrieval could therefore say *which* codes resemble a
description but nothing about *what they are*, which is what the choosing and abstaining
steps actually read.

This writes that text onto the points that already exist. **Vectors are never touched**:
payload and vector are independent, so nothing here changes what the index retrieves or
invalidates the model-and-dimensionality pairing the vectors were built under. It is
reversible by clearing the added keys.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from qdrant_client import QdrantClient

from deepclare.reference.tree import TreeEntry

logger = logging.getLogger(__name__)

LANGUAGES = ("en", "hy", "ru")
PAYLOAD_BATCH = 256

ADDED_PAYLOAD_KEYS = (
    "name_en", "name_hy", "name_ru",
    "path_en", "path_hy", "path_ru",
    "supplementary_unit",
)
"""Everything this module adds. Listed so the change can be undone precisely."""


def write_entries(directory: Path, entries: list[TreeEntry]) -> Path:
    """Write the entries artifact, ancestry included, as JSON lines."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "entries.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(entry.model_dump_json(exclude_none=True) + "\n")
    logger.info("wrote %d entries to %s", len(entries), path)
    return path


def enrich_collection(
    client: QdrantClient, collection: str, entries: list[TreeEntry]
) -> tuple[int, int]:
    """Attach names, taxonomic paths and units to the points already in the collection.

    Returns (points updated, points whose code has no entry). A non-zero second number
    means the vectors and the tree disagree and one of them is stale.
    """
    by_code = {entry.code: entry for entry in entries}

    updated = 0
    unmatched = 0
    batch: list[tuple[int | str, dict[str, str]]] = []
    offset = None

    while True:
        points, offset = client.scroll(
            collection, limit=1024, offset=offset, with_payload=True, with_vectors=False
        )
        for point in points:
            entry = by_code.get(str(point.payload.get("code", "")))
            if entry is None:
                unmatched += 1
                continue
            batch.append((point.id, _payload_for(entry)))
            if len(batch) >= PAYLOAD_BATCH:
                updated += _flush(client, collection, batch)
                batch = []
        if offset is None:
            break

    updated += _flush(client, collection, batch)
    logger.info("enriched %d points; %d had no matching entry", updated, unmatched)
    return updated, unmatched


def _payload_for(entry: TreeEntry) -> dict[str, str]:
    """The text one point gains. Absent values are omitted rather than stored empty."""
    payload: dict[str, str] = {}
    for language in LANGUAGES:
        if name := getattr(entry, f"name_{language}"):
            payload[f"name_{language}"] = name
        if path := entry.path(language):
            payload[f"path_{language}"] = path
    if entry.supplementary_unit:
        payload["supplementary_unit"] = entry.supplementary_unit
    return payload


def _flush(
    client: QdrantClient, collection: str, batch: list[tuple[int | str, dict[str, str]]]
) -> int:
    """Points differ in which keys they carry, so each is set individually."""
    for point_id, payload in batch:
        client.set_payload(collection, payload=payload, points=[point_id], wait=True)
    return len(batch)


def load_nodes(path: Path) -> list[dict]:
    """Read an acquisition snapshot. Kept so re-deriving never re-acquires."""
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
