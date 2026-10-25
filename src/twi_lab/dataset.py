"""
Dataset loading, validation, and command-line interface for the
Twi Translation Benchmark Lab.

Responsibilities:
- Load JSONL passage records with line-accurate error reporting.
- Validate every record against the BenchmarkPassage schema.
- Detect duplicate passage IDs.
- Produce a structured ValidationReport.
- Provide a CLI entry point: ``python -m twi_lab.dataset --validate``

Usage:
    python -m twi_lab.dataset --validate
    python -m twi_lab.dataset --validate --dataset path/to/passages.jsonl
    python -m twi_lab.dataset --validate --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from pydantic import ValidationError

from twi_lab.config import Settings, get_settings
from twi_lab.logging_config import setup_logging
from twi_lab.schemas import (
    BenchmarkPassage,
    RecordValidationError,
    ValidationReport,
)

logger = setup_logging()


# ---------------------------------------------------------------------------
# Low-level JSONL reading
# ---------------------------------------------------------------------------


def _iter_jsonl_lines(path: Path) -> Iterator[Tuple[int, Optional[dict], Optional[str]]]:
    """
    Yield ``(line_number, parsed_dict_or_None, error_or_None)`` for every
    non-blank line in a JSONL file.

    Line numbers are 1-indexed to match text editor conventions.
    Blank lines are silently skipped (not counted as errors).
    """
    with open(path, "r", encoding="utf-8") as fh:
        for line_number, raw_line in enumerate(fh, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
                if not isinstance(record, dict):
                    yield line_number, None, f"Expected a JSON object, got {type(record).__name__}."
                else:
                    yield line_number, record, None
            except json.JSONDecodeError as exc:
                snippet = stripped[:80] + ("…" if len(stripped) > 80 else "")
                yield line_number, None, f"JSON parse error: {exc.msg} (snippet: {snippet!r})"


# ---------------------------------------------------------------------------
# Core validation logic
# ---------------------------------------------------------------------------


def validate_dataset(
    dataset_path: Path,
    settings: Optional[Settings] = None,
) -> ValidationReport:
    """
    Load a JSONL passage dataset and validate every record.

    Args:
        dataset_path: Absolute path to the ``.jsonl`` passages file.
        settings: Optional Settings instance (uses singleton if omitted).

    Returns:
        A :class:`~twi_lab.schemas.ValidationReport` describing the outcome.

    Raises:
        FileNotFoundError: If ``dataset_path`` does not exist.
    """
    if settings is None:
        settings = get_settings()

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Dataset file not found: {dataset_path}\n"
            "Check DATASET_PATH in your .env or pass --dataset explicitly."
        )

    logger.info("Loading dataset: %s", dataset_path)

    errors: List[RecordValidationError] = []
    seen_ids: dict[str, int] = {}   # passage_id -> first line number
    duplicate_ids: List[str] = []
    category_counts: dict[str, int] = {}
    valid_count = 0
    total_count = 0

    for line_number, record, parse_error in _iter_jsonl_lines(dataset_path):
        total_count += 1

        # JSON parse failure
        if parse_error is not None:
            logger.warning("Line %d: JSON error — %s", line_number, parse_error)
            errors.append(
                RecordValidationError(
                    line_number=line_number,
                    error_message=parse_error,
                )
            )
            continue

        # Pydantic schema validation
        try:
            passage = BenchmarkPassage.model_validate(record)
        except ValidationError as exc:
            pid = record.get("passage_id")
            for pydantic_err in exc.errors():
                field = " -> ".join(str(loc) for loc in pydantic_err["loc"])
                msg = pydantic_err["msg"]
                logger.warning(
                    "Line %d (passage_id=%r): Validation error on '%s': %s",
                    line_number, pid, field, msg,
                )
                snippet = json.dumps(record)[:100] + ("…" if len(json.dumps(record)) > 100 else "")
                errors.append(
                    RecordValidationError(
                        line_number=line_number,
                        passage_id=pid,
                        field=field if field else None,
                        error_message=msg,
                        raw_snippet=snippet,
                    )
                )
            continue

        # Duplicate ID detection
        pid = passage.passage_id
        if pid in seen_ids:
            msg = (
                f"Duplicate passage_id '{pid}' first seen on line {seen_ids[pid]}, "
                f"repeated on line {line_number}."
            )
            logger.warning(msg)
            errors.append(
                RecordValidationError(
                    line_number=line_number,
                    passage_id=pid,
                    error_message=msg,
                )
            )
            if pid not in duplicate_ids:
                duplicate_ids.append(pid)
            continue

        seen_ids[pid] = line_number
        category_counts[passage.category.value] = (
            category_counts.get(passage.category.value, 0) + 1
        )
        valid_count += 1

    is_valid = len(errors) == 0
    report = ValidationReport(
        is_valid=is_valid,
        total_records=total_count,
        valid_records=valid_count,
        invalid_records=total_count - valid_count,
        duplicate_ids=duplicate_ids,
        category_counts=category_counts,
        errors=errors,
    )

    if is_valid:
        logger.info(
            "Validation PASSED: %d/%d records valid, %d categories.",
            valid_count, total_count, len(category_counts),
        )
    else:
        logger.error(
            "Validation FAILED: %d valid, %d invalid, %d duplicates out of %d records.",
            valid_count, total_count - valid_count, len(duplicate_ids), total_count,
        )

    return report


def load_passages(
    dataset_path: Path,
    settings: Optional[Settings] = None,
) -> List[BenchmarkPassage]:
    """
    Load and return only the valid passages from a JSONL file.

    Invalid or duplicate records are logged and skipped; they do NOT raise.
    Call :func:`validate_dataset` for a full error report.

    Args:
        dataset_path: Absolute path to the ``.jsonl`` passages file.
        settings: Optional Settings instance.

    Returns:
        List of validated :class:`~twi_lab.schemas.BenchmarkPassage` objects.
    """
    report = validate_dataset(dataset_path, settings)
    if not report.is_valid:
        logger.warning(
            "load_passages: dataset has %d invalid records; returning %d valid passages.",
            report.invalid_records, report.valid_records,
        )

    # Re-parse to return objects (only valid ones by design)
    passages: List[BenchmarkPassage] = []
    seen_ids: set[str] = set()
    for _, record, parse_error in _iter_jsonl_lines(dataset_path):
        if parse_error or record is None:
            continue
        try:
            passage = BenchmarkPassage.model_validate(record)
            if passage.passage_id not in seen_ids:
                passages.append(passage)
                seen_ids.add(passage.passage_id)
        except ValidationError:
            pass

    return passages


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _print_report(report: ValidationReport, verbose: bool = False) -> None:
    """Print a human-readable validation summary to stdout."""
    sep = "-" * 60
    print(sep)
    print("  TWI TRANSLATION BENCHMARK -- DATASET VALIDATION REPORT")
    print(sep)
    print(f"  Status         : {'PASSED' if report.is_valid else 'FAILED'}")
    print(f"  Total records  : {report.total_records}")
    print(f"  Valid records  : {report.valid_records}")
    print(f"  Invalid records: {report.invalid_records}")
    print(f"  Duplicate IDs  : {len(report.duplicate_ids)}")

    if report.duplicate_ids:
        for dup in report.duplicate_ids:
            print(f"    ↳ {dup}")

    if report.category_counts:
        print()
        print("  Category counts:")
        for cat, count in sorted(report.category_counts.items()):
            print(f"    {cat:<40} {count:>3}")

    if report.errors and (verbose or not report.is_valid):
        print()
        print(f"  Errors ({len(report.errors)}):")
        for err in report.errors:
            loc = f"line {err.line_number}" if err.line_number else "unknown line"
            pid = f" | id={err.passage_id}" if err.passage_id else ""
            field = f" | field={err.field}" if err.field else ""
            print(f"    [{loc}{pid}{field}] {err.error_message}")
            if verbose and err.raw_snippet:
                print(f"      snippet: {err.raw_snippet}")

    print(sep)


def cli(argv: Optional[List[str]] = None) -> None:
    """
    Command-line entry point for dataset validation.

    Exit codes:
        0  Validation passed.
        1  Validation failed (invalid records, duplicates, or missing file).
        2  Configuration or argument error.
    """
    parser = argparse.ArgumentParser(
        prog="python -m twi_lab.dataset",
        description="Validate the Twi Translation Benchmark JSONL dataset.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        required=True,
        help="Run dataset validation (required).",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to the passages JSONL file (overrides configured default).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print full error details and raw record snippets.",
    )

    args = parser.parse_args(argv)

    try:
        settings = get_settings()
        setup_logging(level=settings.log_level)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.dataset is not None:
        dataset_path = args.dataset.resolve()
    else:
        dataset_path = settings.resolved_dataset_path

    try:
        report = validate_dataset(dataset_path, settings)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Unexpected error during validation: {exc}", file=sys.stderr)
        sys.exit(1)

    _print_report(report, verbose=args.verbose)

    sys.exit(0 if report.is_valid else 1)


if __name__ == "__main__":
    cli()
