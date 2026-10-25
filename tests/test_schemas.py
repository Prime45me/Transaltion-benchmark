"""
Tests for BenchmarkPassage, TranslationResult, ExperimentRun, and
ValidationReport schemas defined in twi_lab.schemas.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from twi_lab.schemas import (
    BenchmarkPassage,
    DatasetManifest,
    ExperimentRun,
    ExperimentStatus,
    LinguisticCategory,
    RecordValidationError,
    ReferenceStatus,
    ReviewStatus,
    TranslationResult,
    TranslationStatus,
    ValidationReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_passage(**overrides) -> dict:
    """Return the minimum valid passage dict, with optional field overrides."""
    base = {
        "story_id": "TEST-001",
        "passage_id": "TEST-001-P01",
        "category": "simple_sentence",
        "english": "The bird sang in the tree.",
    }
    base.update(overrides)
    return base


def _minimal_result(**overrides) -> dict:
    base = {
        "experiment_id": "exp-001",
        "story_id": "TEST-001",
        "passage_id": "TEST-001-P01",
        "engine_name": "opus-mt",
        "source_text": "The bird sang in the tree.",
    }
    base.update(overrides)
    return base


# ===========================================================================
# BenchmarkPassage — valid cases
# ===========================================================================


class TestBenchmarkPassageValid:

    def test_minimal_valid_passage(self):
        p = BenchmarkPassage.model_validate(_minimal_passage())
        assert p.passage_id == "TEST-001-P01"
        assert p.story_id == "TEST-001"
        assert p.category == LinguisticCategory.SIMPLE_SENTENCE
        assert p.english == "The bird sang in the tree."
        assert p.reference_twi is None
        assert p.reference_status == ReferenceStatus.ABSENT
        assert p.review_status == ReviewStatus.PENDING

    def test_all_optional_fields_populated(self):
        p = BenchmarkPassage.model_validate(_minimal_passage(
            story_context="A morning scene.",
            character_names=["Ama", "Kofi"],
            glossary={"Ama": "Main character"},
            source_metadata={"author": "Test", "license": "CC-BY-4.0"},
        ))
        assert p.character_names == ["Ama", "Kofi"]
        assert p.glossary == {"Ama": "Main character"}
        assert p.story_context == "A morning scene."

    def test_reference_status_drafted_without_twi(self):
        """drafted status is allowed without reference_twi (translation in progress)."""
        p = BenchmarkPassage.model_validate(_minimal_passage(
            reference_status="drafted",
            reference_twi=None,
        ))
        assert p.reference_status == ReferenceStatus.DRAFTED

    def test_reference_status_human_reviewed_requires_twi(self):
        p = BenchmarkPassage.model_validate(_minimal_passage(
            reference_status="human_reviewed",
            reference_twi="Ɔkɔkɔ no anka dua no mu.",
        ))
        assert p.reference_twi == "Ɔkɔkɔ no anka dua no mu."

    def test_all_linguistic_categories_are_accepted(self):
        for cat in LinguisticCategory:
            p = BenchmarkPassage.model_validate(_minimal_passage(
                passage_id=f"TEST-CAT-{cat.value}",
                category=cat.value,
            ))
            assert p.category == cat

    def test_whitespace_is_stripped_from_ids(self):
        p = BenchmarkPassage.model_validate(_minimal_passage(
            story_id="  TEST-001  ",
            passage_id="  TEST-001-P01  ",
        ))
        assert p.story_id == "TEST-001"
        assert p.passage_id == "TEST-001-P01"

    def test_underscores_and_dashes_in_ids_accepted(self):
        p = BenchmarkPassage.model_validate(_minimal_passage(
            story_id="MY_STORY-01",
            passage_id="MY_STORY-01_P01",
        ))
        assert p.story_id == "MY_STORY-01"


# ===========================================================================
# BenchmarkPassage — invalid cases
# ===========================================================================


class TestBenchmarkPassageInvalid:

    def test_missing_story_id(self):
        data = _minimal_passage()
        del data["story_id"]
        with pytest.raises(ValidationError) as exc_info:
            BenchmarkPassage.model_validate(data)
        assert "story_id" in str(exc_info.value)

    def test_missing_passage_id(self):
        data = _minimal_passage()
        del data["passage_id"]
        with pytest.raises(ValidationError):
            BenchmarkPassage.model_validate(data)

    def test_missing_english(self):
        data = _minimal_passage()
        del data["english"]
        with pytest.raises(ValidationError):
            BenchmarkPassage.model_validate(data)

    def test_empty_english_string(self):
        with pytest.raises(ValidationError) as exc_info:
            BenchmarkPassage.model_validate(_minimal_passage(english=""))
        assert "empty" in str(exc_info.value).lower() or "english" in str(exc_info.value).lower()

    def test_whitespace_only_english(self):
        with pytest.raises(ValidationError):
            BenchmarkPassage.model_validate(_minimal_passage(english="   "))

    def test_invalid_category_value(self):
        with pytest.raises(ValidationError) as exc_info:
            BenchmarkPassage.model_validate(_minimal_passage(category="nonsense_category"))
        assert "category" in str(exc_info.value).lower() or "nonsense" in str(exc_info.value).lower()

    def test_invalid_passage_id_special_chars(self):
        with pytest.raises(ValidationError) as exc_info:
            BenchmarkPassage.model_validate(_minimal_passage(passage_id="TEST 001/P01"))
        assert "invalid characters" in str(exc_info.value).lower()

    def test_invalid_story_id_special_chars(self):
        with pytest.raises(ValidationError):
            BenchmarkPassage.model_validate(_minimal_passage(story_id="STORY@001"))

    def test_human_reviewed_without_reference_twi_fails(self):
        with pytest.raises(ValidationError) as exc_info:
            BenchmarkPassage.model_validate(_minimal_passage(
                reference_status="human_reviewed",
                reference_twi=None,
            ))
        assert "human_reviewed" in str(exc_info.value).lower()

    def test_absent_status_with_nonempty_reference_twi_fails(self):
        with pytest.raises(ValidationError) as exc_info:
            BenchmarkPassage.model_validate(_minimal_passage(
                reference_status="absent",
                reference_twi="Ɔkɔkɔ no anka dua no mu.",
            ))
        assert "absent" in str(exc_info.value).lower()

    def test_invalid_reference_status_value(self):
        with pytest.raises(ValidationError):
            BenchmarkPassage.model_validate(_minimal_passage(reference_status="verified"))

    def test_invalid_review_status_value(self):
        with pytest.raises(ValidationError):
            BenchmarkPassage.model_validate(_minimal_passage(review_status="done"))

    def test_extra_unknown_field_is_rejected(self):
        with pytest.raises(ValidationError):
            BenchmarkPassage.model_validate(_minimal_passage(unknown_field="oops"))


# ===========================================================================
# TranslationResult — Phase 2 contract
# ===========================================================================


class TestTranslationResult:

    def test_minimal_valid_result(self):
        r = TranslationResult.model_validate(_minimal_result())
        assert r.engine_name == "opus-mt"
        assert r.status == TranslationStatus.SUCCESS
        assert r.context_strategy == "none"
        assert r.result_id is not None  # auto-generated UUID

    def test_source_character_count_auto_populated(self):
        r = TranslationResult.model_validate(_minimal_result())
        assert r.source_character_count == len("The bird sang in the tree.")

    def test_target_character_count_auto_populated(self):
        r = TranslationResult.model_validate(_minimal_result(
            translated_text="Ɔkɔkɔ no anka dua no mu.",
        ))
        assert r.target_character_count == len("Ɔkɔkɔ no anka dua no mu.")

    def test_failed_result(self):
        r = TranslationResult.model_validate(_minimal_result(
            status="failed",
            error_message="Connection timed out.",
            error_details={"http_status": 503},
        ))
        assert r.status == TranslationStatus.FAILED
        assert r.error_message == "Connection timed out."
        assert r.error_details["http_status"] == 503

    def test_full_provenance_fields(self):
        r = TranslationResult.model_validate(_minimal_result(
            engine_version="1.2.3",
            model_identifier="Helsinki-NLP/opus-mt-en-tw",
            model_revision="abc123",
            context_strategy="window_k",
            generation_settings={"beam_size": 4, "max_length": 256},
            estimated_cost_usd=0.0002,
        ))
        assert r.model_identifier == "Helsinki-NLP/opus-mt-en-tw"
        assert r.estimated_cost_usd == 0.0002
        assert r.generation_settings["beam_size"] == 4

    def test_result_id_is_unique_per_instance(self):
        r1 = TranslationResult.model_validate(_minimal_result())
        r2 = TranslationResult.model_validate(_minimal_result())
        assert r1.result_id != r2.result_id

    def test_experiment_id_required(self):
        data = _minimal_result()
        del data["experiment_id"]
        with pytest.raises(ValidationError):
            TranslationResult.model_validate(data)


# ===========================================================================
# ExperimentRun
# ===========================================================================


class TestExperimentRun:

    def test_minimal_valid_experiment(self):
        exp = ExperimentRun.model_validate({
            "title": "Baseline comparison",
            "dataset_version": "0.1.0",
            "dataset_path": "data/samples/passages.jsonl",
        })
        assert exp.status == ExperimentStatus.CREATED
        assert exp.experiment_id is not None
        assert exp.engines == []

    def test_experiment_with_all_fields(self):
        exp = ExperimentRun.model_validate({
            "title": "Context window test",
            "description": "Testing window_k vs none strategy.",
            "dataset_version": "0.1.0",
            "dataset_path": "data/samples/passages.jsonl",
            "selected_passage_ids": ["TEST-001-P01"],
            "engines": ["opus-mt", "khaya"],
            "context_strategy": "window_k",
            "configuration": {"window_size": 2},
        })
        assert "opus-mt" in exp.engines
        assert exp.context_strategy == "window_k"

    def test_missing_title_fails(self):
        with pytest.raises(ValidationError):
            ExperimentRun.model_validate({
                "dataset_version": "0.1.0",
                "dataset_path": "data/samples/passages.jsonl",
            })


# ===========================================================================
# ValidationReport
# ===========================================================================


class TestValidationReport:

    def test_empty_valid_report(self):
        report = ValidationReport(is_valid=True, total_records=0, valid_records=0, invalid_records=0)
        assert report.is_valid is True
        assert report.errors == []
        assert report.duplicate_ids == []

    def test_report_with_errors(self):
        err = RecordValidationError(
            line_number=3,
            passage_id="P01",
            field="english",
            error_message="English source cannot be empty.",
        )
        report = ValidationReport(
            is_valid=False,
            total_records=5,
            valid_records=4,
            invalid_records=1,
            errors=[err],
        )
        assert report.invalid_records == 1
        assert report.errors[0].line_number == 3
        assert report.errors[0].field == "english"

    def test_category_counts_populated(self):
        report = ValidationReport(
            is_valid=True,
            total_records=3,
            valid_records=3,
            invalid_records=0,
            category_counts={"simple_sentence": 2, "dialogue": 1},
        )
        assert report.category_counts["simple_sentence"] == 2


# ===========================================================================
# DatasetManifest
# ===========================================================================


class TestDatasetManifest:

    def test_valid_manifest(self):
        m = DatasetManifest.model_validate({
            "title": "Test Dataset",
            "version": "0.1.0",
            "description": "A test fixture.",
            "passage_count": 10,
            "story_count": 3,
            "created_date": "2026-10-21",
            "notes": "Development only.",
        })
        assert m.is_development_fixture is True
        assert m.language_source == "en"
        assert m.language_target == "ak-twi"
