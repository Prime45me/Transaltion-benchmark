"""
Experiment runner for the Twi Translation Benchmark Lab.

Orchestrates translation experiments: loads passages, evaluates narrative context
strategies, budgets and deduplicates engine calls, enforces persistent disk caching,
records TranslationResult objects, and persists an ExperimentRun manifest.

Usage (CLI):
    python -m twi_lab.runner --engine opus-mt --title "Baseline run"
    python -m twi_lab.runner --engine khaya   --title "Khaya baseline" --confirm-live-khaya
    python -m twi_lab.runner --engine all     --title "Context comparison" --context-strategy all --dry-run
    python -m twi_lab.runner --cache-stats
    python -m twi_lab.runner --clear-cache

Output files written to results/:
    experiment_<id>.json       — ExperimentRun record (metadata + summary)
    results_<id>.jsonl         — One TranslationResult JSON object per line
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from twi_lab.cache import TranslationCache, compute_cache_key
from twi_lab.config import Settings, get_settings
from twi_lab.context import ContextManager, ContextStrategyType
from twi_lab.dataset import load_passages
from twi_lab.engines.base import EngineAdapter
from twi_lab.logging_config import setup_logging
from twi_lab.schemas import (
    BenchmarkPassage,
    ExperimentRun,
    ExperimentStatus,
    TranslationResult,
    TranslationStatus,
)

logger = setup_logging()


class BudgetExceededError(RuntimeError):
    """Raised when estimated live API calls exceed the configured budget."""


class LiveCallConfirmationError(RuntimeError):
    """Raised when live API calls require confirmation but none was given."""


@dataclass
class PlannedRequest:
    """Planned translation unit before cache lookup and dispatch."""

    passage: BenchmarkPassage
    engine: EngineAdapter
    strategy: str
    supplied_context: Optional[str]
    context_metadata: Dict[str, Any]
    cache_key: str


# ---------------------------------------------------------------------------
# Core experiment runner
# ---------------------------------------------------------------------------


def run_experiment(
    engines: List[EngineAdapter],
    *,
    dataset_path: Path,
    experiment_title: str,
    context_strategy: str = "none",
    selected_passage_ids: Optional[List[str]] = None,
    generation_settings: Optional[dict] = None,
    results_dir: Optional[Path] = None,
    settings: Optional[Settings] = None,
    dry_run: bool = False,
    window_k: int = 1,
    summaries_path: Optional[Path] = None,
    glossary_path: Optional[Path] = None,
    khaya_budget: Optional[int] = None,
    confirm_live_khaya: bool = False,
    cache_only: bool = False,
    cache_file: Optional[Path] = None,
) -> ExperimentRun:
    """
    Run a translation experiment over a passage dataset with one or more engines.

    Incorporates Phase 3 context strategies, Khaya API budgeting, persistent
    disk caching, and pre-dispatch deduplication.

    Args:
        engines:              Adapter instances to evaluate.
        dataset_path:         Path to the benchmark JSONL passages file.
        experiment_title:     Short human-readable label for this run.
        context_strategy:     Strategy: 'none', 'window_k', 'story_summary',
                              'glossary_guided', or 'all'.
        selected_passage_ids: Run only these passage IDs; None = all passages.
        generation_settings:  Engine hyperparameters forwarded to adapters.
        results_dir:          Output directory. Defaults to resolved_results_dir.
        settings:             Settings instance. Defaults to singleton.
        dry_run:              If True, calculate usage and plan with zero engine calls.
        window_k:             Sentence window size for 'window_k' strategy.
        summaries_path:       Path to story summaries JSON.
        glossary_path:        Path to approved glossary JSON.
        khaya_budget:         Maximum allowed live Khaya calls for this run.
        confirm_live_khaya:   Explicit authorization flag for live Khaya calls.
        cache_only:           If True, abort if any live API/engine call is needed.
        cache_file:           Custom cache JSON path (defaults to config).

    Returns:
        The completed (or failed) ExperimentRun Pydantic model.
    """
    if settings is None:
        settings = get_settings()

    results_dir = Path(results_dir or settings.resolved_results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    cache_path = Path(cache_file or settings.resolved_cache_path)
    cache = TranslationCache(cache_path)

    experiment_id = str(uuid4())
    engine_names = [e.engine_name for e in engines]
    gen = generation_settings or {}

    # 1. Load passages
    passages = load_passages(dataset_path, settings)
    if selected_passage_ids:
        id_set = set(selected_passage_ids)
        passages = [p for p in passages if p.passage_id in id_set]
        logger.info("Passage filter applied — %d passages selected.", len(passages))
    else:
        logger.info("Running all %d passages.", len(passages))

    # 2. Determine strategies to evaluate
    if context_strategy.lower() == "all":
        eval_strategies = [s.value for s in ContextStrategyType]
    else:
        eval_strategies = [context_strategy.lower()]

    # 3. Context manager initialization
    summs_p = summaries_path or settings.resolved_summaries_path
    gloss_p = glossary_path or settings.resolved_glossary_path
    context_mgr = ContextManager.load_from_files(
        passages=passages,
        summaries_path=summs_p,
        glossary_path=gloss_p,
    )

    # 4. Pre-flight planning: build list of all planned requests
    planned_requests: List[PlannedRequest] = []
    for passage in passages:
        for engine in engines:
            for strat in eval_strategies:
                ctx_text, ctx_meta = context_mgr.build_context(
                    passage, strategy=strat, window_k=window_k
                )
                model_id = getattr(engine, "_model_name", None) or getattr(
                    engine, "model_identifier", None
                )
                key = compute_cache_key(
                    engine_name=engine.engine_name,
                    engine_version=engine.engine_version,
                    source_text=passage.english,
                    context_strategy=strat,
                    supplied_context=ctx_text,
                    generation_settings=gen,
                    model_identifier=model_id,
                )
                planned_requests.append(
                    PlannedRequest(
                        passage=passage,
                        engine=engine,
                        strategy=strat,
                        supplied_context=ctx_text,
                        context_metadata=ctx_meta,
                        cache_key=key,
                    )
                )

    # 5. Deduplication and cache pre-flight analysis
    seen_keys: set[str] = set()
    unique_requests: List[PlannedRequest] = []
    duplicate_count = 0

    for req in planned_requests:
        if req.cache_key in seen_keys:
            duplicate_count += 1
        else:
            seen_keys.add(req.cache_key)
            unique_requests.append(req)

    cached_unique_count = 0
    uncached_khaya_calls = 0
    uncached_other_calls = 0

    for req in unique_requests:
        if cache.has(req.cache_key):
            cached_unique_count += 1
        else:
            if req.engine.engine_name == "khaya":
                uncached_khaya_calls += 1
            else:
                uncached_other_calls += 1

    total_planned = len(planned_requests)
    estimated_cache_hits = duplicate_count + cached_unique_count
    saved_by_cache = cached_unique_count
    saved_by_dedup = duplicate_count
    effective_khaya_budget = (
        khaya_budget if khaya_budget is not None else settings.khaya_call_budget
    )
    permitted_to_proceed = uncached_khaya_calls <= effective_khaya_budget

    logger.info(
        "Pre-flight analysis: %d planned records, %d unique requests, "
        "%d cached, %d duplicate reuses, %d estimated live Khaya calls (Budget: %d)",
        total_planned,
        len(unique_requests),
        cached_unique_count,
        duplicate_count,
        uncached_khaya_calls,
        effective_khaya_budget,
    )

    exp_file = results_dir / f"experiment_{experiment_id}.json"

    # 6. Budget enforcement (checked before any network call or model execution)
    if uncached_khaya_calls > effective_khaya_budget:
        msg = (
            f"Estimated live Khaya API calls ({uncached_khaya_calls}) exceeds "
            f"configured budget ({effective_khaya_budget}). "
            f"Experiment aborted before making any calls."
        )
        logger.error(msg)
        raise BudgetExceededError(msg)

    # 7. Cache-only enforcement
    if cache_only and (uncached_khaya_calls + uncached_other_calls) > 0:
        msg = (
            f"Cache-only mode requested but "
            f"{uncached_khaya_calls + uncached_other_calls} live calls are required."
        )
        logger.error(msg)
        raise RuntimeError(msg)

    # 8. Live Khaya confirmation enforcement
    if uncached_khaya_calls > 0 and not confirm_live_khaya and not dry_run:
        msg = (
            f"Live Khaya API calls require explicit authorization (--confirm-live-khaya). "
            f"Estimated live calls: {uncached_khaya_calls}, Budget: {effective_khaya_budget}."
        )
        logger.error(msg)
        raise LiveCallConfirmationError(msg)

    # 9. Handle Dry Run
    if dry_run:
        logger.info("Dry run — zero live API calls and zero inference executed.")
        experiment = ExperimentRun(
            experiment_id=experiment_id,
            title=experiment_title,
            dataset_version="0.1.0",
            dataset_path=str(dataset_path),
            engines=engine_names,
            context_strategy=context_strategy,
            selected_passage_ids=selected_passage_ids or [],
            configuration={
                "generation_settings": gen,
                "dry_run": True,
                "window_k": window_k,
                "khaya_budget": effective_khaya_budget,
            },
            status=ExperimentStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            summary_metrics={
                "dry_run": True,
                "engines": engine_names,
                "total_planned_records": total_planned,
                "unique_requests": len(unique_requests),
                "estimated_cache_hits": estimated_cache_hits,
                "estimated_live_khaya_calls": uncached_khaya_calls,
                "estimated_live_other_calls": uncached_other_calls,
                "khaya_budget": effective_khaya_budget,
                "permitted_to_proceed": permitted_to_proceed,
                "saved_by_cache": saved_by_cache,
                "saved_by_deduplication": saved_by_dedup,
            },
        )
        _write_json(exp_file, experiment.model_dump(mode="json"))
        return experiment

    # 10. Execute Live Experiment
    experiment = ExperimentRun(
        experiment_id=experiment_id,
        title=experiment_title,
        dataset_version="0.1.0",
        dataset_path=str(dataset_path),
        engines=engine_names,
        context_strategy=context_strategy,
        selected_passage_ids=selected_passage_ids or [],
        configuration={
            "generation_settings": gen,
            "dry_run": False,
            "window_k": window_k,
            "khaya_budget": effective_khaya_budget,
        },
        status=ExperimentStatus.RUNNING,
    )
    _write_json(exp_file, experiment.model_dump(mode="json"))

    results_file = results_dir / f"results_{experiment_id}.jsonl"
    total = 0
    success_count = 0
    failed_count = 0
    timeout_count = 0
    live_calls: Dict[str, int] = {name: 0 for name in engine_names}
    cache_hits_total = 0
    elapsed_sums: Dict[str, float] = {name: 0.0 for name in engine_names}
    elapsed_counts: Dict[str, int] = {name: 0 for name in engine_names}

    # Store executed results by cache key for in-run deduplication reuse
    results_by_key: Dict[str, TranslationResult] = {}

    try:
        with open(results_file, "w", encoding="utf-8") as fh:
            for req in planned_requests:
                # Case A: Duplicate within this run
                if req.cache_key in results_by_key:
                    orig = results_by_key[req.cache_key]
                    result = orig.model_copy(
                        update={
                            "result_id": str(uuid4()),
                            "experiment_id": experiment_id,
                            "story_id": req.passage.story_id,
                            "passage_id": req.passage.passage_id,
                            "is_cache_hit": True,
                        }
                    )
                    cache_hits_total += 1
                # Case B: Exists in persistent disk cache
                elif cache.has(req.cache_key):
                    cached_res = cache.get(req.cache_key)
                    if cached_res is not None:
                        result = cached_res.model_copy(
                            update={
                                "result_id": str(uuid4()),
                                "experiment_id": experiment_id,
                                "story_id": req.passage.story_id,
                                "passage_id": req.passage.passage_id,
                                "is_cache_hit": True,
                            }
                        )
                        results_by_key[req.cache_key] = result
                        cache_hits_total += 1
                    else:
                        # Fallback if corrupted entry was dropped
                        result = req.engine.translate(
                            source_text=req.passage.english,
                            experiment_id=experiment_id,
                            story_id=req.passage.story_id,
                            passage_id=req.passage.passage_id,
                            context_strategy=req.strategy,
                            supplied_context=req.supplied_context,
                            generation_settings=gen if gen else None,
                        )
                        result.context_metadata = req.context_metadata
                        result.is_cache_hit = False
                        live_calls[req.engine.engine_name] += 1
                        if result.status == TranslationStatus.SUCCESS:
                            cache.set(req.cache_key, result)
                        results_by_key[req.cache_key] = result
                # Case C: Uncached live request
                else:
                    result = req.engine.translate(
                        source_text=req.passage.english,
                        experiment_id=experiment_id,
                        story_id=req.passage.story_id,
                        passage_id=req.passage.passage_id,
                        context_strategy=req.strategy,
                        supplied_context=req.supplied_context,
                        generation_settings=gen if gen else None,
                    )
                    result.context_metadata = req.context_metadata
                    result.is_cache_hit = False
                    live_calls[req.engine.engine_name] += 1
                    if result.status == TranslationStatus.SUCCESS:
                        cache.set(req.cache_key, result)
                    results_by_key[req.cache_key] = result

                fh.write(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))
                fh.write("\n")
                total += 1

                if result.status == TranslationStatus.SUCCESS:
                    success_count += 1
                elif result.status == TranslationStatus.TIMEOUT:
                    timeout_count += 1
                    failed_count += 1
                else:
                    failed_count += 1

                if result.elapsed_time_ms is not None:
                    elapsed_sums[req.engine.engine_name] += result.elapsed_time_ms
                    elapsed_counts[req.engine.engine_name] += 1

        experiment.status = ExperimentStatus.COMPLETED
        experiment.completed_at = datetime.now(timezone.utc)
        experiment.summary_metrics = {
            "total_results": total,
            "success_count": success_count,
            "failed_count": failed_count,
            "timeout_count": timeout_count,
            "passage_count": len(passages),
            "live_calls": live_calls,
            "cache_hits": cache_hits_total,
            "dedup_saved": duplicate_count,
            "khaya_budget": effective_khaya_budget,
            "khaya_budget_used": live_calls.get("khaya", 0),
            "avg_elapsed_ms": {
                name: (
                    round(elapsed_sums[name] / elapsed_counts[name], 2)
                    if elapsed_counts[name]
                    else None
                )
                for name in engine_names
            },
            "results_file": str(results_file),
        }

    except Exception as exc:
        logger.error("Experiment %s failed unexpectedly: %s", experiment_id, exc)
        experiment.status = ExperimentStatus.FAILED
        experiment.completed_at = datetime.now(timezone.utc)
        experiment.summary_metrics = {
            "error": str(exc),
            "exception_type": type(exc).__name__,
        }

    _write_json(exp_file, experiment.model_dump(mode="json"))
    logger.info(
        "Experiment %s %s — %d total, %d success, %d failed (%d timeout). "
        "Live calls: %s, Cache hits: %d",
        experiment_id,
        experiment.status.value,
        total,
        success_count,
        failed_count,
        timeout_count,
        live_calls,
        cache_hits_total,
    )
    return experiment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: dict) -> None:
    """Atomically write data as pretty-printed JSON to path."""
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def cli(argv: Optional[List[str]] = None) -> None:
    """
    Command-line entry point for running translation experiments.

    Exit codes:
        0  Experiment or cache operation completed successfully.
        1  Experiment failed or engine error.
        2  Argument, configuration, or budget confirmation error.
    """
    parser = argparse.ArgumentParser(
        prog="python -m twi_lab.runner",
        description="Run a Twi Translation Benchmark experiment with context and caching.",
    )
    parser.add_argument(
        "--engine",
        choices=["opus-mt", "khaya", "all"],
        default=None,
        help="Translation engine(s) to run (required unless managing cache).",
    )
    parser.add_argument(
        "--title",
        default="Benchmark experiment",
        help="Short human-readable experiment title.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to passages JSONL (overrides config default).",
    )
    parser.add_argument(
        "--context-strategy",
        default="none",
        choices=["none", "window_k", "story_summary", "glossary_guided", "all"],
        dest="context_strategy",
        help="Context strategy to evaluate (none, window_k, story_summary, glossary_guided, all).",
    )
    parser.add_argument(
        "--window-k",
        type=int,
        default=1,
        help="Number of preceding sentences for 'window_k' strategy (default: 1).",
    )
    parser.add_argument(
        "--summaries",
        type=Path,
        default=None,
        help="Path to story summaries JSON (default: config resolved_summaries_path).",
    )
    parser.add_argument(
        "--glossary",
        type=Path,
        default=None,
        help="Path to approved glossary JSON (default: config resolved_glossary_path).",
    )
    parser.add_argument(
        "--khaya-budget",
        type=int,
        default=None,
        help="Maximum allowed live Khaya API calls (default: config khaya_call_budget).",
    )
    parser.add_argument(
        "--confirm-live-khaya",
        action="store_true",
        help="Explicit confirmation required to execute live Khaya API requests.",
    )
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Only serve translations from cache; abort if live calls are needed.",
    )
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=None,
        help="Path to persistent translation cache JSON.",
    )
    parser.add_argument(
        "--cache-stats",
        action="store_true",
        help="Display cache statistics and exit.",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Deliberately clear all entries in the persistent translation cache and exit.",
    )
    parser.add_argument(
        "--passages",
        nargs="+",
        default=None,
        metavar="PASSAGE_ID",
        help="Limit run to specific passage IDs (default: all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and show usage estimates without executing engine calls.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help="Output directory for results (overrides config default).",
    )

    args = parser.parse_args(argv)

    try:
        settings = get_settings()
        setup_logging(level=settings.log_level)
    except Exception as exc:
        print(f"[ERROR] Configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    cache_target = args.cache_file or settings.resolved_cache_path

    # Cache inspection / deliberate clearing commands
    if args.cache_stats:
        c = TranslationCache(cache_target)
        st = c.stats()
        print(f"Translation Cache Statistics ({st['file_path']}):")
        print(f"  Total entries : {st['total_entries']}")
        print(f"  Cache hits    : {st['hits']}")
        print(f"  Cache misses  : {st['misses']}")
        print(f"  File size     : {st['size_kb']} KB ({st['size_bytes']} bytes)")
        sys.exit(0)

    if args.clear_cache:
        c = TranslationCache(cache_target)
        cleared = c.clear()
        print(f"Cleared {cleared} entries from translation cache ({cache_target}).")
        sys.exit(0)

    # Engine is required for experiment runs
    if not args.engine:
        print(
            "[ERROR] the following arguments are required: --engine",
            file=sys.stderr,
        )
        sys.exit(2)

    dataset_path = (
        args.dataset.resolve() if args.dataset else settings.resolved_dataset_path
    )
    results_dir = (
        args.results_dir.resolve() if args.results_dir else settings.resolved_results_dir
    )

    # Build engine adapter list
    adapters: List[EngineAdapter] = []
    try:
        if args.engine in ("opus-mt", "all"):
            from twi_lab.engines.opus_mt import OPUSMTAdapter

            adapters.append(OPUSMTAdapter())
        if args.engine in ("khaya", "all"):
            from twi_lab.engines.khaya import KhayaAdapter

            adapters.append(KhayaAdapter())
    except Exception as exc:
        print(f"[ERROR] Failed to initialise engine adapter: {exc}", file=sys.stderr)
        sys.exit(2)

    if not adapters:
        print("[ERROR] No engine adapters were created.", file=sys.stderr)
        sys.exit(2)

    try:
        experiment = run_experiment(
            engines=adapters,
            dataset_path=dataset_path,
            experiment_title=args.title,
            context_strategy=args.context_strategy,
            selected_passage_ids=args.passages,
            results_dir=results_dir,
            settings=settings,
            dry_run=args.dry_run,
            window_k=args.window_k,
            summaries_path=args.summaries,
            glossary_path=args.glossary,
            khaya_budget=args.khaya_budget,
            confirm_live_khaya=args.confirm_live_khaya,
            cache_only=args.cache_only,
            cache_file=args.cache_file,
        )
    except (BudgetExceededError, LiveCallConfirmationError) as exc:
        print(f"\n[BUDGET / SAFETY ERROR] {exc}\n", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"[ERROR] Unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)

    if experiment.status == ExperimentStatus.COMPLETED:
        print(f"\nExperiment completed: {experiment.experiment_id}")
        metrics = experiment.summary_metrics
        if metrics.get("dry_run"):
            print("  Mode                      : DRY RUN (no live calls made)")
            print(f"  Total planned records     : {metrics.get('total_planned_records')}")
            print(f"  Unique requests           : {metrics.get('unique_requests')}")
            print(f"  Estimated cache hits      : {metrics.get('estimated_cache_hits')}")
            print(f"  Estimated live Khaya calls: {metrics.get('estimated_live_khaya_calls')}")
            print(f"  Calls saved by cache      : {metrics.get('saved_by_cache')}")
            print(f"  Calls saved by deduplication: {metrics.get('saved_by_deduplication')}")
            print(f"  Configured Khaya budget   : {metrics.get('khaya_budget')}")
            print(f"  Permitted to proceed      : {metrics.get('permitted_to_proceed')}")
        else:
            print(f"  Total results   : {metrics.get('total_results', 0)}")
            print(f"  Success         : {metrics.get('success_count', 0)}")
            print(f"  Failed          : {metrics.get('failed_count', 0)}")
            print(f"  Timeout         : {metrics.get('timeout_count', 0)}")
            print(f"  Live calls      : {metrics.get('live_calls', {})}")
            print(f"  Cache hits      : {metrics.get('cache_hits', 0)}")
            print(f"  Dedup saved     : {metrics.get('dedup_saved', 0)}")
            print(f"  Results file    : {metrics.get('results_file', 'N/A')}")
        sys.exit(0)
    else:
        print(f"\nExperiment FAILED: {experiment.experiment_id}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli()
