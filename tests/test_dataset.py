"""
Tests for dataset.py — JSONL loading, validation logic, duplicate detection,
and CLI behavior. Uses temporary files so benchmark data is never touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from twi_lab.dataset import _iter_jsonl_lines, load_passages, validate_dataset, cli
from twi_lab.schemas import ValidationReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(tmp_path: Path, records: list) -> Path:
    """Write a list of objects to a temporary JSONL file."""
    fpath = tmp_path / "passages.jsonl"
    lines = []
    for r in records:
        if isinstance(r, str):
            lines.append(r)  # pre-encoded (can be invalid JSON)
        else:
            lines.append(json.dumps(r, ensure_ascii=False))
    fpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fpath


def _valid_record(**overrides) -> dict:
    base = {
        "story_id": "STORY-T01",
        "passage_id": "STORY-T01-P01",
        "category": "simple_sentence",
        "english": "The drum sounded across the valley.",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# JSONL line iterator
# ---------------------------------------------------------------------------


class TestIterJsonlLines:

    def test_valid_json_object_parsed(self, tmp_path):
        fpath = _write_jsonl(tmp_path, [_valid_record()])
        results = list(_iter_jsonl_lines(fpath))
        assert len(results) == 1
        line_num, record, err = results[0]
        assert line_num == 1
        assert err is None
        assert record["english"] == "The drum sounded across the valley."

    def test_blank_lines_skipped(self, tmp_path):
        fpath = tmp_path / "p.jsonl"
        fpath.write_text("\n\n" + json.dumps(_valid_record()) + "\n\n", encoding="utf-8")
        results = list(_iter_jsonl_lines(fpath))
        assert len(results) == 1

    def test_invalid_json_returns_error(self, tmp_path):
        fpath = _write_jsonl(tmp_path, ["{not valid json"])
        results = list(_iter_jsonl_lines(fpath))
        assert len(results) == 1
        _, record, err = results[0]
        assert record is None
        assert "JSON parse error" in err

    def test_json_array_is_rejected(self, tmp_path):
        fpath = _write_jsonl(tmp_path, ["[1, 2, 3]"])
        results = list(_iter_jsonl_lines(fpath))
        _, record, err = results[0]
        assert record is None
        assert "JSON object" in err


# ---------------------------------------------------------------------------
# validate_dataset — acceptance
# ---------------------------------------------------------------------------


class TestValidateDatasetAcceptance:

    def test_all_valid_records_pass(self, tmp_path):
        records = [
            _valid_record(passage_id="STORY-T01-P01"),
            _valid_record(passage_id="STORY-T01-P02", category="dialogue",
                          english="She called his name."),
            _valid_record(passage_id="STORY-T01-P03", category="negation",
                          english="He did not answer."),
        ]
        fpath = _write_jsonl(tmp_path, records)
        report = validate_dataset(fpath)
        assert report.is_valid is True
        assert report.total_records == 3
        assert report.valid_records == 3
        assert report.invalid_records == 0
        assert report.duplicate_ids == []

    def test_category_counts_are_correct(self, tmp_path):
        records = [
            _valid_record(passage_id="P01", category="simple_sentence"),
            _valid_record(passage_id="P02", category="simple_sentence",
                          english="The child laughed."),
            _valid_record(passage_id="P03", category="dialogue",
                          english="She spoke softly."),
        ]
        fpath = _write_jsonl(tmp_path, records)
        report = validate_dataset(fpath)
        assert report.category_counts["simple_sentence"] == 2
        assert report.category_counts["dialogue"] == 1

    def test_single_valid_record_passes(self, tmp_path):
        fpath = _write_jsonl(tmp_path, [_valid_record()])
        report = validate_dataset(fpath)
        assert report.is_valid is True
        assert report.valid_records == 1


# ---------------------------------------------------------------------------
# validate_dataset — rejection cases
# ---------------------------------------------------------------------------


class TestValidateDatasetRejection:

    def test_missing_required_field_fails(self, tmp_path):
        bad = _valid_record()
        del bad["english"]
        fpath = _write_jsonl(tmp_path, [bad])
        report = validate_dataset(fpath)
        assert report.is_valid is False
        assert report.invalid_records == 1
        assert any("english" in e.error_message.lower() or
                   (e.field and "english" in e.field.lower())
                   for e in report.errors)

    def test_empty_english_source_fails(self, tmp_path):
        fpath = _write_jsonl(tmp_path, [_valid_record(english="")])
        report = validate_dataset(fpath)
        assert report.is_valid is False
        assert report.invalid_records == 1

    def test_invalid_category_value_fails(self, tmp_path):
        fpath = _write_jsonl(tmp_path, [_valid_record(category="made_up_category")])
        report = validate_dataset(fpath)
        assert report.is_valid is False

    def test_malformed_json_lines_fail(self, tmp_path):
        fpath = _write_jsonl(tmp_path, ["{broken json line"])
        report = validate_dataset(fpath)
        assert report.is_valid is False
        assert report.invalid_records == 1

    def test_mixed_valid_and_invalid(self, tmp_path):
        records: list = [
            _valid_record(passage_id="P01"),
            "{broken",                                    # malformed JSON
            _valid_record(passage_id="P03", english=""),  # empty english
            _valid_record(passage_id="P04", english="Good record."),
        ]
        fpath = _write_jsonl(tmp_path, records)
        report = validate_dataset(fpath)
        assert report.is_valid is False
        assert report.valid_records == 2
        assert report.invalid_records == 2

    def test_line_numbers_reported_in_errors(self, tmp_path):
        records: list = [
            _valid_record(passage_id="P01"),
            _valid_record(passage_id="P02", english=""),  # line 2 fails
        ]
        fpath = _write_jsonl(tmp_path, records)
        report = validate_dataset(fpath)
        error_lines = [e.line_number for e in report.errors]
        assert 2 in error_lines


# ---------------------------------------------------------------------------
# Duplicate ID detection
# ---------------------------------------------------------------------------


class TestDuplicateIdDetection:

    def test_duplicate_passage_ids_detected(self, tmp_path):
        records = [
            _valid_record(passage_id="P01"),
            _valid_record(passage_id="P01", english="Different text."),
        ]
        fpath = _write_jsonl(tmp_path, records)
        report = validate_dataset(fpath)
        assert report.is_valid is False
        assert "P01" in report.duplicate_ids

    def test_duplicate_ids_counted_once_in_duplicate_list(self, tmp_path):
        records = [
            _valid_record(passage_id="P01"),
            _valid_record(passage_id="P01", english="Second."),
            _valid_record(passage_id="P01", english="Third."),
        ]
        fpath = _write_jsonl(tmp_path, records)
        report = validate_dataset(fpath)
        assert report.duplicate_ids.count("P01") == 1

    def test_unique_ids_not_flagged(self, tmp_path):
        records = [
            _valid_record(passage_id="P01"),
            _valid_record(passage_id="P02", english="Another passage."),
        ]
        fpath = _write_jsonl(tmp_path, records)
        report = validate_dataset(fpath)
        assert report.duplicate_ids == []


# ---------------------------------------------------------------------------
# File-not-found
# ---------------------------------------------------------------------------


class TestFileNotFound:

    def test_missing_file_raises(self, tmp_path):
        missing = tmp_path / "nonexistent.jsonl"
        with pytest.raises(FileNotFoundError):
            validate_dataset(missing)


# ---------------------------------------------------------------------------
# load_passages
# ---------------------------------------------------------------------------


class TestLoadPassages:

    def test_load_returns_valid_passages_only(self, tmp_path):
        records: list = [
            _valid_record(passage_id="P01"),
            _valid_record(passage_id="P02", english=""),  # invalid
            _valid_record(passage_id="P03", english="Another one."),
        ]
        fpath = _write_jsonl(tmp_path, records)
        passages = load_passages(fpath)
        ids = [p.passage_id for p in passages]
        assert "P01" in ids
        assert "P03" in ids
        assert len(passages) == 2

    def test_load_skips_duplicates(self, tmp_path):
        records = [
            _valid_record(passage_id="P01"),
            _valid_record(passage_id="P01", english="Duplicate."),
        ]
        fpath = _write_jsonl(tmp_path, records)
        passages = load_passages(fpath)
        assert len(passages) == 1
        assert passages[0].passage_id == "P01"

    def test_load_empty_file_returns_empty_list(self, tmp_path):
        fpath = tmp_path / "empty.jsonl"
        fpath.write_text("", encoding="utf-8")
        passages = load_passages(fpath)
        assert passages == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:

    def test_cli_exits_zero_on_valid_dataset(self, tmp_path, capsys):
        fpath = _write_jsonl(tmp_path, [
            _valid_record(passage_id="P01"),
            _valid_record(passage_id="P02", english="The drum beat slowly."),
        ])
        with pytest.raises(SystemExit) as exc:
            cli(["--validate", "--dataset", str(fpath)])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "PASSED" in captured.out

    def test_cli_exits_one_on_invalid_dataset(self, tmp_path, capsys):
        fpath = _write_jsonl(tmp_path, [_valid_record(english="")])
        with pytest.raises(SystemExit) as exc:
            cli(["--validate", "--dataset", str(fpath)])
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "FAILED" in captured.out

    def test_cli_exits_one_on_missing_file(self, tmp_path, capsys):
        missing = str(tmp_path / "ghost.jsonl")
        with pytest.raises(SystemExit) as exc:
            cli(["--validate", "--dataset", missing])
        assert exc.value.code == 1

    def test_cli_reports_category_counts(self, tmp_path, capsys):
        fpath = _write_jsonl(tmp_path, [
            _valid_record(passage_id="P01", category="simple_sentence"),
            _valid_record(passage_id="P02", category="dialogue",
                          english="She asked a question."),
        ])
        with pytest.raises(SystemExit):
            cli(["--validate", "--dataset", str(fpath)])
        captured = capsys.readouterr()
        assert "simple_sentence" in captured.out
        assert "dialogue" in captured.out

    def test_cli_verbose_shows_error_snippets(self, tmp_path, capsys):
        fpath = _write_jsonl(tmp_path, [_valid_record(english="")])
        with pytest.raises(SystemExit):
            cli(["--validate", "--dataset", str(fpath), "--verbose"])
        captured = capsys.readouterr()
        assert "FAILED" in captured.out

    def test_cli_requires_validate_flag(self, tmp_path):
        """--validate is required; omitting it should error."""
        fpath = _write_jsonl(tmp_path, [_valid_record()])
        with pytest.raises(SystemExit) as exc:
            cli(["--dataset", str(fpath)])
        # argparse exits with code 2 for usage errors
        assert exc.value.code == 2
