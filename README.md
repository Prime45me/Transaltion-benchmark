# Twi Translation Benchmark Lab

An experimental research tool for comparing English-to-Asante Twi translation engines on children's stories. It combines local and cloud translation engines with controlled narrative-context strategies, reproducible experiment records, and a benchmark dataset designed for later human review.

> **Project status:** Phases 1–3 are implemented. The shared human-review workspace (Phase 4) and analysis/reporting features (Phase 5) are planned.

## At a glance

| | |
|---|---|
| **Language pair** | English → Asante Twi |
| **Python** | 3.10+ |
| **Engines** | OPUS-MT (local), Khaya / GhanaNLP (API) |
| **Test suite** | `pytest` |
| **Current dataset** | 25 development-fixture passages across 16 linguistic categories |

This repository is an evaluation tool, not a production storytelling application, public translation service, payment system, or user-account system. Its sample passages are development fixtures, not a validated or representative linguistic benchmark.

## Contents

- [Project roadmap](#project-roadmap)
- [Quick start](#quick-start)
- [Optional translation engines](#optional-translation-engines)
- [Configuration](#configuration)
- [Dataset](#dataset)
- [Running experiments](#running-experiments)
- [Context strategies, caching, and budgeting](#context-strategies-caching-and-budgeting)
- [Testing](#testing)
- [Repository layout](#repository-layout)
- [Limitations and research principles](#limitations-and-research-principles)

## Project roadmap

| Phase | Focus | Status |
|---|---|---|
| 1 | Foundation, dataset, and infrastructure | Complete |
| 2 | OPUS-MT and Khaya translation engines | Complete |
| 3 | Context experiments, caching, and call budgeting | Complete |
| 4 | Shared human-review workspace | Planned |
| 5 | Analysis and reporting | Planned |

The planned hosted review interface is described in [`docs/deployment_architecture.md`](docs/deployment_architecture.md).

## Quick start

### Requirements

- Python 3.10 or later (3.12 recommended)
- Git
- Internet access to install dependencies; engine-specific network requirements are described below
- No GPU required for the default CPU setup

### Create an environment and install

**Windows PowerShell**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

This installs the package and test dependencies. To use the Khaya API, install its optional HTTP dependency as well:

```bash
pip install -e ".[dev,phase2]"
```

Validate the sample dataset:

```bash
python -m twi_lab.dataset --validate
```

Run the test suite:

```bash
pytest
```

## Optional translation engines

### Khaya / GhanaNLP API

Khaya sends requests to the GhanaNLP translation service and requires internet access and an API key. Install the optional API dependency:

```bash
pip install -e ".[phase2]"
```

Create a local `.env` file in the project root (or set the environment variables in your shell) and add your key:

```dotenv
KHAYA_API_KEY=your_api_key
KHAYA_API_BASE_URL=https://translation-api.ghananlp.org/v1
KHAYA_TIMEOUT_SECONDS=30
```

An optional `KHAYA_API_SECONDARY_KEY` can be configured for key failover. Never commit API keys, `.env` files, or credential files.

Before running a live batch, review the [Khaya call budget and confirmation controls](#khaya-budget-and-live-call-controls).

### OPUS-MT local model

OPUS-MT runs locally using Hugging Face Transformers. Install its optional dependencies:

```bash
pip install -e ".[phase2-opus]"
```

Download the model once:

```bash
python -m twi_lab.engines.opus_mt --download
```

The model files are stored under `models/opus-mt-en-tw` and are excluded from Git. After download, inference runs locally; CPU is the default, and a GPU is not required.

## Configuration

Settings are read from environment variables and, if present, a `.env` file in the project root. Paths can be relative to the project root or absolute.

| Variable | Default | Description |
|---|---|---|
| `PROJECT_ENV` | `development` | Runtime environment: `development`, `testing`, or `production` |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `DATASET_PATH` | `data/samples/passages.jsonl` | Benchmark passage dataset |
| `MANIFEST_PATH` | `data/samples/manifest.json` | Dataset metadata |
| `RESULTS_DIR` | `results` | Experiment output directory |
| `LOGS_DIR` | `logs` | Log output directory |
| `CACHE_PATH` | `data/cache/translation_cache.json` | Persistent translation cache |
| `SUMMARIES_PATH` | `data/samples/summaries.json` | Authored story summaries |
| `GLOSSARY_PATH` | `data/samples/glossary.json` | Approved terminology |
| `KHAYA_API_KEY` | *(unset)* | Khaya API credential |
| `KHAYA_API_SECONDARY_KEY` | *(unset)* | Optional fallback credential |
| `KHAYA_API_BASE_URL` | `https://translation-api.ghananlp.org/v1` | Khaya / GhanaNLP API base URL |
| `KHAYA_TIMEOUT_SECONDS` | `30` | Khaya request timeout |
| `KHAYA_CALL_BUDGET` | `10` | Maximum allowed live Khaya calls per run |
| `OPUS_MT_MODEL_NAME` | `Helsinki-NLP/opus-mt-en-tw` | Hugging Face model identifier |
| `OPUS_MT_MODEL_DIR` | `models/opus-mt-en-tw` | Local model directory |
| `LOCAL_DEVICE` | `cpu` | Local inference device (`cpu` or `cuda`) |

## Dataset

The benchmark dataset is [`data/samples/passages.jsonl`](data/samples/passages.jsonl), with one JSON object per line. Each record requires:

| Field | Type | Description |
|---|---|---|
| `story_id` | string | Stable story identifier |
| `passage_id` | string | Unique passage identifier across the dataset |
| `category` | string | Linguistic phenomenon represented |
| `english` | string | Non-empty English source passage |

Optional fields include `story_context`, `character_names`, `glossary`, `reference_twi`, `reference_status`, `review_status`, and `source_metadata`. A `human_reviewed` reference status requires a non-empty reference translation. Do not invent Asante Twi references; qualified reviewers should supply and approve them.

The 16 supported categories are:

```text
simple_sentence              pronouns_character_ref       dialogue
multiple_characters          event_order_tense            cause_and_effect
ambiguous_reference          idioms_figurative             cultural_context
character_name_consistency   descriptions_relationships   child_friendly_vocabulary
questions_and_commands       negation                      long_range_context
completeness_boundaries
```

### Add a passage

1. Add one valid JSON object per line to `data/samples/passages.jsonl`; do not separate records with commas.
2. Use a unique `passage_id` and one of the supported categories.
3. Keep `reference_twi` empty and `reference_status` set to `"absent"` until a qualified Asante Twi reviewer approves a translation.
4. Validate the dataset and update the counts and categories in `data/samples/manifest.json`:

   ```bash
   python -m twi_lab.dataset --validate
   ```

### Dataset validation

```bash
python -m twi_lab.dataset --validate
python -m twi_lab.dataset --validate --dataset path/to/passages.jsonl
python -m twi_lab.dataset --validate --verbose
```

The validator exits with `0` when records are valid, `1` when validation fails, and `2` for a configuration or argument error. The equivalent installed command is `twi-validate`.

## Running experiments

The runner writes an experiment manifest (`experiment_<id>.json`) and a JSONL file of translation results (`results_<id>.jsonl`) to `results/`.

```bash
# Preview an all-engine run without translating
python -m twi_lab.runner --engine all --title "Setup check" --dry-run

# Run OPUS-MT on selected passages
python -m twi_lab.runner --engine opus-mt --title "OPUS-MT baseline" \
  --passages STORY-001-P01 STORY-001-P02

# Run a Khaya experiment (requires a key and explicit live-call confirmation)
python -m twi_lab.runner --engine khaya --title "Khaya baseline" \
  --passages STORY-001-P01 STORY-001-P02 --confirm-live-khaya
```

The installed command is `twi-run`. Use `--help` to see all available options.

### Khaya budget and live-call controls

- The runner estimates cache hits, duplicate requests, and live calls before dispatch.
- The default maximum is 10 live Khaya calls per experiment; override it with `--khaya-budget` or `KHAYA_CALL_BUDGET`.
- If the estimated number exceeds the budget, the run aborts before sending requests.
- Live Khaya batch runs require `--confirm-live-khaya`.
- `--dry-run` previews the run without calling an engine.
- `--cache-only` prevents live requests and requires results to be available in the cache.

## Context strategies, caching, and budgeting

Phase 3 adds four controlled strategies, selected with `--context-strategy`:

| Strategy | Behavior |
|---|---|
| `none` | Translates the target passage without added context |
| `window_k` | Supplies up to *k* preceding sentences from the same story; defaults to `k=1` |
| `story_summary` | Uses an existing human-authored summary from `data/samples/summaries.json` |
| `glossary_guided` | Supplies approved terms and character names from the glossary data |
| `all` | Runs all four strategies |

Unavailable summaries or unmatched glossary terms are recorded as unavailable or empty; the runner does not generate summaries or invent terminology. Passages remain intact as translation targets. When context is supplied, both engines receive the same constructed input, while the original source and context provenance are retained separately in each result.

The persistent cache is stored at `data/cache/translation_cache.json`. Its key includes engine/model details, source text, context, and generation settings. Only successful translations are cached, and cache writes are atomic.

```powershell
# Preview all context strategies
python -m twi_lab.runner --engine all --title "Context preview" `
  --context-strategy all --dry-run

# Run OPUS-MT with the two preceding sentences as context
python -m twi_lab.runner --engine opus-mt --title "Window context" `
  --context-strategy window_k --window-k 2

# Run only from previously cached results
python -m twi_lab.runner --engine khaya --title "Cached run" `
  --context-strategy none --cache-only

# Inspect or clear the persistent cache
python -m twi_lab.runner --cache-stats
python -m twi_lab.runner --clear-cache
```

## Testing

Run the full test suite:

```bash
pytest
```

Tests use mocks and temporary files. They do not call the Khaya API or require downloading the OPUS-MT model.

## Repository layout

```text
data/
  samples/              Benchmark passages, manifest, summaries, and glossary
src/twi_lab/
  engines/              Shared engine interface, Khaya, and OPUS-MT adapters
  cache.py              Persistent translation cache
  config.py             Settings and path resolution
  context.py            Context strategy construction
  dataset.py            Dataset loading, validation, and CLI
  runner.py             Experiment orchestration and CLI
  schemas.py            Validated data models
tests/                  Unit and integration tests
docs/
  deployment_architecture.md
pyproject.toml           Package metadata and optional dependencies
```

Generated experiment results, logs, local model weights, virtual environments, and local secret files are excluded from Git. Benchmark source data under `data/samples/` is tracked.

## Limitations and research principles

- The 25 passages are original development fixtures, not a linguistically validated or representative benchmark. Coverage, balance, and difficulty have not been independently calibrated.
- No human-reviewed Asante Twi references are currently included, so reference-based quality metrics cannot yet be calculated.
- There is no shared human-review interface; that is planned for Phase 4.
- Automated analysis and reporting are planned for Phase 5.
- Neither engine is assumed to be better without evidence from the evaluation.

Research principles:

1. Human-reviewed Asante Twi is the primary quality reference; automated metrics are supplementary.
2. Engine identities should be hidden during human comparison.
3. Context strategies must be compared experimentally; more context is not automatically better.
4. Fair comparisons use the same source passages and comparable settings.
5. Critical meaning errors should be tracked separately from average scores.
6. Quality, speed, cost, reliability, and editing effort should be reported separately.
7. Model versions, configurations, and data provenance should be preserved for reproducibility.
