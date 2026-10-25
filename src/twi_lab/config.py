"""
Configuration management for the Twi Translation Benchmark Lab.

Uses pydantic-settings to load typed configurations from environment variables
and an optional .env file, providing sensible defaults for local development.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings with environment variable support and validation."""

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Repository base directory (defaults to the root of the workspace)
    base_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent,
        description="Absolute path to the project root directory.",
    )

    # Runtime environment
    project_env: Literal["development", "testing", "production"] = Field(
        default="development",
        description="Current deployment or execution environment.",
    )

    # Structured logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )

    # Benchmark dataset paths
    dataset_path: Path = Field(
        default=Path("data/samples/passages.jsonl"),
        description="Path to the sample passages JSONL dataset.",
    )
    manifest_path: Path = Field(
        default=Path("data/samples/manifest.json"),
        description="Path to the dataset manifest JSON.",
    )
    results_dir: Path = Field(
        default=Path("results"),
        description="Directory where benchmark experiment results are stored.",
    )
    logs_dir: Path = Field(
        default=Path("logs"),
        description="Directory where application log files are stored.",
    )

    # Phase 3: Context and Cache paths and limits
    cache_path: Path = Field(
        default=Path("data/cache/translation_cache.json"),
        description="Path to the persistent translation cache JSON file.",
    )
    summaries_path: Path = Field(
        default=Path("data/samples/summaries.json"),
        description="Path to story summaries JSON file.",
    )
    glossary_path: Path = Field(
        default=Path("data/samples/glossary.json"),
        description="Path to approved glossary JSON file.",
    )
    khaya_call_budget: int = Field(
        default=10,
        description="Default maximum allowed live Khaya API calls per experiment run.",
    )

    # Phase 2: Khaya Translation API configuration
    khaya_api_key: Optional[str] = Field(
        default=None,
        description="API Key for Khaya / GhanaNLP translation service (Phase 2).",
    )
    khaya_api_secondary_key: Optional[str] = Field(
        default=None,
        description="Secondary/backup API key for Khaya / GhanaNLP automatic failover.",
    )
    khaya_api_base_url: str = Field(
        default="https://translation-api.ghananlp.org/v1",
        description="Base URL for Khaya / GhanaNLP translation API endpoints.",
    )
    khaya_timeout_seconds: float = Field(
        default=30.0,
        description="HTTP request timeout for Khaya API calls in seconds.",
    )

    # Phase 2: Local OPUS-MT configuration (placeholders for Phase 1)
    opus_mt_model_name: str = Field(
        default="Helsinki-NLP/opus-mt-en-tw",
        description="Hugging Face model identifier for local OPUS-MT.",
    )
    opus_mt_model_dir: Path = Field(
        default=Path("models/opus-mt-en-tw"),
        description="Local directory for cached OPUS-MT model weights.",
    )
    local_device: str = Field(
        default="cpu",
        description="Target compute device for local inference (cpu/cuda).",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        val_upper = value.upper()
        if val_upper not in valid:
            raise ValueError(
                f"Invalid log_level '{value}'. Must be one of {sorted(valid)}"
            )
        return val_upper

    def resolve_path(self, path: Path | str) -> Path:
        """Resolves a path relative to base_dir if it is not already absolute."""
        p = Path(path)
        if p.is_absolute():
            return p
        return (self.base_dir / p).resolve()

    @property
    def resolved_dataset_path(self) -> Path:
        return self.resolve_path(self.dataset_path)

    @property
    def resolved_manifest_path(self) -> Path:
        return self.resolve_path(self.manifest_path)

    @property
    def resolved_results_dir(self) -> Path:
        return self.resolve_path(self.results_dir)

    @property
    def resolved_logs_dir(self) -> Path:
        return self.resolve_path(self.logs_dir)

    @property
    def resolved_cache_path(self) -> Path:
        return self.resolve_path(self.cache_path)

    @property
    def resolved_summaries_path(self) -> Path:
        return self.resolve_path(self.summaries_path)

    @property
    def resolved_glossary_path(self) -> Path:
        return self.resolve_path(self.glossary_path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns a cached singleton Settings instance."""
    return Settings()
