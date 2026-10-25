"""
Unit tests for Phase 3 experiment runner enhancements:
  - Dry-run estimation accuracy with zero engine calls
  - API call budgeting and pre-dispatch enforcement
  - Live Khaya confirmation requirement
  - Request deduplication and separate record generation
  - Persistent caching and cache-only mode
  - Multi-strategy execution ('all')
  - CLI cache inspection and deliberate clearing
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from twi_lab.cache import TranslationCache
from twi_lab.engines.base import EngineAdapter
from twi_lab.runner import (
    BudgetExceededError,
    LiveCallConfirmationError,
    cli,
    run_experiment,
)
from twi_lab.schemas import (
    BenchmarkPassage,
    ExperimentStatus,
    LinguisticCategory,
    ReferenceStatus,
    ReviewStatus,
    TranslationResult,
    TranslationStatus,
)


# ---------------------------------------------------------------------------
# Test Helpers & Stubs
# ---------------------------------------------------------------------------


def _valid_passage_dict(
    passage_id: str = "STORY-001-P01",
    story_id: str = "STORY-001",
    english: str = "The sun rose.",
    glossary: dict | None = None,
) -> dict:
    return {
        "story_id": story_id,
        "passage_id": passage_id,
        "category": "simple_sentence",
        "english": english,
        "character_names": [],
        "glossary": glossary or {},
        "reference_twi": None,
        "reference_status": "absent",
        "review_status": "pending",
        "source_metadata": {"is_dev_fixture": True},
    }


def _write_dataset(path: Path, passages: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for p in passages:
            fh.write(json.dumps(p) + "\n")
    return path


class _CountingAdapter(EngineAdapter):
    """Counts actual calls to translate()."""

    def __init__(self, name: str = "stub-engine", status: TranslationStatus = TranslationStatus.SUCCESS):
        self._name = name
        self._status = status
        self.call_count = 0
        self.calls: list[dict] = []

    @property
    def engine_name(self) -> str:
        return self._name

    @property
    def engine_version(self) -> Optional[str]:
        return "1.0.0"

    def translate(
        self,
        source_text: str,
        *,
        experiment_id: str,
        story_id: str,
        passage_id: str,
        context_strategy: str = "none",
        supplied_context: Optional[str] = None,
        generation_settings: Optional[dict] = None,
    ) -> TranslationResult:
        self.call_count += 1
        self.calls.append({
            "source_text": source_text,
            "context_strategy": context_strategy,
            "supplied_context": supplied_context,
        })
        return TranslationResult(
            experiment_id=experiment_id,
            story_id=story_id,
            passage_id=passage_id,
            engine_name=self.engine_name,
            engine_version=self.engine_version,
            source_text=source_text,
            supplied_context=supplied_context,
            translated_text="Translated output." if self._status == TranslationStatus.SUCCESS else None,
            elapsed_time_ms=10.0,
            status=self._status,
            context_strategy=context_strategy,
        )


# ---------------------------------------------------------------------------
# Dry Run & Estimation Tests
# ---------------------------------------------------------------------------


class TestRunnerDryRunEstimates:

    def test_dry_run_makes_zero_engine_calls(self, tmp_path: Path):
        dataset = _write_dataset(
            tmp_path / "passages.jsonl",
            [_valid_passage_dict("P01"), _valid_passage_dict("P02")],
        )
        khaya_engine = _CountingAdapter(name="khaya")
        opus_engine = _CountingAdapter(name="opus-mt")

        exp = run_experiment(
            [khaya_engine, opus_engine],
            dataset_path=dataset,
            experiment_title="Dry run zero calls",
            results_dir=tmp_path / "results",
            cache_file=tmp_path / "cache.json",
            dry_run=True,
        )

        assert exp.status == ExperimentStatus.COMPLETED
        assert exp.summary_metrics["dry_run"] is True
        assert khaya_engine.call_count == 0
        assert opus_engine.call_count == 0

    def test_dry_run_accurately_estimates_calls_and_savings(self, tmp_path: Path):
        # 3 passages, 1 duplicated in text
        dataset = _write_dataset(
            tmp_path / "passages.jsonl",
            [
                _valid_passage_dict("P01", english="Common morning line."),
                _valid_passage_dict("P02", english="Unique second line."),
                _valid_passage_dict("P03", english="Common morning line."),
            ],
        )
        khaya_engine = _CountingAdapter(name="khaya")
        cache_path = tmp_path / "cache.json"

        # Pre-seed cache with P01
        cache = TranslationCache(cache_path)
        # We simulate a dry-run on empty cache first
        exp = run_experiment(
            [khaya_engine],
            dataset_path=dataset,
            experiment_title="Dry run estimates",
            results_dir=tmp_path / "results",
            cache_file=cache_path,
            dry_run=True,
            khaya_budget=10,
        )

        metrics = exp.summary_metrics
        assert metrics["total_planned_records"] == 3
        assert metrics["unique_requests"] == 2  # P01 and P03 share same key
        assert metrics["saved_by_deduplication"] == 1
        assert metrics["estimated_live_khaya_calls"] == 2
        assert metrics["permitted_to_proceed"] is True


# ---------------------------------------------------------------------------
# Budget Enforcement & Safety Tests
# ---------------------------------------------------------------------------


class TestRunnerBudgetEnforcement:

    def test_budget_exceeded_aborts_before_any_network_call(self, tmp_path: Path):
        dataset = _write_dataset(
            tmp_path / "passages.jsonl",
            [
                _valid_passage_dict("P01", english="Line one."),
                _valid_passage_dict("P02", english="Line two."),
                _valid_passage_dict("P03", english="Line three."),
            ],
        )
        khaya_engine = _CountingAdapter(name="khaya")

        # Budget of 2 is less than 3 required calls
        with pytest.raises(BudgetExceededError) as exc_info:
            run_experiment(
                [khaya_engine],
                dataset_path=dataset,
                experiment_title="Budget test",
                results_dir=tmp_path / "results",
                cache_file=tmp_path / "cache.json",
                khaya_budget=2,
                confirm_live_khaya=True,
                dry_run=False,
            )

        assert "exceeds configured budget (2)" in str(exc_info.value)
        # Crucial check: ZERO engine calls made!
        assert khaya_engine.call_count == 0

    def test_confirm_live_khaya_required_for_live_requests(self, tmp_path: Path):
        dataset = _write_dataset(tmp_path / "passages.jsonl", [_valid_passage_dict("P01")])
        khaya_engine = _CountingAdapter(name="khaya")

        # confirm_live_khaya=False by default
        with pytest.raises(LiveCallConfirmationError) as exc_info:
            run_experiment(
                [khaya_engine],
                dataset_path=dataset,
                experiment_title="Unconfirmed live run",
                results_dir=tmp_path / "results",
                cache_file=tmp_path / "cache.json",
                confirm_live_khaya=False,
                dry_run=False,
            )

        assert "--confirm-live-khaya" in str(exc_info.value)
        assert khaya_engine.call_count == 0


# ---------------------------------------------------------------------------
# Deduplication and Caching Tests
# ---------------------------------------------------------------------------


class TestRunnerDeduplicationAndCache:

    def test_in_run_deduplication_reuses_result_with_separate_records(self, tmp_path: Path):
        # 2 identical passages with different passage IDs
        dataset = _write_dataset(
            tmp_path / "passages.jsonl",
            [
                _valid_passage_dict("P01", english="Identical text."),
                _valid_passage_dict("P02", english="Identical text."),
            ],
        )
        engine = _CountingAdapter(name="khaya")
        results_dir = tmp_path / "results"

        exp = run_experiment(
            [engine],
            dataset_path=dataset,
            experiment_title="Dedup run",
            results_dir=results_dir,
            cache_file=tmp_path / "cache.json",
            confirm_live_khaya=True,
            dry_run=False,
        )

        assert exp.status == ExperimentStatus.COMPLETED
        # Only 1 live engine call made despite 2 passages
        assert engine.call_count == 1
        assert exp.summary_metrics["total_results"] == 2
        assert exp.summary_metrics["cache_hits"] == 1
        assert exp.summary_metrics["dedup_saved"] == 1

        # Check the result records in the output JSONL
        results_file = Path(exp.summary_metrics["results_file"])
        lines = [json.loads(line) for line in results_file.read_text(encoding="utf-8").splitlines()]
        assert len(lines) == 2
        assert lines[0]["passage_id"] == "P01"
        assert lines[0]["is_cache_hit"] is False
        assert lines[1]["passage_id"] == "P02"
        assert lines[1]["is_cache_hit"] is True
        assert lines[0]["result_id"] != lines[1]["result_id"]  # Unique IDs

    def test_persistent_cache_avoids_repeated_calls_on_second_run(self, tmp_path: Path):
        dataset = _write_dataset(tmp_path / "passages.jsonl", [_valid_passage_dict("P01")])
        cache_file = tmp_path / "cache.json"
        engine = _CountingAdapter(name="khaya")

        # Run 1: live call
        exp1 = run_experiment(
            [engine],
            dataset_path=dataset,
            experiment_title="Run 1",
            results_dir=tmp_path / "results",
            cache_file=cache_file,
            confirm_live_khaya=True,
        )
        assert engine.call_count == 1
        assert exp1.summary_metrics["cache_hits"] == 0

        # Run 2: served 100% from persistent cache
        exp2 = run_experiment(
            [engine],
            dataset_path=dataset,
            experiment_title="Run 2",
            results_dir=tmp_path / "results",
            cache_file=cache_file,
            confirm_live_khaya=False,  # No live call needed, so no confirmation error!
        )
        assert engine.call_count == 1  # Not incremented!
        assert exp2.summary_metrics["cache_hits"] == 1

    def test_cache_only_mode_succeeds_when_cached(self, tmp_path: Path):
        dataset = _write_dataset(tmp_path / "passages.jsonl", [_valid_passage_dict("P01")])
        cache_file = tmp_path / "cache.json"
        engine = _CountingAdapter(name="khaya")

        # Seed cache
        run_experiment(
            [engine],
            dataset_path=dataset,
            experiment_title="Seed",
            results_dir=tmp_path / "results",
            cache_file=cache_file,
            confirm_live_khaya=True,
        )

        # Cache-only run
        exp = run_experiment(
            [engine],
            dataset_path=dataset,
            experiment_title="Cache-only success",
            results_dir=tmp_path / "results",
            cache_file=cache_file,
            cache_only=True,
        )
        assert exp.status == ExperimentStatus.COMPLETED

    def test_cache_only_mode_aborts_when_uncached(self, tmp_path: Path):
        dataset = _write_dataset(tmp_path / "passages.jsonl", [_valid_passage_dict("P01")])
        engine = _CountingAdapter(name="khaya")

        with pytest.raises(RuntimeError) as exc_info:
            run_experiment(
                [engine],
                dataset_path=dataset,
                experiment_title="Cache-only failure",
                results_dir=tmp_path / "results",
                cache_file=tmp_path / "empty_cache.json",
                cache_only=True,
            )
        assert "Cache-only mode requested" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Multi-strategy and CLI Tests
# ---------------------------------------------------------------------------


class TestRunnerMultiStrategyAndCLI:

    def test_context_strategy_all_evaluates_four_strategies(self, tmp_path: Path):
        dataset = _write_dataset(tmp_path / "passages.jsonl", [_valid_passage_dict("P01")])
        engine = _CountingAdapter(name="opus-mt")

        exp = run_experiment(
            [engine],
            dataset_path=dataset,
            experiment_title="All strategies",
            results_dir=tmp_path / "results",
            cache_file=tmp_path / "cache.json",
            context_strategy="all",
            dry_run=True,
        )

        # 1 passage × 1 engine × 4 strategies = 4 planned records
        assert exp.summary_metrics["total_planned_records"] == 4

    def test_cli_cache_stats_and_clear(self, tmp_path: Path, capsys):
        cache_file = tmp_path / "cli_cache.json"
        c = TranslationCache(cache_file)
        c.set("k1", TranslationResult(
            experiment_id=str(uuid4()),
            story_id="S1",
            passage_id="P1",
            engine_name="khaya",
            source_text="Test",
            translated_text="Sɔhwɛ",
        ))

        # Check --cache-stats
        with pytest.raises(SystemExit) as exc:
            cli(["--cache-stats", "--cache-file", str(cache_file)])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "Total entries : 1" in captured.out

        # Check --clear-cache
        with pytest.raises(SystemExit) as exc:
            cli(["--clear-cache", "--cache-file", str(cache_file)])
        assert exc.value.code == 0
        captured2 = capsys.readouterr()
        assert "Cleared 1 entries" in captured2.out
        assert cache_file.exists() is False
