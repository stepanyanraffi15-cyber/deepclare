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

    # One model id per tier. A stage names a tier and never a model id, so swapping a
    # model is a configuration change and the trace can pin what actually answered.
    genai_model_cheap: str = Field(min_length=1)
    genai_model_standard: str = Field(min_length=1)
    genai_model_strong: str = Field(min_length=1)

    # A hard ceiling on generated tokens. It must clear the largest expected answer plus
    # whatever the model spends on reasoning, which is billed and counted separately:
    # exhausting it truncates the answer mid-JSON and the call fails.
    genai_max_output_tokens: int = Field(gt=0)
    genai_timeout_seconds: float = Field(gt=0)

    # --- prompts ------------------------------------------------------------
    prompts_dir: Path

    # --- reference data -----------------------------------------------------
    # The vector collection and the tree that gives its codes meaning. Both are large
    # derived objects no checkout reproduces, so their absence must be a startup
    # failure rather than a runtime where every classification quietly returns nothing.
    qdrant_path: Path
    qdrant_collection: str = Field(min_length=1)
    reference_dir: Path
    reference_snapshot_dir: Path

    # The authority the tree is acquired from. Enumerated by node id: the paged listing
    # endpoint silently caps at 10,000 rows against an id space past 21,000, so anything
    # built on it is missing most of the tree with no error anywhere.
    nomenclature_api_base: str = Field(min_length=1)
    nomenclature_max_node_id: int = Field(gt=0)
    nomenclature_crawl_workers: int = Field(gt=0)

    @field_validator("genai_api_base", "nomenclature_api_base")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("prompts_dir")
    @classmethod
    def _must_be_an_existing_directory(cls, value: Path) -> Path:
        resolved = value.expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError(f"no such directory: {resolved}")
        return resolved


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
