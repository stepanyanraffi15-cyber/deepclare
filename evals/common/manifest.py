"""What a result set has to carry to be reproducible.

A scorecard without provenance is an anecdote. Every eval run writes one of
these next to its results so a number can be traced back to the code, the
models, the data vintage and the feature flags that produced it.
"""

from __future__ import annotations

import json
import pathlib
import platform
import subprocess
import time
from typing import Any


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - provenance is best-effort, never fatal
        return "unknown"


def build(
    *,
    eval_name: str,
    provider: str,
    models: dict[str, str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "eval": eval_name,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "provider": provider,
        "models": models,
        **(extra or {}),
    }


def write(path: pathlib.Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
