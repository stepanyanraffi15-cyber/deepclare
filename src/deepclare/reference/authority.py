"""Acquiring the commodity nomenclature from the government open-data API.

Part of M3 (Reference Data Build). It knows how to obtain nodes and nothing about who
wants them.

THE ACQUISITION HAZARD, which decides the shape of this whole module:

The API's paged listing endpoint **silently caps**. Measured against the live service:
it reports `totalRoots = 10000` no matter what filters are applied, against an id space
extending past 21,000. Nothing errors, nothing warns — a build on the listing endpoint
simply omits most of the tree, and every classification afterwards searches a
nomenclature with holes in it.

The only complete route is enumerating node ids. Gaps in the id space answer 404 and are
ordinary; a transient failure is retried with exponential backoff; and an id still
unresolved after its retries **fails the entire acquisition**. A half-acquired tree that
returns successfully is worse than none, because nothing downstream can tell it apart
from a whole one.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

RETRY_ATTEMPTS = 3
INITIAL_BACKOFF_SECONDS = 1.0
KEPT_FIELDS = ("id", "parentId", "code", "name", "nameEn", "nameRu", "type", "unit")
"""What the snapshot retains. `formula` and `isMrp` are served but their meaning is
undetermined, so they are not carried into anything that reads like knowledge."""


class PartialAcquisitionError(RuntimeError):
    """Some ids could not be settled as either present or absent. Deliberately fatal."""


def acquire_tree(
    *,
    api_base: str,
    max_node_id: int,
    workers: int,
    snapshot: Path,
    reacquire: bool = False,
) -> list[dict]:
    """Return every node the authority serves, reusing a snapshot when one exists.

    Snapshots are retained so that re-deriving the tree — which happens whenever the
    shape of the entries changes — never re-acquires it.
    """
    if snapshot.exists() and not reacquire:
        nodes = _read_snapshot(snapshot)
        logger.info("reusing snapshot of %d nodes from %s", len(nodes), snapshot)
        return nodes

    logger.info(
        "enumerating node ids 1..%d at %s with %d workers "
        "(the paged listing endpoint silently caps and is never used)",
        max_node_id, api_base, workers,
    )
    nodes, gaps, failures = _enumerate(api_base, max_node_id, workers)

    if failures:
        shown = ", ".join(f"id={i} ({e})" for i, e in failures[:5])
        raise PartialAcquisitionError(
            f"{len(failures)} of {max_node_id} ids unresolved after {RETRY_ATTEMPTS} "
            f"retries; refusing to return a partial tree. First failures: {shown}"
        )

    _write_snapshot(snapshot, nodes)
    logger.info("acquired %d nodes (%d id gaps, 0 failures)", len(nodes), gaps)
    return nodes


def _enumerate(
    api_base: str, max_node_id: int, workers: int
) -> tuple[list[dict], int, list[tuple[int, str]]]:
    nodes: list[dict] = []
    failures: list[tuple[int, str]] = []
    gaps = 0

    limits = httpx.Limits(max_connections=workers, max_keepalive_connections=workers)
    with httpx.Client(timeout=25.0, limits=limits) as client:
        fetch = lambda node_id: _fetch(client, api_base, node_id)  # noqa: E731
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for scanned, (node_id, node, error) in enumerate(
                pool.map(fetch, range(1, max_node_id + 1)), 1
            ):
                if error is not None:
                    failures.append((node_id, error))
                elif node is None:
                    gaps += 1
                else:
                    nodes.append(node)
                if scanned % 3000 == 0:
                    logger.info(
                        "  %d/%d scanned, %d nodes, %d gaps",
                        scanned, max_node_id, len(nodes), gaps,
                    )
    return nodes, gaps, failures


def _fetch(
    client: httpx.Client, api_base: str, node_id: int
) -> tuple[int, dict | None, str | None]:
    """Fetch one node. Both node and error None means the id is a gap, which is normal."""
    url = f"{api_base}/codes/{node_id}"
    backoff = INITIAL_BACKOFF_SECONDS
    last_error = ""

    for attempt in range(RETRY_ATTEMPTS + 1):
        try:
            response = client.get(url)
            if response.status_code == 404:
                return node_id, None, None
            response.raise_for_status()
            payload = response.json()
            return node_id, {k: payload.get(k) for k in KEPT_FIELDS}, None
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < RETRY_ATTEMPTS:
                time.sleep(backoff)
                backoff *= 2

    return node_id, None, last_error


def _read_snapshot(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_snapshot(path: Path, nodes: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for node in nodes:
            handle.write(json.dumps(node, ensure_ascii=False) + "\n")
