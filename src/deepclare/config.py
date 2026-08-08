"""Environment-specific configuration, read once at startup into a typed object.

Nothing else in the codebase reads the environment. Per dossier 10 §4 invariant 2, no
module reads ambient process configuration: behaviour switches reach a run as explicit
input. This module exists to load the environment exactly once, at the edge, so that
everything below it receives values rather than fetching them.

A missing or malformed required variable fails here, naming itself, rather than halfway
through a run.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view of the environment. Construct via `load_settings()`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- model provider -----------------------------------------------------
    google_api_key: str = Field(min_length=1)
    genai_api_base: str = Field(min_length=1)

    # --- embeddings: the symmetry contract ----------------------------------
    # Dossier 11 §2: build side and query side must use the same model and the same
    # dimensionality or the vectors do not align. These are configuration so that a run
    # can pin what it actually used.
    classify_embedding_model: str = Field(min_length=1)
    classify_embedding_dim: int = Field(gt=0)
    embedding_text_structure: str = Field(min_length=1)

    # --- vector store -------------------------------------------------------
    qdrant_path: Path
    qdrant_collection: str = Field(min_length=1)

    # --- reference data -----------------------------------------------------
    nomenclature_artifact_path: Path
    nomenclature_snapshot_path: Path
    nomenclature_api_base: str = Field(min_length=1)
    nomenclature_crawl_max_id: int = Field(gt=0)
    nomenclature_crawl_workers: int = Field(gt=0)
    nomenclature_crawl_timeout_seconds: float = Field(gt=0)
    nomenclature_expected_leaf_count: int = Field(gt=0)
    nomenclature_leaf_count_tolerance: int = Field(ge=0)

    @field_validator("genai_api_base", "nomenclature_api_base")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")


class ConfigurationError(RuntimeError):
    """Raised at startup when the environment cannot produce valid settings."""


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Read and validate the environment once.

    Raises ConfigurationError naming every variable that is missing or invalid.
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:  # pydantic ValidationError, or a bad .env
        raise ConfigurationError(_explain(exc)) from exc


def _explain(exc: Exception) -> str:
    """Turn a validation failure into a message that names the variables at fault."""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return f"Configuration could not be loaded: {exc}"

    lines = ["Configuration is incomplete or invalid. Fix these in .env:"]
    for error in errors():
        variable = ".".join(str(part) for part in error["loc"]).upper()
        lines.append(f"  {variable}: {error['msg']}")
    lines.append("")
    lines.append("Start from the shipped template:  cp .env.example .env")
    return "\n".join(lines)
