# Twi Translation Benchmark Lab

An independent research tool for comparing English-to-Asante Twi translation engines on children's story content. The lab evaluates translation quality, cultural faithfulness, and child-friendliness using human reviewer judgements and structured linguistic benchmarks.

> **Phase 1 — Foundation and Dataset.**  
> Translation does not happen yet. This phase establishes the data contracts, dataset, validation tooling, and architecture needed for Phases 2–5.

---

## Table of Contents

1. [Project Purpose and Scope](#1-project-purpose-and-scope)
2. [Five-Phase Roadmap](#2-five-phase-roadmap)
3. [Prerequisites](#3-prerequisites)
4. [Virtual Environment Setup](#4-virtual-environment-setup)
5. [Dependency Installation](#5-dependency-installation)
6. [Configuration](#6-configuration)
7. [Directory Structure](#7-directory-structure)
8. [Dataset Schema](#8-dataset-schema)
9. [Adding a New Sample Passage](#9-adding-a-new-sample-passage)
10. [Validating the Dataset](#10-validating-the-dataset)
11. [Running Tests](#11-running-tests)
12. [Current Limitations](#12-current-limitations)
13. [What is Postponed to Phase 2](#13-what-is-postponed-to-phase-2)
14. [Phase 3 — Context Experiments, Caching, and Budgeting](#14-phase-3--context-experiments-caching-and-budgeting)
15. [Quality and Research Principles](#15-quality-and-research-principles)

---

## 1. Project Purpose and Scope

This lab compares translation engines to determine which produces the most accurate, natural, contextually appropriate, culturally faithful, and child-friendly Asante Twi translations for children's stories.

**Initial engines:**
- **OPUS-MT** — runs locally, no API key required.
- **Khaya** — cloud translation API, requires a key (Phase 2).

Human narrators and qualified Asante Twi reviewers evaluate translations. Their corrections and judgements help the content team decide which translation is suitable for review and eventual publication.

**This is an experimental evaluation tool.** It is not the production storytelling application, payment system, parent account system, or public translation service.

---

## 2. Five-Phase Roadmap

| Phase | Title | Status |
|-------|-------|--------|
| **1** | Foundation, dataset, and infrastructure | ✅ Complete |
| **2** | Translation engines (OPUS-MT + Khaya) | ✅ Complete |
| **3** | Context experiments | ✅ Complete |
| **4** | Shared human review workspace | 🔲 Not started |
| **5** | Analysis and reporting | 🔲 Not started |

See [`docs/deployment_architecture.md`](docs/deployment_architecture.md) for the planned hosted review interface architecture.

---

## 3. Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.10+ | 3.12 recommended. Check: `python --version` |
| Git | For version control |
| Internet access | Only needed for pip install and Phase 2+ Khaya API |
| GPU | **Not required.** CPU-only inference is the default. |

No Docker, Kubernetes, Redis, or remote database is required for Phase 1 or 2.

---

## 4. Virtual Environment Setup

### Windows PowerShell

```powershell
cd C:\Users\user\Desktop\Translaton-benchmark
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Windows Command Prompt

```cmd
cd C:\Users\user\Desktop\Translaton-benchmark
python -m venv .venv
.venv\Scripts\activate.bat
```

### Linux / macOS

```bash
cd ~/path/to/Translaton-benchmark
python3 -m venv .venv
source .venv/bin/activate
```

---

## 5. Dependency Installation

Install the package in editable mode with development dependencies:

```bash
pip install -e ".[dev]"
```

Phase 1 dependencies:
- `pydantic>=2.7.0,<3.0.0` — data validation and schema enforcement
- `pydantic-settings>=2.2.0,<3.0.0` — environment variable configuration
- `pytest>=8.0.0,<9.0.0` — automated tests (dev only)

Phase 2 dependencies (not installed yet):
- `requests>=2.31.0` — HTTP client for Khaya API

Model weights (OPUS-MT) are **not downloaded in Phase 1**.

---

## 6. Configuration

Copy the example file and adjust values for your environment:

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

Edit `.env` as needed. The file is excluded from version control by `.gitignore`.  
**Never commit real API keys.**

### Available configuration keys

| Key | Default | Description |
|-----|---------|-------------|
| `PROJECT_ENV` | `development` | `development`, `testing`, or `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `DATASET_PATH` | `data/samples/passages.jsonl` | Path to passages JSONL |
| `MANIFEST_PATH` | `data/samples/manifest.json` | Path to dataset manifest |
| `RESULTS_DIR` | `results` | Where experiment results are stored |
| `LOGS_DIR` | `logs` | Where log files are written |
| `KHAYA_API_KEY` | *(none)* | **Phase 2 only.** Not required for Phase 1. |
| `KHAYA_API_BASE_URL` | `https://api.khaya.ai/v1` | Khaya endpoint |
| `OPUS_MT_MODEL_NAME` | `Helsinki-NLP/opus-mt-en-tw` | HuggingFace model ID |
| `OPUS_MT_MODEL_DIR` | `models/opus-mt-en-tw` | Local model cache directory |
| `LOCAL_DEVICE` | `cpu` | `cpu` or `cuda` |

---

## 7. Directory Structure

```
Translaton-benchmark/
├── data/
│   ├── samples/
│   │   ├── passages.jsonl       # Benchmark passages (JSONL, one record per line)
│   │   └── manifest.json        # Dataset provenance and coverage metadata
│   └── references/
│       └── .gitkeep             # Reserved for human reference translations
├── docs/
│   └── deployment_architecture.md  # Shared review interface design (Phase 4)
├── src/
│   └── twi_lab/
│       ├── __init__.py          # Package marker
│       ├── config.py            # Settings and environment configuration
│       ├── dataset.py           # JSONL loader, validator, CLI entry point
│       ├── logging_config.py    # Structured logging with secret redaction
│       └── schemas.py           # Pydantic data contracts for all phases
├── tests/
│   ├── __init__.py
│   ├── test_config.py           # Configuration and path resolution tests
│   ├── test_dataset.py          # Dataset loading, validation, and CLI tests
│   └── test_schemas.py          # Schema acceptance and rejection tests
├── results/
│   └── .gitkeep                 # Experiment results (gitignored)
├── .env.example                 # Configuration template (safe to commit)
├── .gitignore
├── pyproject.toml
└── README.md
```

### What is committed vs. gitignored

| Path | Committed? | Reason |
|------|-----------|--------|
| `data/samples/` | ✅ Yes | Source benchmark data is a tracked asset |
| `data/references/` | ✅ Yes | Human-reviewed reference translations (when added) |
| `results/` | ❌ No | Generated experiment outputs (transient) |
| `logs/` | ❌ No | Application logs (transient) |
| `models/` | ❌ No | Downloaded model weights (large, reproducible) |
| `.env` | ❌ No | Contains secrets |
| `.venv/` | ❌ No | Virtual environment (reproducible) |

---

## 8. Dataset Schema

Each line in `data/samples/passages.jsonl` is a valid JSON object representing one benchmark passage.

### Required fields

| Field | Type | Description |
|-------|------|-------------|
| `story_id` | string | Stable story identifier. Alphanumeric, dashes, underscores only. Example: `STORY-001` |
| `passage_id` | string | Unique passage identifier across the whole dataset. Example: `STORY-001-P01` |
| `category` | string | Linguistic phenomenon. Must be one of the 16 supported values (see below). |
| `english` | string | Exact English source passage. Must not be empty. |

### Optional fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `story_context` | string or null | null | Surrounding narrative context for the translator |
| `character_names` | list of strings | `[]` | Characters appearing in the passage |
| `glossary` | dict | `{}` | Approved names and term meanings |
| `reference_twi` | string or null | null | Human-reviewed Asante Twi reference translation |
| `reference_status` | string | `"absent"` | `absent`, `drafted`, or `human_reviewed` |
| `review_status` | string | `"pending"` | `pending`, `in_review`, `approved`, or `rejected` |
| `source_metadata` | dict | `{}` | Author, license, creation date, and provenance notes |

### Consistency rules

- `reference_status: "human_reviewed"` requires a non-empty `reference_twi`.
- `reference_status: "absent"` requires `reference_twi` to be null or empty.
- `passage_id` must be unique across the entire dataset.

### Supported linguistic categories

```
simple_sentence            pronouns_character_ref     dialogue
multiple_characters        event_order_tense          cause_and_effect
ambiguous_reference        idioms_figurative           cultural_context
character_name_consistency  descriptions_relationships  child_friendly_vocabulary
questions_and_commands      negation                   long_range_context
completeness_boundaries
```

### Example passage record

```json
{
  "story_id": "STORY-001",
  "passage_id": "STORY-001-P01",
  "category": "simple_sentence",
  "english": "The sun rose slowly over the hills.",
  "story_context": "Opening line of a morning story set in a small village.",
  "character_names": [],
  "glossary": {},
  "reference_twi": null,
  "reference_status": "absent",
  "review_status": "pending",
  "source_metadata": {
    "author": "Original fixture",
    "license": "CC-BY-4.0",
    "created": "2026-10-21",
    "is_dev_fixture": true
  }
}
```

---

## 9. Adding a New Sample Passage

1. Open `data/samples/passages.jsonl` in any text editor.
2. Add one JSON object per line at the end of the file. Do not add commas between lines.
3. Assign a unique `passage_id` following the pattern `STORY-NNN-PNN`.
4. Choose a category from the 16 supported values.
5. Leave `reference_twi` as `null` and `reference_status` as `"absent"` unless a qualified Asante Twi reviewer has approved the reference.
6. Run validation to confirm the record is accepted:

   ```bash
   python -m twi_lab.dataset --validate
   ```

7. Update the `passage_count` and `categories` fields in `data/samples/manifest.json` to match the new totals.

> **Do not invent Asante Twi translations.** Leave `reference_twi` empty until a qualified reviewer supplies and approves one.

---

## 10. Validating the Dataset

### Basic validation

```bash
python -m twi_lab.dataset --validate
```

### Validate a specific file

```bash
python -m twi_lab.dataset --validate --dataset path/to/passages.jsonl
```

### Verbose output (includes raw error snippets)

```bash
python -m twi_lab.dataset --validate --verbose
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All records valid |
| `1` | Validation failed (invalid records, duplicates, or file not found) |
| `2` | Configuration or argument error |

### Example output

```
────────────────────────────────────────────────────────────
  TWI TRANSLATION BENCHMARK — DATASET VALIDATION REPORT
────────────────────────────────────────────────────────────
  Status         : ✅ PASSED
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
    dialogue                                   3
    event_order_tense                          1
    idioms_figurative                          2
    long_range_context                         1
    multiple_characters                        1
    negation                                   2
    pronouns_character_ref                     2
    questions_and_commands                     1
    simple_sentence                            2
────────────────────────────────────────────────────────────
```

---

## 11. Running Tests

Ensure the virtual environment is activated, then run:

```bash
pytest
```

Run with verbose output:

```bash
pytest -v
```

Run a specific test file:

```bash
pytest tests/test_schemas.py
pytest tests/test_dataset.py
pytest tests/test_config.py
```

Tests use temporary directories and files. They do not touch `data/samples/` and do not call any external API.

---

## 12. Current Limitations

- **No translation occurs in Phase 1.** The engines are not implemented, configured, or called.
- **No Asante Twi reference translations exist.** All passages have `reference_status: "absent"`. A qualified reviewer must supply references before quality metrics can be calculated.
- **The sample dataset is a development fixture**, not a validated or representative linguistic benchmark. It covers 25 original passages across 16 categories but has not been reviewed for linguistic adequacy, balance, or difficulty calibration.
- **No reviewer interface.** Human review is planned for Phase 4 as a hosted web application. The current architecture documentation is in `docs/deployment_architecture.md`.
- **No automated metrics.** BLEU, chrF, and other automated metrics are Phase 5 additions.
- **No experiment runner.** `ExperimentRun` and `TranslationResult` schemas are defined but not connected to execution logic.

---

---

## 13. Translation Engines & Experiment Execution (Phase 2)

Phase 2 introduces the two core translation engines and the experiment orchestrator.

### 13.1 Khaya API Configuration & Key Optimization

The Khaya cloud adapter translates English text into Asante Twi via the GhanaNLP REST API (`https://translation-api.ghananlp.org/v1/translate`).

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Configure your API key in `.env`:
   ```env
   KHAYA_API_KEY=your_primary_key_here
   KHAYA_API_SECONDARY_KEY=your_secondary_key_here
   KHAYA_API_BASE_URL=https://translation-api.ghananlp.org/v1
   KHAYA_TIMEOUT_SECONDS=30
   ```
3. **Key Optimization & Failover:**
   - The adapter supports **automatic key failover**: if the primary key experiences a rate limit (HTTP 429) or authentication / quota error (HTTP 401/403), it automatically retries with the secondary key.
   - **In-memory caching** prevents redundant network calls and saves quota for repeated translations.
   - **Connection pooling** reuses HTTP connections across requests.
   - `.env` and `*keys*.txt` are strictly ignored by `.gitignore` to prevent credential leaks.

### 13.2 OPUS-MT Local Model Download & Offline Inference

OPUS-MT (`Helsinki-NLP/opus-mt-en-tw`) is a local MarianMT model running via HuggingFace Transformers.

1. **Install requirements:**
   ```bash
   pip install transformers sentencepiece torch
   ```
2. **Download model weights (one-time download, ~283 MB):**
   ```bash
   python -m twi_lab.engines.opus_mt --download
   ```
   Weights and tokenizer files are saved to `models/opus-mt-en-tw` (ignored by Git).
3. **Offline inference:**
   Once downloaded, OPUS-MT runs **100% locally on CPU without internet access**.

### 13.3 Testing Engines Independently

You can verify each adapter from Python or small CLI commands:

```bash
# Test Khaya API with a single sentence:
python -c "from twi_lab.engines.khaya import KhayaAdapter; res = KhayaAdapter().translate('Welcome to our school.', experiment_id='test', story_id='test', passage_id='p1'); print(res.translated_text)"

# Test OPUS-MT offline inference:
python -c "from twi_lab.engines.opus_mt import OPUSMTAdapter; res = OPUSMTAdapter().translate('Welcome to our school.', experiment_id='test', story_id='test', passage_id='p1'); print(res.translated_text)"
```

### 13.4 Running Baseline Experiments

The runner orchestrates evaluation runs across one or more engines and records structured outputs in `results/`:

```bash
# Run OPUS-MT local baseline on a subset of passages:
python -m twi_lab.runner --engine opus-mt --title "OPUS-MT local baseline" --passages STORY-001-P01 STORY-001-P02 STORY-001-P03

# Run Khaya API baseline on a subset of passages:
python -m twi_lab.runner --engine khaya --title "Khaya API baseline" --passages STORY-001-P01 STORY-001-P02 STORY-001-P03

# Run both engines on all passages (dry run to validate setup):
python -m twi_lab.runner --engine all --dry-run
```

### 13.5 Result Artifacts & Schema

Each experiment creates two files in `results/`:
- `experiment_<id>.json` — Experiment run manifest (timing, summary counts, engine versions, status).
- `results_<id>.jsonl` — One `TranslationResult` record per line containing original English, Asante Twi translation, engine name/version, character counts, and latency in milliseconds.

### 13.6 Internet Access Requirements

| Operation | Internet Required? | Notes |
|-----------|--------------------|-------|
| Unit tests (`pytest`) | ❌ No | Fully mocked; zero network calls |
| OPUS-MT inference | ❌ No | Runs completely offline from `models/` |
| OPUS-MT download | ✅ Yes | One-time HuggingFace download |
| Khaya API translation | ✅ Yes | HTTPS requests to `translation-api.ghananlp.org` |

### 13.7 Common Failure Modes & Troubleshooting

| Failure Mode | HTTP / Error Code | Cause & Remedy |
|--------------|-------------------|----------------|
| Missing API Key | `missing_api_key` | `KHAYA_API_KEY` not set in `.env`. Add key to `.env`. |
| Auth Failure | HTTP 401 / 403 | Invalid subscription key. Adapter will fail over to `KHAYA_API_SECONDARY_KEY` if configured. |
| Quota / Rate Limit | HTTP 429 | Subscription quota exceeded. Adapter automatically retries with secondary key. |
| Timeout | `status=timeout` | Network latency exceeded `KHAYA_TIMEOUT_SECONDS` (default 30s). Increase timeout in `.env`. |
| Model Missing | `RuntimeError` | OPUS-MT weights not found. Run `python -m twi_lab.engines.opus_mt --download`. |
| Encoding Error on Windows | `UnicodeEncodeError` | Asante Twi characters (e.g. `ɛ`, `ɔ`) require UTF-8 output. Code handles UTF-8 buffers. |

---

## 14. Phase 3 — Context Experiments, Caching, and Budgeting

Phase 3 introduces controlled narrative context strategies, persistent disk caching, pre-flight API call budgeting, and request deduplication to answer the primary research question:
*Does additional narrative context improve English-to-Asante-Twi translation quality, and does the effect differ between OPUS-MT and Khaya?*

### 14.1 The Four Context Strategies

All four strategies are implemented behind the shared `ContextManager` interface (`src/twi_lab/context.py`):

1. **`none` (Baseline):**
   - Translates the target passage in isolation without extra contextual text.
   - The original `english` source is preserved completely unchanged.
2. **`window_k` (Preceding Sentences):**
   - Supplies the trailing `k` sentences extracted from earlier passages in the exact same story.
   - Configurable via `--window-k <int>` (default: `1`).
   - **Boundary Guarantees:** Never includes future sentences, never looks across story boundaries, and returns empty preceding context if the passage is the first in a story.
3. **`story_summary` (Pre-authored Narrative Summary):**
   - Provides a concise, human-authored story synopsis from `data/samples/summaries.json`.
   - Never makes automated API calls to generate summaries.
   - If no pre-existing summary is available for a story, marks the strategy unavailable for that passage rather than guessing or querying APIs.
4. **`glossary_guided` (Approved Terminology & Character Names):**
   - Injects approved Akan character day-names and domain terminology from `data/samples/glossary.json` and passage-specific glossaries.
   - Terms are merged and formatted deterministically (`Term: Definition; ...`).
   - If no approved terms match, explicitly records an empty glossary state. A SHA-256 glossary content hash is saved in result metadata for provenance.

### 14.2 Treatment of Paragraphs and Sentences

- **Default Unit:** Passages in `data/samples/passages.jsonl` represent paragraph-sized narrative units. By default, passages are treated as intact translation targets and are **never split** into separate API requests.
- **Context Extraction:** When `window_k` segments preceding passages into sentences, it uses order-preserving regex sentence splitting (`split_sentences()`) while leaving the target passage source code intact.

### 14.3 Engine Integration & Context Limitations

Neither local MarianMT (`Helsinki-NLP/opus-mt-en-tw`) nor the GhanaNLP / Khaya translation endpoint natively supports an auxiliary `context` API parameter.

To ensure an honest, reproducible, and fair comparison across engines:
- Both engines receive an identical constructed input string when context is active:
  ```
  [Context: <supplied_context>] <target_passage>
  ```
- The original unmutated English passage remains stored in `TranslationResult.source_text`.
- The exact contextual text is stored in `TranslationResult.supplied_context`, and strategy provenance details are recorded in `TranslationResult.context_metadata`.

### 14.4 Khaya API Budgeting and Safety Controls

To avoid unexpected costs or exhausting subscription quotas:
1. **Pre-flight Estimation:** Before any network call or model inference, the runner analyzes planned requests, counts cache hits and deduplicated reuses, and determines the exact number of required live API calls.
2. **Configurable Budget:** Set with `--khaya-budget <int>` (default: `10`, or `KHAYA_CALL_BUDGET` in `.env`).
3. **Pre-Dispatch Abort:** If `estimated_live_calls > budget`, the experiment aborts immediately with exit code 2 and makes **zero** live calls.
4. **Explicit Authorization:** Live Khaya batch experiments require `--confirm-live-khaya`. Without this flag, the runner aborts before calling Khaya.
5. **No Network Calls in Tests:** Automated test suites mock all engine adapters; zero API calls occur during testing.

### 14.5 Persistent Disk Caching and Invalidation

The `TranslationCache` (`src/twi_lab/cache.py`) persists successful translations in `data/cache/translation_cache.json`.

- **Composite SHA-256 Key:** Computed from engine name, engine version, model identifier, source text, context strategy, supplied context string, and generation hyperparameters. If any input changes, a new cache key is produced.
- **Atomic Writes:** Cache files are written via temporary file replacement (`os.replace`) to prevent file corruption during crashes or interrupts.
- **Failures Excluded:** HTTP errors, rate limits, timeouts, and partial responses are **never** stored in the cache.
- **Cache-Only Execution:** Run `--cache-only` to verify an experiment without internet connectivity using pre-cached responses.

### 14.6 Cache Inspection and Deliberate Clearing

```powershell
# Inspect cache statistics (file path, entry count, hit/miss counts, file size):
python -m twi_lab.runner --cache-stats

# Deliberately clear persistent translation cache:
python -m twi_lab.runner --clear-cache
```

### 14.7 Running Phase 3 Experiments

```powershell
# 1. Dry run across all 4 strategies to preview usage and budget:
python -m twi_lab.runner --engine all --title "Dry run all strategies" --context-strategy all --dry-run

# 2. Local OPUS-MT experiment with window_k context (k=2):
python -m twi_lab.runner --engine opus-mt --title "OPUS window_k run" --context-strategy window_k --window-k 2

# 3. Controlled Khaya experiment with budget and explicit confirmation:
python -m twi_lab.runner --engine khaya --title "Khaya glossary run" --context-strategy glossary_guided --khaya-budget 5 --confirm-live-khaya

# 4. Offline run using only cached results:
python -m twi_lab.runner --engine khaya --title "Cached run" --context-strategy none --cache-only
```

---

## 15. Quality and Research Principles

These principles guide all phases of development:

1. **Human-reviewed Asante Twi is the primary quality reference.** Automated metrics are supplementary.
2. **Engine names are hidden during human comparison** (Phase 4). Reviewers evaluate blind.
3. **Context strategies are compared experimentally.** More context is not automatically better.
4. **Fair comparisons use the same source passages and comparable settings** for all engines.
5. **Critical meaning errors are tracked separately** from average quality scores.
6. **Quality, speed, cost, reliability, and editing effort are reported separately.**
7. **Model versions and experiment configurations are stored** for reproducibility.
8. **Source English passages are never modified** after they are added to the dataset.
9. **Data provenance and permissions are recorded** in `source_metadata`.
10. **No engine is declared better before the evaluation supports that conclusion.**
#   T r a n s a l t i o n - b e n c h m a r k  
 