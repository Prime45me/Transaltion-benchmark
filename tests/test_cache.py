"""
Unit tests for TranslationCache and compute_cache_key (src/twi_lab/cache.py).
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from twi_lab.cache import TranslationCache, compute_cache_key
from twi_lab.schemas import TranslationResult, TranslationStatus


# ---------------------------------------------------------------------------
# compute_cache_key tests
# ---------------------------------------------------------------------------


class TestComputeCacheKey:

    def test_cache_key_is_deterministic(self):
        k1 = compute_cache_key(
            engine_name="khaya",
            engine_version="0.1.0",
            source_text="The sun rose slowly.",
            context_strategy="none",
            supplied_context=None,
        )
        k2 = compute_cache_key(
            engine_name="khaya",
            engine_version="0.1.0",
            source_text="The sun rose slowly.",
            context_strategy="none",
            supplied_context=None,
        )
        assert k1 == k2
        assert len(k1) == 64  # SHA-256 hex digest length

    def test_cache_key_differs_on_context_strategy(self):
        k1 = compute_cache_key(
            engine_name="khaya",
            engine_version="0.1.0",
            source_text="The sun rose.",
            context_strategy="none",
        )
        k2 = compute_cache_key(
            engine_name="khaya",
            engine_version="0.1.0",
            source_text="The sun rose.",
            context_strategy="window_k",
        )
        assert k1 != k2

    def test_cache_key_differs_on_supplied_context(self):
        k1 = compute_cache_key(
            engine_name="khaya",
            engine_version="0.1.0",
            source_text="The sun rose.",
            context_strategy="window_k",
            supplied_context="Morning began.",
        )
        k2 = compute_cache_key(
            engine_name="khaya",
            engine_version="0.1.0",
            source_text="The sun rose.",
            context_strategy="window_k",
            supplied_context="Night ended.",
        )
        assert k1 != k2

    def test_cache_key_differs_on_source_text(self):
        k1 = compute_cache_key(engine_name="khaya", engine_version="0.1.0", source_text="Text A")
        k2 = compute_cache_key(engine_name="khaya", engine_version="0.1.0", source_text="Text B")
        assert k1 != k2

    def test_cache_key_differs_on_generation_settings(self):
        k1 = compute_cache_key(
            engine_name="opus-mt",
            engine_version="0.1.0",
            source_text="Text",
            generation_settings={"num_beams": 4},
        )
        k2 = compute_cache_key(
            engine_name="opus-mt",
            engine_version="0.1.0",
            source_text="Text",
            generation_settings={"num_beams": 8},
        )
        assert k1 != k2

    def test_cache_key_differs_on_engine_or_version(self):
        k1 = compute_cache_key(engine_name="opus-mt", engine_version="0.1.0", source_text="Text")
        k2 = compute_cache_key(engine_name="khaya", engine_version="0.1.0", source_text="Text")
        k3 = compute_cache_key(engine_name="opus-mt", engine_version="0.2.0", source_text="Text")
        assert k1 != k2
        assert k1 != k3


# ---------------------------------------------------------------------------
# TranslationCache operational tests
# ---------------------------------------------------------------------------


class TestTranslationCacheOperations:

    @pytest.fixture
    def cache_path(self, tmp_path: Path) -> Path:
        return tmp_path / "cache" / "test_cache.json"

    @pytest.fixture
    def cache(self, cache_path: Path) -> TranslationCache:
        return TranslationCache(cache_path)

    def _sample_result(self, status: TranslationStatus = TranslationStatus.SUCCESS) -> TranslationResult:
        return TranslationResult(
            experiment_id=str(uuid4()),
            story_id="STORY-001",
            passage_id="STORY-001-P01",
            engine_name="khaya",
            engine_version="0.1.0",
            source_text="The sun rose.",
            translated_text="Owia puei." if status == TranslationStatus.SUCCESS else None,
            status=status,
            context_strategy="none",
        )

    def test_cache_get_and_set_roundtrip(self, cache: TranslationCache):
        result = self._sample_result()
        key = "test_key_123"

        assert cache.has(key) is False
        assert cache.get(key) is None

        cache.set(key, result)

        assert cache.has(key) is True
        cached = cache.get(key)
        assert cached is not None
        assert cached.translated_text == "Owia puei."
        assert cached.passage_id == "STORY-001-P01"

    def test_cache_hits_and_misses_stats(self, cache: TranslationCache):
        res = self._sample_result()
        key = "stat_key"
        cache.set(key, res)

        _ = cache.get(key)  # hit
        _ = cache.get(key)  # hit
        _ = cache.get("missing_key")  # miss

        stats = cache.stats()
        assert stats["total_entries"] == 1
        assert stats["hits"] == 2
        assert stats["misses"] == 1

    def test_non_success_results_never_cached(self, cache: TranslationCache):
        failed_res = self._sample_result(status=TranslationStatus.FAILED)
        timeout_res = self._sample_result(status=TranslationStatus.TIMEOUT)
        partial_res = self._sample_result(status=TranslationStatus.PARTIAL)

        cache.set("k_failed", failed_res)
        cache.set("k_timeout", timeout_res)
        cache.set("k_partial", partial_res)

        assert cache.has("k_failed") is False
        assert cache.has("k_timeout") is False
        assert cache.has("k_partial") is False
        assert cache.stats()["total_entries"] == 0

    def test_cache_persists_across_instances(self, cache_path: Path):
        cache1 = TranslationCache(cache_path)
        res = TranslationResult(
            experiment_id=str(uuid4()),
            story_id="STORY-001",
            passage_id="P01",
            engine_name="khaya",
            engine_version="0.1.0",
            source_text="Hello",
            translated_text="Akwaaba",
            status=TranslationStatus.SUCCESS,
        )
        cache1.set("persisted_key", res)

        # Load fresh cache instance from the same disk file
        cache2 = TranslationCache(cache_path)
        assert cache2.has("persisted_key") is True
        loaded = cache2.get("persisted_key")
        assert loaded is not None
        assert loaded.translated_text == "Akwaaba"

    def test_clear_cache(self, cache: TranslationCache, cache_path: Path):
        cache.set("k1", self._sample_result())
        cache.set("k2", self._sample_result())
        assert cache.stats()["total_entries"] == 2
        assert cache_path.exists()

        cleared_count = cache.clear()
        assert cleared_count == 2
        assert cache.stats()["total_entries"] == 0
        assert cache_path.exists() is False

    def test_malformed_cache_file_loads_empty_without_crashing(self, cache_path: Path):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("CORRUPTED NOT JSON {{{", encoding="utf-8")

        # Must not raise
        cache = TranslationCache(cache_path)
        assert cache.stats()["total_entries"] == 0
