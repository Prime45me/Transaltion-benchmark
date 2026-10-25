"""
Persistent translation cache for the Twi Translation Benchmark Lab.

Provides thread-safe, atomic-write disk caching for successful translation results.
Guarantees that:
  - Cache keys account for all inputs affecting translation (engine, version,
    source text, context strategy, supplied context, generation settings).
  - Failed, timeout, or partial translations are NEVER cached.
  - Writes are atomic to prevent cache corruption during crashes or interrupts.
  - Cache statistics and deliberate cache-clearing are fully supported.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from twi_lab.logging_config import setup_logging
from twi_lab.schemas import TranslationResult, TranslationStatus

logger = setup_logging()


def compute_cache_key(
    engine_name: str,
    engine_version: Optional[str],
    source_text: str,
    context_strategy: str = "none",
    supplied_context: Optional[str] = None,
    generation_settings: Optional[Dict[str, Any]] = None,
    model_identifier: Optional[str] = None,
) -> str:
    """
    Compute a deterministic SHA-256 cache key from all inputs that affect translation.

    Any variation in source text, context strategy, supplied context, engine version,
    or generation hyperparameters produces a distinct key.
    """
    key_dict = {
        "engine_name": engine_name.strip().lower(),
        "engine_version": str(engine_version or "").strip(),
        "model_identifier": str(model_identifier or "").strip(),
        "source_text": source_text.strip(),
        "context_strategy": context_strategy.strip().lower(),
        "supplied_context": str(supplied_context or "").strip(),
        "generation_settings": generation_settings or {},
    }
    serialized = json.dumps(key_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class TranslationCache:
    """
    Persistent, atomic disk cache for translation results.

    Stores TranslationResult dictionaries keyed by their SHA-256 input hash.
    Safe against corruption via temporary-file swap on write.
    """

    def __init__(self, cache_file: Path | str) -> None:
        self.cache_file = Path(cache_file).resolve()
        self._lock = threading.Lock()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._hits = 0
        self._misses = 0
        self._load()

    def _load(self) -> None:
        """Load cache entries from disk if the file exists."""
        with self._lock:
            if not self.cache_file.exists():
                self._cache = {}
                return
            try:
                data = json.loads(self.cache_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._cache = data
                    logger.debug(
                        "Loaded %d entries from translation cache (%s)",
                        len(self._cache), self.cache_file,
                    )
                else:
                    logger.warning("Cache file %s malformed; starting empty.", self.cache_file)
                    self._cache = {}
            except Exception as exc:
                logger.error("Failed to read cache file %s: %s", self.cache_file, exc)
                self._cache = {}

    def _save(self) -> None:
        """Atomically persist cache entries to disk using a temp file."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        # Write to temp file in the same directory so os.replace is an atomic rename
        temp_dir = self.cache_file.parent
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=temp_dir,
            delete=False,
            encoding="utf-8",
            suffix=".tmp",
        ) as tf:
            temp_name = tf.name
            json.dump(self._cache, tf, indent=2, ensure_ascii=False)

        try:
            os.replace(temp_name, self.cache_file)
        except Exception:
            if os.path.exists(temp_name):
                os.remove(temp_name)
            raise

    def get(self, cache_key: str) -> Optional[TranslationResult]:
        """
        Retrieve a cached TranslationResult by its cache key.

        Returns None on miss. Updates hit/miss counters.
        """
        with self._lock:
            if cache_key in self._cache:
                self._hits += 1
                try:
                    record = self._cache[cache_key]
                    result = TranslationResult.model_validate(record)
                    logger.debug("Cache HIT for key %s", cache_key[:12])
                    return result
                except Exception as exc:
                    logger.warning("Invalid cache record for %s: %s", cache_key[:12], exc)
                    del self._cache[cache_key]
            self._misses += 1
            return None

    def has(self, cache_key: str) -> bool:
        """Check if a cache key exists without updating hit/miss counters."""
        with self._lock:
            return cache_key in self._cache

    def set(self, cache_key: str, result: TranslationResult) -> None:
        """
        Store a successful TranslationResult in the cache and persist to disk.

        Does NOT cache failed, timeout, or partial results.
        """
        if result.status != TranslationStatus.SUCCESS:
            logger.debug(
                "Skipping cache for non-success result %s (status=%s)",
                result.result_id, result.status,
            )
            return

        with self._lock:
            self._cache[cache_key] = result.model_dump(mode="json")
            try:
                self._save()
                logger.debug("Cached result %s under key %s", result.result_id, cache_key[:12])
            except Exception as exc:
                logger.error("Failed to save cache to disk: %s", exc)

    def stats(self) -> Dict[str, Any]:
        """Return cache usage and footprint statistics."""
        with self._lock:
            size_bytes = self.cache_file.stat().st_size if self.cache_file.exists() else 0
            return {
                "file_path": str(self.cache_file),
                "total_entries": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "size_bytes": size_bytes,
                "size_kb": round(size_bytes / 1024.0, 2),
            }

    def clear(self) -> int:
        """
        Deliberately clear all entries from cache and disk.

        Returns:
            The number of entries cleared.
        """
        with self._lock:
            count = len(self._cache)
            self._cache = {}
            self._hits = 0
            self._misses = 0
            if self.cache_file.exists():
                try:
                    self.cache_file.unlink()
                except Exception as exc:
                    logger.error("Failed to delete cache file %s: %s", self.cache_file, exc)
            logger.info("Cleared %d entries from translation cache (%s)", count, self.cache_file)
            return count
