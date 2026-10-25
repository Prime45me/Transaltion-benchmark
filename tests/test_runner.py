"""
Tests for the experiment runner (twi_lab.runner).

All engine adapter calls are replaced by lightweight stub adapters —
no translation APIs are called and no model weights are loaded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

from twi_lab.engines.base import EngineAdapter
from twi_lab.runner import run_experiment, cli
from twi_lab.schemas import ExperimentStatus, TranslationResult, TranslationStatus


# ---------------------------------------------------------------------------
# Stub adapters used across all runner tests
# ---------------------------------------------------------------------------

class _SuccessAdapter(EngineAdapter):
    """Always returns a SUCCESS result after a fake 5 ms translation."""

    def __init__(self, name: str = "stub-engine"):
        self._name = name

    @property
    def engine_name(self) -> str:
        return self._name

    @property
    def engine_version(self) -> Optional[str]:
        return "0.0.0"

    def translate(self, source_text, *, experiment_id, story_id, passage_id,
                  context_strategy="none", supplied_context=None,
                  generation_settings=None) -> TranslationResult:
        return TranslationResult(
            experiment_id=experiment_id,
            story_id=story_id,
            passage_id=passage_id,
            engine_name=self.engine_name,
            engine_version=self.engine_version,
            source_text=source_text,
            translated_text="Stub translation.",
            elapsed_time_ms=5.0,
            status=TranslationStatus.SUCCESS,
            context_strategy=context_strategy,
        )


class _FailAdapter(EngineAdapter):
    """Always returns a FAILED result."""

    @property
    def engine_name(self) -> str:
        return "fail-engine"

    @property
    def engine_version(self) -> Optional[str]:
        return "0.0.0"

    def translate(self, source_text, *, experiment_id, story_id, passage_id,
                  context_strategy="none", supplied_context=None,
                  generation_settings=None) -> TranslationResult:
        return TranslationResult(
            experiment_id=experiment_id,
            story_id=story_id,
            passage_id=passage_id,
            engine_name=self.engine_name,
            engine_version=self.engine_version,
            source_text=source_text,
            translated_text=None,
            elapsed_time_ms=1.0,
            status=TranslationStatus.FAILED,
            error_message="Stub failure.",
            context_strategy=context_strategy,
        )


class _TimeoutAdapter(EngineAdapter):
    """Always returns a TIMEOUT result."""

    @property
    def engine_name(self) -> str:
        return "timeout-engine"

    @property
    def engine_version(self) -> Optional[str]:
        return "0.0.0"

    def translate(self, source_text, *, experiment_id, story_id, passage_id,
                  context_strategy="none", supplied_context=None,
                  generation_settings=None) -> TranslationResult:
        return TranslationResult(
            experiment_id=experiment_id,
            story_id=story_id,
            passage_id=passage_id,
            engine_name=self.engine_name,
            engine_version=self.engine_version,
            source_text=source_text,
            elapsed_time_ms=30000.0,
            status=TranslationStatus.TIMEOUT,
            error_message="Request timed out.",
            context_strategy=context_strategy,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, records: list) -> None:
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _valid_passage(passage_id: str = "P01", story_id: str = "STORY-001") -> dict:
    return {
        "story_id": story_id,
        "passage_id": passage_id,
        "category": "simple_sentence",
        "english": "The child laughed.",
    }


# ---------------------------------------------------------------------------
# run_experiment — basic success
# ---------------------------------------------------------------------------

class TestRunExperimentSuccess:

    def test_completed_status_on_success(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage()])
        results_dir = tmp_path / "results"

        exp = run_experiment(
            [_SuccessAdapter()],
            dataset_path=dataset,
            experiment_title="Test run",
            results_dir=results_dir,
        )

        assert exp.status == ExperimentStatus.COMPLETED

    def test_experiment_id_is_populated(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage()])

        exp = run_experiment(
            [_SuccessAdapter()],
            dataset_path=dataset,
            experiment_title="ID test",
            results_dir=tmp_path / "results",
        )

        assert exp.experiment_id
        assert len(exp.experiment_id) > 0

    def test_summary_metrics_counted_correctly(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [
            _valid_passage("P01"),
            _valid_passage("P02"),
            _valid_passage("P03"),
        ])

        exp = run_experiment(
            [_SuccessAdapter()],
            dataset_path=dataset,
            experiment_title="Count test",
            results_dir=tmp_path / "results",
        )

        assert exp.summary_metrics["total_results"] == 3
        assert exp.summary_metrics["success_count"] == 3
        assert exp.summary_metrics["failed_count"] == 0

    def test_results_jsonl_written(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage("P01"), _valid_passage("P02")])
        results_dir = tmp_path / "results"

        exp = run_experiment(
            [_SuccessAdapter()],
            dataset_path=dataset,
            experiment_title="File test",
            results_dir=results_dir,
        )

        results_file = Path(exp.summary_metrics["results_file"])
        assert results_file.exists()
        lines = [l for l in results_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 2

    def test_experiment_json_manifest_written(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage()])
        results_dir = tmp_path / "results"

        exp = run_experiment(
            [_SuccessAdapter()],
            dataset_path=dataset,
            experiment_title="Manifest test",
            results_dir=results_dir,
        )

        manifest_file = results_dir / f"experiment_{exp.experiment_id}.json"
        assert manifest_file.exists()
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert data["title"] == "Manifest test"
        assert data["status"] == "completed"

    def test_multiple_engines_produce_all_results(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage("P01"), _valid_passage("P02")])

        exp = run_experiment(
            [_SuccessAdapter("engine-a"), _SuccessAdapter("engine-b")],
            dataset_path=dataset,
            experiment_title="Multi engine",
            results_dir=tmp_path / "results",
        )

        # 2 passages × 2 engines = 4 results
        assert exp.summary_metrics["total_results"] == 4

    def test_results_jsonl_contains_valid_json_objects(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage()])
        results_dir = tmp_path / "results"

        exp = run_experiment(
            [_SuccessAdapter()],
            dataset_path=dataset,
            experiment_title="JSON validity test",
            results_dir=results_dir,
        )

        results_file = Path(exp.summary_metrics["results_file"])
        for line in results_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                obj = json.loads(line)
                assert "engine_name" in obj
                assert "source_text" in obj
                assert "status" in obj

    def test_engine_names_recorded_in_experiment(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage()])

        exp = run_experiment(
            [_SuccessAdapter("engine-a"), _SuccessAdapter("engine-b")],
            dataset_path=dataset,
            experiment_title="Engine names test",
            results_dir=tmp_path / "results",
        )

        assert "engine-a" in exp.engines
        assert "engine-b" in exp.engines


# ---------------------------------------------------------------------------
# run_experiment — failure counting
# ---------------------------------------------------------------------------

class TestRunExperimentFailureCounting:

    def test_failed_results_counted(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage("P01"), _valid_passage("P02")])

        exp = run_experiment(
            [_FailAdapter()],
            dataset_path=dataset,
            experiment_title="Fail count test",
            results_dir=tmp_path / "results",
        )

        assert exp.status == ExperimentStatus.COMPLETED
        assert exp.summary_metrics["failed_count"] == 2
        assert exp.summary_metrics["success_count"] == 0

    def test_timeout_results_counted_separately(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage()])

        exp = run_experiment(
            [_TimeoutAdapter()],
            dataset_path=dataset,
            experiment_title="Timeout test",
            results_dir=tmp_path / "results",
        )

        assert exp.summary_metrics["timeout_count"] == 1
        assert exp.summary_metrics["failed_count"] == 1

    def test_mixed_engines_counted_correctly(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage()])

        exp = run_experiment(
            [_SuccessAdapter(), _FailAdapter()],
            dataset_path=dataset,
            experiment_title="Mixed engines",
            results_dir=tmp_path / "results",
        )

        assert exp.summary_metrics["total_results"] == 2
        assert exp.summary_metrics["success_count"] == 1
        assert exp.summary_metrics["failed_count"] == 1


# ---------------------------------------------------------------------------
# run_experiment — dry run
# ---------------------------------------------------------------------------

class TestRunExperimentDryRun:

    def test_dry_run_completes_without_engine_calls(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage()])

        called = []
        class _TrackingAdapter(_SuccessAdapter):
            def translate(self, *args, **kwargs):
                called.append(True)
                return super().translate(*args, **kwargs)

        exp = run_experiment(
            [_TrackingAdapter()],
            dataset_path=dataset,
            experiment_title="Dry run test",
            results_dir=tmp_path / "results",
            dry_run=True,
        )

        assert exp.status == ExperimentStatus.COMPLETED
        assert exp.summary_metrics.get("dry_run") is True
        assert called == []  # no engine calls

    def test_dry_run_writes_experiment_manifest(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage()])
        results_dir = tmp_path / "results"

        exp = run_experiment(
            [_SuccessAdapter()],
            dataset_path=dataset,
            experiment_title="Dry run manifest",
            results_dir=results_dir,
            dry_run=True,
        )

        manifest = results_dir / f"experiment_{exp.experiment_id}.json"
        assert manifest.exists()


# ---------------------------------------------------------------------------
# run_experiment — passage filtering
# ---------------------------------------------------------------------------

class TestRunExperimentPassageFiltering:

    def test_selected_passage_ids_filter_correctly(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [
            _valid_passage("P01"),
            _valid_passage("P02"),
            _valid_passage("P03"),
        ])

        exp = run_experiment(
            [_SuccessAdapter()],
            dataset_path=dataset,
            experiment_title="Filter test",
            selected_passage_ids=["P01", "P03"],
            results_dir=tmp_path / "results",
        )

        assert exp.summary_metrics["total_results"] == 2
        assert exp.summary_metrics["passage_count"] == 2

    def test_empty_passage_filter_runs_all(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage("P01"), _valid_passage("P02")])

        exp = run_experiment(
            [_SuccessAdapter()],
            dataset_path=dataset,
            experiment_title="All passages",
            selected_passage_ids=None,
            results_dir=tmp_path / "results",
        )

        assert exp.summary_metrics["total_results"] == 2


# ---------------------------------------------------------------------------
# run_experiment — context strategy recorded
# ---------------------------------------------------------------------------

class TestRunExperimentContextStrategy:

    def test_context_strategy_stored_in_experiment(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage()])

        exp = run_experiment(
            [_SuccessAdapter()],
            dataset_path=dataset,
            experiment_title="Strategy test",
            context_strategy="none",
            results_dir=tmp_path / "results",
        )

        assert exp.context_strategy == "none"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestRunnerCLI:

    def test_dry_run_exits_zero(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage()])
        results_dir = tmp_path / "results"

        # OPUSMTAdapter is imported locally inside cli(); patch it at its source
        with patch("twi_lab.engines.opus_mt.OPUSMTAdapter", return_value=_SuccessAdapter("opus-mt")):
            with pytest.raises(SystemExit) as exc:
                cli([
                    "--engine", "opus-mt",
                    "--title", "CLI dry run",
                    "--dataset", str(dataset),
                    "--results-dir", str(results_dir),
                    "--dry-run",
                ])
            assert exc.value.code == 0

    def test_missing_engine_flag_exits_two(self, tmp_path):
        dataset = tmp_path / "passages.jsonl"
        _write_jsonl(dataset, [_valid_passage()])
        with pytest.raises(SystemExit) as exc:
            cli(["--title", "No engine"])
        assert exc.value.code == 2

    def test_invalid_engine_choice_exits_two(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            cli(["--engine", "gpt-4", "--title", "Bad engine"])
        assert exc.value.code == 2
