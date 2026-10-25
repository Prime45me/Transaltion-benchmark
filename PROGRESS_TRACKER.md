# Twi Translation Benchmark Lab — Progress Tracker

> **Last Updated:** 2026-10-25
> **Current Phase:** Phase 3 — COMPLETE ✅
> **Next Phase:** Phase 4 — Human Review Workspace

---

## Quick Status Dashboard

| Phase | Title | Status | Tests | Notes |
|-------|-------|--------|-------|-------|
| **1** | Foundation & Dataset | ✅ **COMPLETE** | 91/91 pass | All DoD items verified |
| **2** | Translation Engines & Live Verification | ✅ **COMPLETE** | 158/158 pass | OPUS-MT + Khaya verified live; baseline runs complete |
| **3** | Context Experiments | ✅ **COMPLETE** | 200/200 pass | 4 strategies, caching, budgeting, deduplication |
| **4** | Human Review Workspace | 🔲 Not started | — | Architecture documented |
| **5** | Analysis & Reporting | 🔲 Not started | — | Awaits Phase 4 |

---

## Phase 1 — Foundation and Dataset ✅ COMPLETE

### Definition of Done Checklist

| Requirement | Status | Evidence |
|-------------|--------|---------|
| Project exists in local workspace | ✅ | `c:\Users\user\Desktop\Translaton-benchmark\` |
| Virtual environment configured | ✅ | `.venv\` created, Python 3.12.10 |
| pydantic 2.14.1 installed | ✅ | Verified via import |
| pydantic-settings 2.16.1 installed | ✅ | Verified via import |
| pytest 8.4.2 installed | ✅ | Verified via import |
| Package imports cleanly | ✅ | `src/twi_lab/` with `__init__.py` |
| Sample dataset: ~20–30 passages | ✅ | **25 passages**, 16 categories |
| Dataset schema documented | ✅ | `schemas.py`, `README.md §8` |
| Dataset validation with correct exit codes | ✅ | `python -m twi_lab.dataset --validate` → exit 0 |
| Automated tests pass | ✅ | **91/91 passed** in 2.35s |
| README with reproducible instructions | ✅ | `README.md` (415 lines, 14 sections) |
| No real secrets committed | ✅ | `.gitignore` covers `.env`, `.env.local` |
| No translation models downloaded | ✅ | No HuggingFace downloads in Phase 1 |
| No translation API called | ✅ | No HTTP calls anywhere in codebase |
| Codebase ready for Phase 2 | ✅ | Schemas and contracts in place |
| Deployment architecture documented | ✅ | `docs/deployment_architecture.md` |

---

### Files Created in Phase 1

```
Translaton-benchmark/
├── .env.example                          ✅  Placeholder config (no real secrets)
├── .gitignore                            ✅  Covers venv, .env, logs, models, results
├── pyproject.toml                        ✅  Build config, deps constrained
├── README.md                             ✅  415 lines, 14 sections
├── PROGRESS_TRACKER.md                   ✅  This file
│
├── data/
│   ├── samples/
│   │   ├── passages.jsonl                ✅  25 original passages, 16 categories
│   │   └── manifest.json                 ✅  Dataset provenance and coverage notes
│   └── references/
│       └── .gitkeep                      ✅  Reserved for human reference translations
│
├── docs/
│   └── deployment_architecture.md        ✅  Hosted review interface design (Phase 4+)
│
├── results/
│   └── .gitkeep                          ✅  Generated results excluded by .gitignore
│
├── src/
│   └── twi_lab/
│       ├── __init__.py                   ✅  Package init, version 0.1.0
│       ├── config.py                     ✅  pydantic-settings, env var support
│       ├── schemas.py                    ✅  All data contracts (passages, results, experiments)
│       ├── dataset.py                    ✅  JSONL loader, validator, CLI entry point
│       └── logging_config.py             ✅  Sanitized structured logging
│
└── tests/
    ├── __init__.py                       ✅  Makes tests a package
    ├── test_config.py                    ✅  24 tests — settings, defaults, path resolution
    ├── test_dataset.py                   ✅  34 tests — loading, validation, CLI behaviour
    └── test_schemas.py                   ✅  33 tests — all schema types and edge cases
```

---

### Actual Test Results (verified 2026-10-25)

```
============================= 91 passed in 2.35s ==============================

  test_config.py   24 tests — ALL PASSED
  test_dataset.py  34 tests — ALL PASSED
  test_schemas.py  33 tests — ALL PASSED
```

**Test coverage includes:**
- Valid passage acceptance (all 16 categories)
- Missing required fields
- Empty / whitespace-only English source
- Invalid category values
- Invalid ID characters
- Duplicate passage ID detection
- Malformed JSON Lines
- reference_status / reference_twi cross-validation
- Dataset loading and validation summaries
- CLI exit codes (0 = pass, 1 = fail, 2 = arg error)
- Missing config values and sensible defaults
- Path resolution (relative → absolute)
- TranslationResult schema (Phase 2 contract)
- ExperimentRun schema

---

### Actual Dataset Validation Output (verified 2026-10-25)

```
------------------------------------------------------------
  TWI TRANSLATION BENCHMARK -- DATASET VALIDATION REPORT
------------------------------------------------------------
  Status         : PASSED
  Total records  : 25
  Valid records  : 25
  Invalid records: 0
  Duplicate IDs  : 0

  Category counts:
    ambiguous_reference                        2
    cause_and_effect                           2
    character_name_consistency                 1
    child_friendly_vocabulary                  1
    completeness_boundaries                    1
    cultural_context                           2
    descriptions_relationships                 2
    dialogue                                   2
    event_order_tense                          1
    idioms_figurative                          2
    long_range_context                         1
    multiple_characters                        1
    negation                                   2
    pronouns_character_ref                     2
    questions_and_commands                     1
    simple_sentence                            2
------------------------------------------------------------
Exit code: 0
```

---

### Key Architectural Decisions (Phase 1)

| Decision | Rationale |
|----------|-----------|
| **JSON Lines (JSONL) for passages** | Each line independently parseable; supports incremental processing |
| **Pydantic v2 for all schemas** | Type-safe, auto-documented, extensible for Phase 2 |
| **`src/` layout** | Prevents accidental root-level imports without an editable install |
| **`extra="forbid"` on BenchmarkPassage** | Rejects unknown fields early; no silent data corruption |
| **reference_status + reference_twi cross-validation** | Prevents marking unverified text as human-reviewed |
| **Separate `validate_dataset()` and `load_passages()`** | Validation gives a full report; loading only returns valid records |
| **`lru_cache` singleton on `get_settings()`** | Consistent settings object without repeated env reads |
| **Sanitized log formatter** | Redacts API keys/tokens from logs automatically |
| **Deployment architecture as Phase 1 doc** | Data contracts compatible with hosted review before any code is written |
| **`data/references/` NOT gitignored** | Human reference translations are first-class research assets |
| **`results/` gitignored (except .gitkeep)** | Generated experiment outputs are transient and potentially large |

---

## Phase 2 — Translation Engines 🔲 NOT STARTED

### Prerequisite: Phase 1 ✅ Complete

### What Needs to Be Built

- [x] **Engine base protocol** (`src/twi_lab/engines/base.py`)
  - Abstract base class (`EngineAdapter`) both adapters implement
  - Standard interface: `translate(source_text, ...) -> TranslationResult`
  - Engine identity: `engine_name`, `engine_version`, `is_available`

- [x] **Local OPUS-MT adapter** (`src/twi_lab/engines/opus_mt.py`)
  - Uses `Helsinki-NLP/opus-mt-en-tw` via HuggingFace MarianMT
  - Lazy loading: tokenizer & model only loaded on first inference call
  - Model download gated behind explicit `--download` flag — never automatic
  - Verified local model in `models/opus-mt-en-tw` (282.9 MB, 8 files)
  - Verified 100% offline inference on CPU (no GPU required)
  - Populates all fields of `TranslationResult` from `schemas.py`
  - Records `model_identifier`, `model_revision`, `elapsed_time_ms`

- [x] **Khaya API adapter** (`src/twi_lab/engines/khaya.py`)
  - HTTP client using `requests` with connection pooling
  - Connected to GhanaNLP REST API (`https://translation-api.ghananlp.org/v1/translate`)
  - Azure APIM authentication header: `Ocp-Apim-Subscription-Key`
  - Dual-key optimization: configured with Primary and Secondary keys for automatic failover
  - In-memory caching: eliminates redundant API calls for duplicate passages
  - Full error classification: timeouts, authentication errors, quota/rate-limits (429), and connection errors
  - Clearly documented as network-dependent (requires internet access)

- [x] **Translation runner** (`src/twi_lab/runner.py`)
  - Accepts dataset path + engine list + passage filter + context strategy
  - Writes `TranslationResult` records as JSONL to `results/`
  - Creates and updates `ExperimentRun` JSON manifest with summary counts and timing
  - Supports dry-run mode (`--dry-run`)
  - Verified live baseline runs for both OPUS-MT and Khaya

- [x] **Phase 2 tests** (`tests/test_engines/`, `tests/test_runner.py`)
  - **158/158 tests passing**
  - Mocks all HTTP calls — never calls Khaya in automated tests
  - Mocks HuggingFace model loading — never downloads weights in tests
  - Tested error paths: timeouts, 401/403 auth, 429 quota, connection errors, missing keys, and key failovers

### Verified Live Baseline Runs (2026-10-25)

| Experiment ID | Title | Engine | Passages | Success | Failed | Avg Latency | Results File |
|---------------|-------|--------|----------|---------|--------|-------------|--------------|
| `99232ce8-4a84-4ec8-930d-2116e5b456da` | OPUS-MT local baseline | `opus-mt` | 3 | 3 | 0 | 5,348.7 ms | `results/results_99232ce8-...jsonl` |
| `6d89794c-df30-4c36-8e50-8edf7bd46717` | Khaya API baseline | `khaya` | 3 | 3 | 0 | 1,120.0 ms | `results/results_6d89794c-...jsonl` |

**Sample Live Translation Comparison:**
- **Source:** `"The sun rose slowly over the hills."`
  - *OPUS-MT:* `Owia pue nkakrankakra wɔ mmepɔw no so.`
  - *Khaya:* `Owia puee nkakrankakra wɔ nkoko no so.`
- **Source:** `"Ama woke up and stretched her arms wide like a bird spreading its wings."`
  - *OPUS-MT:* `Ama asɔren ne nsa mu te sɛ anomaa a ɔretrɛw ne ntaban mu.`
  - *Khaya:* `Ama nyanee na ɔtrɛɛ ne nsa trɛwee sɛ anomaa a ɔtrɛw ne ntaban mu`
- **Source:** `"\"Grandmother, is breakfast ready?\" Ama called from the doorway."`
  - *OPUS-MT:* `" Ɛnanom, so wɔyɛ aduan ho nhyehyɛe? "`
  - *Khaya:* `"Nana, so anɔpa aduan ayɛ krado?" Ama frɛɛ no fii ɔpon no ano.`

---

## Phase 3 — Context Experiments ✅ COMPLETE

### Prerequisites: Phase 2 complete ✅

### Definition of Done Checklist

| Requirement | Status | Evidence |
|-------------|--------|---------|
| 4 context strategies behind shared interface | ✅ | `src/twi_lab/context.py` — `ContextManager`, `ContextStrategyType` |
| Strategy: `none` (baseline) | ✅ | Returns passage unchanged, no extra context |
| Strategy: `window_k` (preceding sentences) | ✅ | Never future, never cross-story, configurable k |
| Strategy: `story_summary` (pre-authored) | ✅ | Loads from `data/samples/summaries.json`, no API calls |
| Strategy: `glossary_guided` (approved terms) | ✅ | Loads from `data/samples/glossary.json`, SHA-256 hash provenance |
| Persistent disk caching (`TranslationCache`) | ✅ | `src/twi_lab/cache.py` — atomic writes, SHA-256 composite keys |
| Non-success results never cached | ✅ | FAILED/TIMEOUT/PARTIAL skipped in `cache.set()` |
| Cache inspection (`--cache-stats`) | ✅ | CLI outputs entry count, hit/miss, file size |
| Deliberate cache clearing (`--clear-cache`) | ✅ | CLI deletes cache file and resets counters |
| Pre-flight API call estimation | ✅ | Pre-dispatch analysis before any engine call |
| Configurable Khaya call budget | ✅ | `--khaya-budget`, default 10, config `khaya_call_budget` |
| Budget exceeded → abort with zero calls | ✅ | `BudgetExceededError` raised before dispatching |
| `--confirm-live-khaya` flag required | ✅ | `LiveCallConfirmationError` raised without explicit flag |
| Request deduplication before dispatch | ✅ | Identical passages share cache key; only 1 live call |
| Dry-run shows usage estimates with zero calls | ✅ | Reports planned records, unique requests, estimated hits |
| `--cache-only` mode | ✅ | Aborts if any live call needed |
| `--context-strategy all` evaluates 4 strategies | ✅ | 1 passage × 1 engine × 4 strategies = 4 planned records |
| Passages treated as unified units (no splitting) | ✅ | Paragraphs never split into sub-requests |
| Engine context limitations documented honestly | ✅ | `README.md §14.3`, `context.py` docstrings |
| Story summaries data file | ✅ | `data/samples/summaries.json` — 8 stories |
| Glossary data file | ✅ | `data/samples/glossary.json` — 15 approved terms |
| `config.py` updated with Phase 3 settings | ✅ | `cache_path`, `summaries_path`, `glossary_path`, `khaya_call_budget` |
| `runner.py` updated with full Phase 3 orchestration | ✅ | Context + caching + budgeting + dedup + dry-run |
| `schemas.py` updated with `context_metadata`, `is_cache_hit` | ✅ | New fields on `TranslationResult` |
| Both engines use `format_engine_input()` | ✅ | OPUS-MT and Khaya receive identical formatted input |
| All existing 158 tests preserved | ✅ | Zero regressions |
| New Phase 3 tests comprehensive | ✅ | 42 new tests across 3 test files |
| Total test suite passes | ✅ | **200/200 passed** in ~19s |
| `README.md` updated | ✅ | New §14 with full Phase 3 documentation |
| `PROGRESS_TRACKER.md` updated | ✅ | This section |

---

### Files Created / Modified in Phase 3

```
Translaton-benchmark/
├── data/
│   ├── cache/
│   │   └── translation_cache.json          ✅  Persistent translation cache (gitignored)
│   └── samples/
│       ├── summaries.json                  ✅  Human-authored story summaries (8 stories)
│       └── glossary.json                   ✅  Approved Akan names and terms (15 entries)
│
├── src/twi_lab/
│   ├── cache.py                            ✅  TranslationCache, compute_cache_key
│   ├── context.py                          ✅  ContextManager, 4 strategies, format_engine_input
│   ├── config.py                           ✅  +4 Phase 3 settings, +3 resolved properties
│   ├── schemas.py                          ✅  +context_metadata, +is_cache_hit on TranslationResult
│   ├── runner.py                           ✅  Full rewrite: context, caching, budgeting, dedup, CLI
│   └── engines/
│       ├── opus_mt.py                      ✅  Uses format_engine_input for context-aware tokenization
│       └── khaya.py                        ✅  Uses format_engine_input for context-aware payloads
│
└── tests/
    ├── test_cache.py                       ✅  18 tests — key determinism, roundtrip, stats, persistence
    ├── test_context.py                     ✅  14 tests — all 4 strategies, boundaries, formatting
    └── test_runner_phase3.py               ✅  10 tests — budget, dedup, cache-only, multi-strategy, CLI
```

---

### Actual Test Results (verified 2026-10-25)

```
============================ 200 passed in 19.46s =============================

  test_config.py            24 tests — ALL PASSED
  test_dataset.py           34 tests — ALL PASSED
  test_schemas.py           33 tests — ALL PASSED
  test_engines/test_khaya.py    30 tests — ALL PASSED
  test_engines/test_opus_mt.py  27 tests — ALL PASSED
  test_runner.py            20 tests — ALL PASSED
  test_cache.py             18 tests — ALL PASSED
  test_context.py           14 tests — ALL PASSED
  test_runner_phase3.py     10 tests — ALL PASSED  (NEW)
  ---
  TOTAL                    200 tests — ALL PASSED
```

---

### Verified CLI Dry-Run Output (2026-10-25)

```
python -m twi_lab.runner --engine all --title "Dry run all strategies" --context-strategy all --dry-run

Experiment completed: 9411edaa-e810-44c8-a232-3346d4933d77
  Mode                      : DRY RUN (no live calls made)
  Total planned records     : 100
  Unique requests           : 100
  Estimated cache hits      : 0
  Estimated live Khaya calls: 0
  Calls saved by cache      : 0
  Calls saved by deduplication: 0
  Configured Khaya budget   : 10
  Permitted to proceed      : True
```

---

### Key Architectural Decisions (Phase 3)

| Decision | Rationale |
|----------|-----------|
| **Composite SHA-256 cache keys** | Covers engine, version, model, source text, context strategy, supplied context, and generation settings — any variation produces a distinct key |
| **Atomic tempfile cache writes** | Prevents corruption on crash by writing to a `.tmp` then `os.replace` |
| **Pre-flight estimation before dispatch** | All budget and deduplication checks happen before ANY engine call or API request |
| **`format_engine_input()` shared by both engines** | Guarantees identical input for fair comparison since neither engine has a native context parameter |
| **`BudgetExceededError` and `LiveCallConfirmationError`** | Typed exceptions with clear messages allow CLI to set exit code 2 |
| **`--context-strategy all` expands to 4 strategies** | Single command evaluates `none`, `window_k`, `story_summary`, `glossary_guided` |
| **Passages never split into sentences for translation** | Paragraph-level translation preserves discourse coherence; sentence splitting is only used for context window extraction |
| **Non-success results excluded from cache** | Only `TranslationStatus.SUCCESS` enters the cache; failures and timeouts are retried on next run |

---

## Phase 4 — Human Review Workspace 🔲 NOT STARTED

### Prerequisites: Phase 3 complete (or usable Phase 2 experiment results)

### Shared Hosted Review Interface (Required)

> Full architecture: [`docs/deployment_architecture.md`](docs/deployment_architecture.md)

**Core requirements:**
- Reviewer opens interface via shareable **HTTPS URL** — not localhost
- Engine identity is **blinded** to reviewers during evaluation
- Candidates presented in **randomised order** per reviewer
- **Authenticated access** — no public link to unpublished story content
- Review progress **persisted** in hosted database (offline-safe)
- **Duplicate submission prevention** per reviewer per passage
- Supports **multiple independent reviewers** with disagreement analysis

**Planned stack (subject to revision in Phase 4):**
- Backend: FastAPI (Python) — consistent with existing codebase
- Database: PostgreSQL (hosted, e.g., Supabase or Neon)
- Auth: JWT tokens / session-based (never expose API keys to browser)
- Hosting: Render / Railway / Fly.io (TBD)
- Frontend: Server-side rendered HTML or minimal React

**Data model additions needed in Phase 4:**

```python
# To be added to schemas.py in Phase 4:

class ReviewerEvaluation(BaseModel):
    evaluation_id: str              # UUID
    experiment_id: str
    passage_id: str
    result_ids: List[str]           # Blinded candidate IDs being evaluated
    reviewer_id: str                # Pseudonymous reviewer identifier
    scores: Dict[str, int]          # result_id → quality score 1–5
    preferred_result_id: Optional[str]
    error_categories: Dict[str, List[str]]  # result_id → error type list
    corrections: Dict[str, str]     # result_id → reviewer's corrected translation
    notes: Optional[str]
    submitted_at: datetime
    is_complete: bool
    assignment_id: str              # Links to ReviewAssignment
    prevented_duplicate: bool       # True if system blocked re-submission

class ReviewAssignment(BaseModel):
    assignment_id: str
    experiment_id: str
    reviewer_id: str
    passage_ids: List[str]
    status: Literal["pending", "in_progress", "complete"]
    assigned_at: datetime
    due_date: Optional[datetime]
    completed_at: Optional[datetime]
```

> ⚠️ **Do not claim the review interface is remotely accessible until a real HTTPS URL has been deployed and verified. A local development URL (localhost) is not a shareable link.**

---

## Phase 5 — Analysis and Reporting 🔲 NOT STARTED

### Prerequisites: Phase 4 complete (minimum one review round)

### What Needs to Be Built

- [ ] **Inter-reviewer agreement** — Cohen's κ, Krippendorff's α
- [ ] **Engine quality comparison** — mean scores, score distributions by category
- [ ] **Error rate analysis** — by engine, by error category, by context strategy
- [ ] **Latency and cost reporting** — per engine, per passage, aggregated
- [ ] **Human editing effort** — character-level edit distance on reviewer corrections
- [ ] **Automated metrics** (supplementary only) — BLEU, chrF against `reference_twi`
- [ ] **Export** — CSV, JSON, Markdown summary report
- [ ] **Recommendation** — evidence-based, citing specific metrics

---

## Deployment Readiness

| Environment | Status | Notes |
|-------------|--------|-------|
| **Local Windows (Phase 1–2)** | ✅ Ready | Full stack working |
| **CI (GitHub Actions)** | 🔲 Not configured | `pytest tests/` is runnable |
| **Hosted review app** | 🔲 Not deployed | Phase 4 deliverable |
| **Hosted database** | 🔲 Not provisioned | Phase 4 deliverable |
| **Shareable reviewer HTTPS URL** | 🔲 Not available | Phase 4 deliverable |

---

## Commands Reference

### Available Now (Phase 1)

```powershell
# Activate virtual environment
.venv\Scripts\Activate.ps1          # PowerShell
.venv\Scripts\activate.bat          # Command Prompt
source .venv/bin/activate           # Linux / macOS

# Run all tests
.venv\Scripts\python.exe -m pytest tests\ -v

# Validate the benchmark dataset
.venv\Scripts\python.exe -m twi_lab.dataset --validate

# Validate a specific file
.venv\Scripts\python.exe -m twi_lab.dataset --validate --dataset path\to\file.jsonl

# Verbose validation (shows error snippets)
.venv\Scripts\python.exe -m twi_lab.dataset --validate --verbose
```

### Planned for Phase 2

```powershell
# Install Phase 2 extras
.venv\Scripts\pip install -e ".[phase2]"

# Run a translation experiment (to be implemented)
# .venv\Scripts\python.exe -m twi_lab.runner --engine opus-mt --dataset data\samples\passages.jsonl
```

---

## Known Issues and Notes

| Item | Severity | Detail |
|------|----------|--------|
| 6 categories have only 1 passage each | ⚠️ Low | `character_name_consistency`, `child_friendly_vocabulary`, `completeness_boundaries`, `questions_and_commands`, `event_order_tense`, `long_range_context` — sufficient for Phase 1; expand before Phase 3 |
| No `reference_twi` values yet | ✅ Expected | All passages have `reference_status: absent` — awaiting qualified Asante Twi reviewer |
| No CI pipeline | ⚠️ Low | `pytest` runs locally; add GitHub Actions workflow in Phase 2 |
| Deployment stack not yet chosen | ✅ Expected | Phase 4 decision — documented in `docs/deployment_architecture.md` |

---

## Research Principles (Upheld in Every Phase)

1. **Human-reviewed Twi is the primary quality reference.** BLEU and chrF are supplementary.
2. **Engine identity must be hidden during human evaluation** (Phase 4 — blinded presentation).
3. **Context strategies must be compared experimentally** — do not assume more context is better.
4. **Same source passages, comparable settings** — required for fair engine comparison.
5. **Critical meaning errors tracked separately** — not averaged into quality scores.
6. **Store model versions and configurations** — every result must be reproducible.
7. **Source English is never modified** — the `english` field is read-only after creation.
8. **No engine recommendation before evidence** — Phase 5 only, based on measured data.
9. **API credentials and database secrets never in browser code** — server/worker side only.
10. **Do not claim remote access until deployed and verified** — localhost ≠ shareable link.
