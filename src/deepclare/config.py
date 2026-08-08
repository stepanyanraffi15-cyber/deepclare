"""Configuration, read once at startup into a typed object.

Nothing else in the codebase reads the environment. No module reads ambient process
configuration: behaviour switches reach a run as explicit input, so a run is reproducible
from its recorded input alone. This module exists to read the environment exactly once,
at the edge, so everything below receives values rather than fetching them.

**Only a secret is genuinely required.** Everything else has a default that is right for
this repository, because a value the project itself decides — where its own prompts live,
how many workers a crawl uses — is not environment-specific and should not have to be
restated in every deployment. Each default sits here, in one typed place, and every one
can still be overridden by an environment variable when a deployment genuinely differs.

A missing or malformed value fails here, naming itself, rather than halfway through a run.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed view of the configuration. Construct via `load_settings()`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- the only thing that must be supplied -------------------------------
    google_api_key: str = Field(min_length=1)
    """The provider credential. There is no sensible default for a secret."""

    # --- provider ------------------------------------------------------------
    genai_api_base: str = "https://generativelanguage.googleapis.com/v1beta"

    # One model per tier. A stage names a **tier**, never a model id, so changing a model
    # is a configuration change and the trace still records what actually answered.
    genai_model_cheap: str = "gemini-3.5-flash-lite"
    """Page classification, spreadsheet header reading, column labelling."""
    genai_model_standard: str = "gemini-3.6-flash"
    """Vision document reading, evidence, descriptions, chapter and heading narrowing."""
    genai_model_strong: str = "gemini-2.5-pro"
    """The final code pick and its verification — the expert judgement of the product."""

    genai_max_output_tokens: int = Field(default=32768, gt=0)
    """A ceiling that must clear the largest expected answer *plus* the reasoning the
    model spends getting there, which is counted separately: exhausting it truncates the
    answer mid-JSON and the call fails."""

    genai_timeout_seconds: float = Field(default=180.0, gt=0)

    # --- embeddings: locked, not chosen --------------------------------------
    # The vector collection was built with this pairing. A different model or width does
    # not align with those vectors — retrieval would return confident nonsense rather
    # than failing — so overriding either means rebuilding the collection.
    classify_embedding_model: str = "models/gemini-embedding-001"
    classify_embedding_dim: int = Field(default=768, gt=0)

    # --- where things live ---------------------------------------------------
    prompts_dir: Path = REPOSITORY_ROOT / "prompts"
    reference_tables_dir: Path = REPOSITORY_ROOT / "reference_data"
    reference_dir: Path = REPOSITORY_ROOT / "data" / "reference" / "nomenclature_exim"
    reference_snapshot_dir: Path = REPOSITORY_ROOT / "data" / "reference" / "snapshots"
    qdrant_path: Path = REPOSITORY_ROOT / "data" / "qdrant_exim"
    qdrant_collection: str = "atg_aa_codes"

    # --- acquiring the nomenclature ------------------------------------------
    # Enumerated by node id. The paged listing endpoint reports 10,000 rows against an id
    # space past 21,000, so anything built on it silently misses most of the tree.
    nomenclature_api_base: str = "https://exim.src.am/api/govtech"
    nomenclature_max_node_id: int = Field(default=21400, gt=0)
    nomenclature_crawl_workers: int = Field(default=14, gt=0)

    @field_validator("genai_api_base", "nomenclature_api_base")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("prompts_dir", "reference_tables_dir")
    @classmethod
    def _must_be_an_existing_directory(cls, value: Path) -> Path:
        resolved = value.expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError(f"no such directory: {resolved}")
        return resolved


class ConfigurationError(RuntimeError):
    """Raised at startup when the configuration cannot be made valid."""


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Read and validate the configuration once.

    Raises ConfigurationError naming every value that is missing or invalid.
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:  # pydantic ValidationError, or an unreadable .env
        raise ConfigurationError(_explain(exc)) from exc


def _explain(exc: Exception) -> str:
    """Turn a validation failure into a message naming the variables at fault."""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return f"Configuration could not be loaded: {exc}"

    lines = ["Configuration is invalid. Fix these in .env:"]
    for error in errors():
        variable = ".".join(str(part) for part in error["loc"]).upper()
        lines.append(f"  {variable}: {error['msg']}")
    lines.append("")
    lines.append("Only GOOGLE_API_KEY has to be set; everything else has a default.")
    lines.append("Start from the shipped template:  cp .env.example .env")
    return "\n".join(lines)
