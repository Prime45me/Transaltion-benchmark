"""
Data contracts and validation schemas for the Twi Translation Benchmark Lab.

Defines schemas for:
- BenchmarkPassage: Individual story passages and linguistic test fixtures.
- DatasetManifest: Provenance and coverage metadata for the benchmark dataset.
- TranslationResult: Standardized contract for Phase 2 translation engine outputs.
- ExperimentRun: Metadata and tracking for repeatable benchmark experiments.
- ValidationReport: Detailed error and status report from dataset validation.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LinguisticCategory(str, Enum):
    """
    Target linguistic phenomena and evaluation categories for children's stories.
    Covers core translation challenges from simple morphology to long-range narrative coherence.
    """

    SIMPLE_SENTENCE = "simple_sentence"
    PRONOUNS_CHARACTER_REF = "pronouns_character_ref"
    DIALOGUE = "dialogue"
    MULTIPLE_CHARACTERS = "multiple_characters"
    EVENT_ORDER_TENSE = "event_order_tense"
    CAUSE_AND_EFFECT = "cause_and_effect"
    AMBIGUOUS_REFERENCE = "ambiguous_reference"
    IDIOMS_FIGURATIVE = "idioms_figurative"
    CULTURAL_CONTEXT = "cultural_context"
    CHARACTER_NAME_CONSISTENCY = "character_name_consistency"
    DESCRIPTIONS_RELATIONSHIPS = "descriptions_relationships"
    CHILD_FRIENDLY_VOCABULARY = "child_friendly_vocabulary"
    QUESTIONS_AND_COMMANDS = "questions_and_commands"
    NEGATION = "negation"
    LONG_RANGE_CONTEXT = "long_range_context"
    COMPLETENESS_BOUNDARIES = "completeness_boundaries"


class ReferenceStatus(str, Enum):
    """Status of the human reference translation."""

    ABSENT = "absent"
    DRAFTED = "drafted"
    HUMAN_REVIEWED = "human_reviewed"


class ReviewStatus(str, Enum):
    """Review state of a benchmark passage within the lab."""

    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class TranslationStatus(str, Enum):
    """Outcome status of an engine translation request."""

    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    TIMEOUT = "timeout"


class ExperimentStatus(str, Enum):
    """Lifecycle status of a translation experiment run."""

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]+$")


class BenchmarkPassage(BaseModel):
    """
    Individual benchmark passage record.

    Represents a discrete English source segment with surrounding context,
    linguistic test categorization, and optional human-reviewed Asante Twi reference.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    story_id: str = Field(
        ...,
        description="Stable story identifier (e.g., 'STORY-001').",
        min_length=1,
    )
    passage_id: str = Field(
        ...,
        description="Stable passage identifier, unique across dataset (e.g., 'STORY-001-P01').",
        min_length=1,
    )
    category: LinguisticCategory = Field(
        ...,
        description="Linguistic phenomenon being evaluated in this passage.",
    )
    english: str = Field(
        ...,
        description="Exact English source passage for translation.",
        min_length=1,
    )
    story_context: Optional[str] = Field(
        default=None,
        description="Surrounding narrative context (preceding actions, setting, or scene background).",
    )
    character_names: List[str] = Field(
        default_factory=list,
        description="List of characters appearing or referenced in the passage.",
    )
    glossary: Dict[str, str] = Field(
        default_factory=dict,
        description="Approved character names, domain terms, or culturally specific meanings.",
    )
    reference_twi: Optional[str] = Field(
        default=None,
        description="Optional human-reviewed Asante Twi reference translation.",
    )
    reference_status: ReferenceStatus = Field(
        default=ReferenceStatus.ABSENT,
        description="Status of the Asante Twi reference ('absent', 'drafted', 'human_reviewed').",
    )
    review_status: ReviewStatus = Field(
        default=ReviewStatus.PENDING,
        description="Benchmark review status ('pending', 'in_review', 'approved', 'rejected').",
    )
    source_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provenance, author, license, and creation notes.",
    )

    @field_validator("passage_id")
    @classmethod
    def validate_passage_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("passage_id cannot be empty or whitespace only.")
        if not _ID_REGEX.match(v):
            raise ValueError(
                f"passage_id '{v}' contains invalid characters. Use alphanumeric, dashes, and underscores."
            )
        return v

    @field_validator("story_id")
    @classmethod
    def validate_story_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("story_id cannot be empty or whitespace only.")
        if not _ID_REGEX.match(v):
            raise ValueError(
                f"story_id '{v}' contains invalid characters. Use alphanumeric, dashes, and underscores."
            )
        return v

    @field_validator("english")
    @classmethod
    def validate_english(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("English source passage cannot be empty or whitespace only.")
        return v

    @model_validator(mode="after")
    def validate_reference_consistency(self) -> BenchmarkPassage:
        if self.reference_status == ReferenceStatus.HUMAN_REVIEWED:
            if not self.reference_twi or not self.reference_twi.strip():
                raise ValueError(
                    "reference_twi is required when reference_status is 'human_reviewed'."
                )
        elif self.reference_status == ReferenceStatus.ABSENT:
            if self.reference_twi and self.reference_twi.strip():
                raise ValueError(
                    "reference_twi must be None or empty when reference_status is 'absent'."
                )
        return self


class TranslationResult(BaseModel):
    """
    Standardized result contract for Phase 2 translation engine outputs.

    Captures full provenance, configuration, engine identity, timings,
    and structured error metadata for reproducible comparison.
    """

    model_config = ConfigDict(extra="ignore")

    # Identifiers
    result_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this translation result record.",
    )
    experiment_id: str = Field(
        ...,
        description="Identifier of the experiment run that generated this result.",
    )
    story_id: str = Field(
        ...,
        description="Identifier of the source story.",
    )
    passage_id: str = Field(
        ...,
        description="Identifier of the translated benchmark passage.",
    )

    # Engine provenance
    engine_name: str = Field(
        ...,
        description="Identifier of the translation engine ('opus-mt', 'khaya', etc.).",
    )
    engine_version: Optional[str] = Field(
        default=None,
        description="Version string of the engine adapter or service.",
    )
    model_identifier: Optional[str] = Field(
        default=None,
        description="Model checkpoint or model identifier (e.g. 'Helsinki-NLP/opus-mt-en-tw').",
    )
    model_revision: Optional[str] = Field(
        default=None,
        description="Specific commit SHA, checkpoint tag, or revision identifier.",
    )

    # Context strategy and prompt information
    context_strategy: str = Field(
        default="none",
        description="Context strategy applied ('none', 'window_k', 'story_summary', 'glossary_guided').",
    )
    source_text: str = Field(
        ...,
        description="Exact source English passage submitted for translation.",
    )
    supplied_context: Optional[str] = Field(
        default=None,
        description="Contextual text passed alongside source_text to the engine.",
    )
    context_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed provenance and configuration metadata for the context strategy.",
    )
    is_cache_hit: bool = Field(
        default=False,
        description="Whether this result was retrieved from persistent cache instead of live invocation.",
    )

    # Translation output
    translated_text: Optional[str] = Field(
        default=None,
        description="Target Asante Twi translation produced by the engine (None if failed).",
    )

    # Timing and status
    start_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the translation request was initiated.",
    )
    elapsed_time_ms: Optional[float] = Field(
        default=None,
        description="End-to-end inference or API call duration in milliseconds.",
    )
    status: TranslationStatus = Field(
        default=TranslationStatus.SUCCESS,
        description="Execution status ('success', 'failed', 'partial', 'timeout').",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Human-readable error summary if the translation failed.",
    )
    error_details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured error details (e.g., HTTP status code, exception type, trace).",
    )

    # Generation and cost metadata
    generation_settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Engine hyperparameters (temperature, beam size, max tokens, etc.).",
    )
    source_character_count: Optional[int] = Field(
        default=None,
        description="Character count of source_text.",
    )
    source_token_count: Optional[int] = Field(
        default=None,
        description="Token count of source_text (when supported by tokenizer/API).",
    )
    target_character_count: Optional[int] = Field(
        default=None,
        description="Character count of translated_text.",
    )
    target_token_count: Optional[int] = Field(
        default=None,
        description="Token count of translated_text.",
    )
    estimated_cost_usd: Optional[float] = Field(
        default=None,
        description="Estimated API cost in USD based on billed usage.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp of this result record.",
    )

    @model_validator(mode="after")
    def populate_counts(self) -> TranslationResult:
        if self.source_character_count is None and self.source_text:
            self.source_character_count = len(self.source_text)
        if self.target_character_count is None and self.translated_text:
            self.target_character_count = len(self.translated_text)
        return self


class ExperimentRun(BaseModel):
    """
    Experiment record capturing configuration, participating engines, and run status.
    """

    model_config = ConfigDict(extra="ignore")

    experiment_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this experiment run.",
    )
    title: str = Field(
        ...,
        description="Short human-readable title for the experiment.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Detailed description of hypotheses and testing parameters.",
    )
    dataset_version: str = Field(
        ...,
        description="Version of the benchmark dataset evaluated.",
    )
    dataset_path: str = Field(
        ...,
        description="Relative or absolute path to the dataset evaluated.",
    )
    selected_passage_ids: List[str] = Field(
        default_factory=list,
        description="Passages included in this experiment run (empty means all passages).",
    )
    engines: List[str] = Field(
        default_factory=list,
        description="List of translation engine identifiers evaluated.",
    )
    context_strategy: str = Field(
        default="none",
        description="Context strategy evaluated in this experiment.",
    )
    configuration: Dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot of execution configuration and environment settings.",
    )
    status: ExperimentStatus = Field(
        default=ExperimentStatus.CREATED,
        description="Status of the experiment run ('created', 'running', 'completed', 'failed').",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when experiment was created.",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when experiment finished.",
    )
    summary_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics (total passages, success count, failure count, avg latency).",
    )


class DatasetManifest(BaseModel):
    """
    Manifest metadata for the benchmark dataset.
    """

    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., description="Name of the benchmark dataset.")
    version: str = Field(..., description="Semantic version string (e.g. '0.1.0').")
    description: str = Field(..., description="Summary of the dataset purpose.")
    license: str = Field(default="CC-BY-4.0", description="Usage license.")
    language_source: str = Field(default="en", description="Source ISO language code.")
    language_target: str = Field(
        default="ak-twi",
        description="Target language code (Asante Twi dialect).",
    )
    domain: str = Field(default="children_stories", description="Content domain.")
    passage_count: int = Field(..., description="Total number of passages in the dataset.")
    story_count: int = Field(..., description="Total number of distinct stories.")
    categories: Dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown of passage counts per linguistic category.",
    )
    created_date: str = Field(..., description="Creation date string (YYYY-MM-DD).")
    notes: str = Field(..., description="Intended usage and coverage notes.")
    is_development_fixture: bool = Field(
        default=True,
        description="Whether this dataset is a development test fixture rather than a validated linguistic benchmark.",
    )


class RecordValidationError(BaseModel):
    """Details of a record-level validation failure."""

    line_number: Optional[int] = Field(default=None, description="1-indexed line number in JSONL file.")
    passage_id: Optional[str] = Field(default=None, description="Passage ID if identifiable.")
    field: Optional[str] = Field(default=None, description="Field name where error occurred.")
    error_message: str = Field(..., description="Actionable explanation of why validation failed.")
    raw_snippet: Optional[str] = Field(default=None, description="Snippet of raw input line.")


class ValidationReport(BaseModel):
    """Comprehensive summary of dataset validation results."""

    is_valid: bool = Field(..., description="True if no errors were detected.")
    total_records: int = Field(default=0, description="Total JSON Lines processed.")
    valid_records: int = Field(default=0, description="Count of successfully validated records.")
    invalid_records: int = Field(default=0, description="Count of invalid records.")
    duplicate_ids: List[str] = Field(default_factory=list, description="Passage IDs found multiple times.")
    category_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Frequency count of passages per category.",
    )
    errors: List[RecordValidationError] = Field(
        default_factory=list,
        description="Detailed list of validation errors.",
    )
