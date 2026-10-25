"""
Unit tests for context strategy module (src/twi_lab/context.py).

Covers:
  - Sentence splitting and punctuation handling
  - Strategy 'none': baseline, untouched
  - Strategy 'window_k': boundary conditions, order preservation, story isolation, no future leakage
  - Strategy 'story_summary': lookup, missing handling without API call
  - Strategy 'glossary_guided': passage-level, global terms matching, deterministic sorting, empty glossary
  - Glossary hashing
  - Engine input formatting
  - Preservation of paragraphs by default
"""

from __future__ import annotations

import pytest

from twi_lab.context import (
    ContextManager,
    ContextStrategyType,
    compute_glossary_hash,
    format_engine_input,
    split_sentences,
)
from twi_lab.schemas import BenchmarkPassage, LinguisticCategory, ReferenceStatus, ReviewStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_passage(
    story_id: str = "STORY-001",
    passage_id: str = "STORY-001-P01",
    english: str = "The sun rose.",
    glossary: dict | None = None,
) -> BenchmarkPassage:
    return BenchmarkPassage(
        story_id=story_id,
        passage_id=passage_id,
        category=LinguisticCategory.SIMPLE_SENTENCE,
        english=english,
        glossary=glossary or {},
        reference_status=ReferenceStatus.ABSENT,
        review_status=ReviewStatus.PENDING,
    )


# ---------------------------------------------------------------------------
# split_sentences tests
# ---------------------------------------------------------------------------


class TestSentenceSplitting:

    def test_split_simple_sentences(self):
        text = "The sun rose. The birds sang merrily! A cool breeze blew."
        sents = split_sentences(text)
        assert len(sents) == 3
        assert sents[0] == "The sun rose."
        assert sents[1] == "The birds sang merrily!"
        assert sents[2] == "A cool breeze blew."

    def test_split_dialogue_sentences(self):
        text = '"Grandmother, is breakfast ready?" Ama called. "Yes, come here," she replied.'
        sents = split_sentences(text)
        assert len(sents) == 2
        assert sents[0] == '"Grandmother, is breakfast ready?" Ama called.'
        assert sents[1] == '"Yes, come here," she replied.'

    def test_split_empty_or_whitespace(self):
        assert split_sentences("") == []
        assert split_sentences("   \n\t  ") == []

    def test_split_single_sentence(self):
        text = "Only one sentence here."
        assert split_sentences(text) == [text]


# ---------------------------------------------------------------------------
# ContextStrategyType.NONE tests
# ---------------------------------------------------------------------------


class TestStrategyNone:

    def test_none_returns_no_context(self):
        p = _make_passage(english="Paragraph of text.")
        mgr = ContextManager(passages=[p])
        ctx, meta = mgr.build_context(p, strategy=ContextStrategyType.NONE)
        assert ctx is None
        assert meta["strategy"] == "none"

    def test_paragraph_preserved_intact(self):
        orig_text = "This is sentence one. This is sentence two. This is sentence three."
        p = _make_passage(english=orig_text)
        mgr = ContextManager(passages=[p])
        ctx, _ = mgr.build_context(p, strategy="none")
        # Passage object english attribute is completely untouched
        assert p.english == orig_text


# ---------------------------------------------------------------------------
# ContextStrategyType.WINDOW_K tests
# ---------------------------------------------------------------------------


class TestStrategyWindowK:

    @pytest.fixture
    def story_passages(self) -> list[BenchmarkPassage]:
        return [
            _make_passage(
                story_id="STORY-001",
                passage_id="STORY-001-P01",
                english="The sun rose over the hills.",
            ),
            _make_passage(
                story_id="STORY-001",
                passage_id="STORY-001-P02",
                english="Ama woke up. She stretched her arms wide.",
            ),
            _make_passage(
                story_id="STORY-001",
                passage_id="STORY-001-P03",
                english='"Grandmother, is breakfast ready?" Ama called.',
            ),
        ]

    def test_first_passage_in_story_has_no_preceding_context(self, story_passages):
        mgr = ContextManager(passages=story_passages)
        ctx, meta = mgr.build_context(story_passages[0], strategy="window_k", window_k=1)
        assert ctx is None
        assert meta["sentences_extracted"] == 0

    def test_preceding_k_sentences_extracted(self, story_passages):
        mgr = ContextManager(passages=story_passages)
        # P03 has preceding passages P01 (1 sent) and P02 (2 sents) = total 3 preceding sentences:
        # 1: "The sun rose over the hills."
        # 2: "Ama woke up."
        # 3: "She stretched her arms wide."

        # window_k = 1 should return the immediate last preceding sentence
        ctx_k1, meta_k1 = mgr.build_context(story_passages[2], strategy="window_k", window_k=1)
        assert ctx_k1 == "She stretched her arms wide."
        assert meta_k1["sentences_extracted"] == 1

        # window_k = 2 should return the last 2 preceding sentences
        ctx_k2, meta_k2 = mgr.build_context(story_passages[2], strategy="window_k", window_k=2)
        assert ctx_k2 == "Ama woke up. She stretched her arms wide."
        assert meta_k2["sentences_extracted"] == 2

    def test_never_includes_future_sentences(self, story_passages):
        mgr = ContextManager(passages=story_passages)
        # P02 should only see P01, NEVER P03
        ctx, _ = mgr.build_context(story_passages[1], strategy="window_k", window_k=5)
        assert "Grandmother" not in ctx
        assert ctx == "The sun rose over the hills."

    def test_never_crosses_story_boundaries(self):
        p_story1 = _make_passage(story_id="STORY-001", passage_id="STORY-001-P01", english="Story 1 sentence.")
        p_story2 = _make_passage(story_id="STORY-002", passage_id="STORY-002-P01", english="Story 2 sentence.")
        mgr = ContextManager(passages=[p_story1, p_story2])

        # P01 of Story 2 is first in Story 2; must NOT take context from Story 1
        ctx, meta = mgr.build_context(p_story2, strategy="window_k", window_k=2)
        assert ctx is None
        assert meta["sentences_extracted"] == 0

    def test_zero_or_negative_k_returns_none(self, story_passages):
        mgr = ContextManager(passages=story_passages)
        ctx0, meta0 = mgr.build_context(story_passages[2], strategy="window_k", window_k=0)
        assert ctx0 is None
        assert meta0["sentences_extracted"] == 0

        ctx_neg, meta_neg = mgr.build_context(story_passages[2], strategy="window_k", window_k=-1)
        assert ctx_neg is None
        assert meta_neg["sentences_extracted"] == 0


# ---------------------------------------------------------------------------
# ContextStrategyType.STORY_SUMMARY tests
# ---------------------------------------------------------------------------


class TestStrategyStorySummary:

    def test_story_summary_available(self):
        p = _make_passage(story_id="STORY-001")
        summaries = {"STORY-001": "Ama wakes up and has porridge with her grandmother."}
        mgr = ContextManager(passages=[p], summaries=summaries)

        ctx, meta = mgr.build_context(p, strategy="story_summary")
        assert ctx == summaries["STORY-001"]
        assert meta["available"] is True
        assert meta["story_id"] == "STORY-001"

    def test_story_summary_missing_handled_explicitly(self):
        p = _make_passage(story_id="STORY-999")
        mgr = ContextManager(passages=[p], summaries={})

        ctx, meta = mgr.build_context(p, strategy="story_summary")
        assert ctx is None
        assert meta["available"] is False
        assert "No pre-authored summary found" in meta["reason"]


# ---------------------------------------------------------------------------
# ContextStrategyType.GLOSSARY_GUIDED tests
# ---------------------------------------------------------------------------


class TestStrategyGlossaryGuided:

    def test_glossary_from_passage_terms(self):
        p = _make_passage(
            english="Ama spoke with Nana Adwoa.",
            glossary={"Ama": "Main girl", "Nana Adwoa": "Grandmother"},
        )
        mgr = ContextManager(passages=[p])

        ctx, meta = mgr.build_context(p, strategy="glossary_guided")
        assert ctx is not None
        assert "Ama: Main girl" in ctx
        assert "Nana Adwoa: Grandmother" in ctx
        assert meta["empty_glossary"] is False
        assert meta["terms_count"] == 2
        assert len(meta["glossary_hash"]) == 12

    def test_glossary_merges_global_terms_present_in_text(self):
        p = _make_passage(
            english="Kofi and Kweku sat under the odum tree.",
            glossary={"Kofi": "Older brother"},
        )
        global_glossary = {
            "odum": "Sacred native tree",
            "UnrelatedTerm": "Should not appear",
        }
        mgr = ContextManager(passages=[p], global_glossary=global_glossary)

        ctx, meta = mgr.build_context(p, strategy="glossary_guided")
        assert ctx is not None
        assert "Kofi: Older brother" in ctx
        assert "odum: Sacred native tree" in ctx
        assert "UnrelatedTerm" not in ctx
        assert meta["terms_count"] == 2

    def test_empty_glossary_handled_cleanly(self):
        p = _make_passage(english="No names here.", glossary={})
        mgr = ContextManager(passages=[p], global_glossary={})

        ctx, meta = mgr.build_context(p, strategy="glossary_guided")
        assert ctx is None
        assert meta["empty_glossary"] is True
        assert meta["terms_count"] == 0

    def test_glossary_hash_deterministic(self):
        g1 = {"Kofi": "Boy", "Ama": "Girl"}
        g2 = {"Ama": "Girl", "Kofi": "Boy"}
        assert compute_glossary_hash(g1) == compute_glossary_hash(g2)


# ---------------------------------------------------------------------------
# format_engine_input tests
# ---------------------------------------------------------------------------


class TestFormatEngineInput:

    def test_format_engine_input_none_strategy(self):
        src = "The sun rose."
        res = format_engine_input(src, supplied_context="Some context", context_strategy="none")
        assert res == src

    def test_format_engine_input_without_context(self):
        src = "The sun rose."
        res = format_engine_input(src, supplied_context=None, context_strategy="window_k")
        assert res == src

    def test_format_engine_input_with_context(self):
        src = "The sun rose."
        ctx = "Early in the morning."
        res = format_engine_input(src, supplied_context=ctx, context_strategy="window_k")
        assert res == f"[Context: {ctx}] {src}"
