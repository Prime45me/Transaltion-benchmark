"""
Context strategy framework for the Twi Translation Benchmark Lab (Phase 3).

Implements four narrative context strategies behind a unified interface:
  - 'none'           : Baseline — passage translated in isolation.
  - 'window_k'       : Preceding k sentences from the same story.
  - 'story_summary'  : Concise, stable pre-existing story summary.
  - 'glossary_guided': Approved character-name and domain term definitions.

Critical design guarantees:
  - Original passage english source is NEVER mutated.
  - 'window_k' NEVER includes future sentences or sentences from other stories.
  - Missing summaries or empty glossaries are handled explicitly without API calls.
  - Full provenance (glossary hash, sentence count, context strategy) is recorded.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from twi_lab.logging_config import setup_logging
from twi_lab.schemas import BenchmarkPassage

logger = setup_logging()

# Sentence splitter regex: splits on punctuation followed by whitespace and capital letter / quote
_SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'“])")


class ContextStrategyType(str, Enum):
    """Supported context evaluation strategies."""

    NONE = "none"
    WINDOW_K = "window_k"
    STORY_SUMMARY = "story_summary"
    GLOSSARY_GUIDED = "glossary_guided"


def split_sentences(text: str) -> List[str]:
    """
    Split a text paragraph into sentences while preserving order and content.
    Handles basic English punctuation (. ! ?) and dialogue quotation marks.
    """
    cleaned = text.strip()
    if not cleaned:
        return []
    sentences = [s.strip() for s in _SENTENCE_SPLIT_REGEX.split(cleaned) if s.strip()]
    return sentences if sentences else [cleaned]


def compute_glossary_hash(glossary: Dict[str, str]) -> str:
    """Compute a deterministic short hash of glossary terms and definitions."""
    serialized = json.dumps(glossary, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]


def format_engine_input(
    source_text: str,
    supplied_context: Optional[str],
    context_strategy: str = "none",
) -> str:
    """
    Format source text and context into a uniform engine input string.

    Neither OPUS-MT nor Khaya API supports a dedicated auxiliary 'context' parameter
    in their native translation engines. To ensure a fair, honest comparison between engines,
    both receive the exact same constructed input when context is enabled:
        '[Context: <context>] <target_passage>'

    If context is absent or strategy is 'none', returns source_text unchanged.
    """
    if not supplied_context or context_strategy == ContextStrategyType.NONE.value:
        return source_text

    return f"[Context: {supplied_context}] {source_text}"


class ContextManager:
    """
    Builds context for benchmark passages according to selected strategies.

    Manages story passage ordering, sentence extraction, summary lookup,
    and glossary collation.
    """

    def __init__(
        self,
        passages: Optional[List[BenchmarkPassage]] = None,
        summaries: Optional[Dict[str, str]] = None,
        global_glossary: Optional[Dict[str, str]] = None,
        glossary_version: str = "1.0.0",
    ) -> None:
        self._passages_by_story: Dict[str, List[BenchmarkPassage]] = {}
        if passages:
            self.index_passages(passages)
        self.summaries: Dict[str, str] = summaries or {}
        self.global_glossary: Dict[str, str] = global_glossary or {}
        self.glossary_version: str = glossary_version

    def index_passages(self, passages: List[BenchmarkPassage]) -> None:
        """Group and sort passages by story_id and passage_id."""
        self._passages_by_story.clear()
        for p in passages:
            self._passages_by_story.setdefault(p.story_id, []).append(p)

        # Sort passages within each story by passage_id to guarantee narrative sequence
        for story_id in self._passages_by_story:
            self._passages_by_story[story_id].sort(key=lambda p: p.passage_id)

    @classmethod
    def load_from_files(
        cls,
        passages: Optional[List[BenchmarkPassage]] = None,
        summaries_path: Optional[Path | str] = None,
        glossary_path: Optional[Path | str] = None,
    ) -> ContextManager:
        """Factory method to load optional summaries and glossary from JSON files."""
        summaries_dict: Dict[str, str] = {}
        glossary_dict: Dict[str, str] = {}
        glossary_ver = "1.0.0"

        if summaries_path:
            p = Path(summaries_path)
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        summaries_dict = data.get("summaries", data)
                except Exception as exc:
                    logger.warning("Failed to load summaries from %s: %s", p, exc)

        if glossary_path:
            p = Path(glossary_path)
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        glossary_dict = data.get("terms", data)
                        glossary_ver = data.get("version", "1.0.0")
                except Exception as exc:
                    logger.warning("Failed to load glossary from %s: %s", p, exc)

        return cls(
            passages=passages,
            summaries=summaries_dict,
            global_glossary=glossary_dict,
            glossary_version=glossary_ver,
        )

    def build_context(
        self,
        passage: BenchmarkPassage,
        strategy: str | ContextStrategyType,
        window_k: int = 1,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Build contextual text and provenance metadata for a specific passage and strategy.

        Args:
            passage:  The target benchmark passage.
            strategy: One of 'none', 'window_k', 'story_summary', 'glossary_guided'.
            window_k: Preceding sentence count for 'window_k'.

        Returns:
            Tuple of (supplied_context_string_or_None, provenance_metadata_dict).
        """
        strat_str = str(strategy.value if isinstance(strategy, ContextStrategyType) else strategy).lower()

        if strat_str == ContextStrategyType.NONE.value:
            return None, {"strategy": "none"}

        if strat_str == ContextStrategyType.WINDOW_K.value:
            return self._build_window_k(passage, window_k=window_k)

        if strat_str == ContextStrategyType.STORY_SUMMARY.value:
            return self._build_story_summary(passage)

        if strat_str == ContextStrategyType.GLOSSARY_GUIDED.value:
            return self._build_glossary_guided(passage)

        raise ValueError(
            f"Unknown context strategy: {strategy!r}. "
            f"Must be one of {[s.value for s in ContextStrategyType]}"
        )

    # ------------------------------------------------------------------
    # Internal strategy implementations
    # ------------------------------------------------------------------

    def _build_window_k(
        self,
        passage: BenchmarkPassage,
        window_k: int = 1,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Extract preceding k sentences from earlier passages in the exact same story.

        Guarantees:
          - Never includes future sentences.
          - Never includes sentences from other stories.
          - If k <= 0 or passage is first in story, returns None.
        """
        if window_k <= 0:
            return None, {
                "strategy": "window_k",
                "k": window_k,
                "sentences_extracted": 0,
                "note": "k <= 0; no preceding context requested",
            }

        story_passages = self._passages_by_story.get(passage.story_id, [])
        # Find index of current passage within the story
        current_idx = -1
        for idx, p in enumerate(story_passages):
            if p.passage_id == passage.passage_id:
                current_idx = idx
                break

        if current_idx <= 0:
            # First passage in story or unknown story: no preceding context exists
            return None, {
                "strategy": "window_k",
                "k": window_k,
                "sentences_extracted": 0,
                "note": "First passage in story or no preceding story passages available",
            }

        # Collect sentences from preceding passages strictly in narrative order
        preceding_sentences: List[str] = []
        for p in story_passages[:current_idx]:
            sents = split_sentences(p.english)
            preceding_sentences.extend(sents)

        if not preceding_sentences:
            return None, {
                "strategy": "window_k",
                "k": window_k,
                "sentences_extracted": 0,
                "note": "No sentences found in preceding passages",
            }

        # Take the trailing k sentences
        window_sentences = preceding_sentences[-window_k:]
        context_text = " ".join(window_sentences)

        metadata = {
            "strategy": "window_k",
            "k": window_k,
            "sentences_extracted": len(window_sentences),
            "preceding_passages_count": current_idx,
            "context_char_count": len(context_text),
        }
        return context_text, metadata

    def _build_story_summary(
        self,
        passage: BenchmarkPassage,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Retrieve pre-existing story summary for the passage's story.

        If no summary exists, marks strategy unavailable rather than calling an API.
        """
        summary = self.summaries.get(passage.story_id)
        if not summary or not summary.strip():
            logger.info("No story summary available for %s", passage.story_id)
            return None, {
                "strategy": "story_summary",
                "available": False,
                "story_id": passage.story_id,
                "reason": f"No pre-authored summary found for {passage.story_id}",
            }

        cleaned = summary.strip()
        metadata = {
            "strategy": "story_summary",
            "available": True,
            "story_id": passage.story_id,
            "summary_char_count": len(cleaned),
        }
        return cleaned, metadata

    def _build_glossary_guided(
        self,
        passage: BenchmarkPassage,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Collate approved terminology and character names for the passage.

        Merges passage-specific glossary with global glossary terms that appear in english text.
        """
        combined_glossary: Dict[str, str] = {}

        # 1. Terms from the passage record itself
        if passage.glossary:
            combined_glossary.update(passage.glossary)

        # 2. Terms from global glossary if mentioned in the passage
        if self.global_glossary:
            for term, definition in self.global_glossary.items():
                if term.lower() in passage.english.lower():
                    combined_glossary[term] = definition

        if not combined_glossary:
            return None, {
                "strategy": "glossary_guided",
                "empty_glossary": True,
                "terms_count": 0,
                "note": "No approved glossary terms matched this passage",
            }

        # Format into clean deterministic string: "Term: definition; Term2: definition2"
        sorted_items = sorted(combined_glossary.items(), key=lambda x: x[0].lower())
        formatted_terms = [f"{term}: {defn}" for term, defn in sorted_items]
        context_text = "; ".join(formatted_terms)

        glossary_hash = compute_glossary_hash(combined_glossary)
        metadata = {
            "strategy": "glossary_guided",
            "empty_glossary": False,
            "terms_count": len(combined_glossary),
            "glossary_version": self.glossary_version,
            "glossary_hash": glossary_hash,
            "matched_terms": [term for term, _ in sorted_items],
        }
        return context_text, metadata
