# CV-Collection

Batch pipeline for parsing economics faculty CVs (`.docx`) with multiple LLMs, extracting structured fields, comparing model outputs, and aggregating results for review.

## Project Goals

- Read faculty CVs from `input/`
- Extract core fields:
  - `name`
  - `promotion_year`
  - `promotion_university`
  - `years_post_phd`
  - publication counts for 23 target economics journals
- Run multiple models and store per-model outputs separately
- Compare and aggregate outputs across models

## Current Extraction Flow (Staged Pipeline)

`scripts/extract_cvs.py` and `scripts/smoke_test_extract.py` use the staged extractor in `cv_collection/staged_extraction.py`.

High-level flow:

1. `.docx` -> plain text (`paragraphs + tables`, preserving order as much as possible)
2. Heuristic section detection (`education`, `employment`, `publications`, etc.)
   - If the same section header appears multiple times (e.g., multiple publication blocks), matched chunks are preserved and concatenated instead of overwritten.
3. Publication entry splitting (heuristic line grouping)
4. Main extraction
   - metadata extraction with confidence scores
   - publication extraction as per-journal year lists (internal representation)
5. Targeted metadata retry
   - low-confidence metadata fields are retried in **one combined LLM call** (not one call per field)
   - fields are only updated when retry confidence is higher than the original confidence
6. Conditional verification pass (LLM)
   - verification is **not** run for every CV
   - triggered only when extraction appears risky (e.g., low metadata confidence, missing key sections, or publication/working-paper ambiguity)
7. Safe verification context assembly
   - avoids risky truncation
   - prefers full evidence blocks that fit the limit
   - may skip verification if no safe context fits
8. Convert internal publication year lists back to journal counts for CSV output

Notes:

- Final CSV schema remains journal **counts** (compatible with compare/aggregate scripts).
- Verification is intentionally conservative: it may be skipped rather than run on truncated evidence.
- If no `publications` section is detected, verification may still correct metadata (when safe), but journal corrections are not applied.

## Prompt / Rule Architecture (Current)

Prompt logic is now split into shared rules + flow-specific prompt builders.

### Shared Rule / Taxonomy Modules

- `cv_collection/journal_taxonomy.py`
  - Canonical `JOURNALS` list (23 journals)
  - Journal abbreviation hint lines used by prompts
- `cv_collection/prompt_rules.py`
  - Shared extraction rules (single source of truth)
  - tenure/promotion rules (including `Reader`)
  - source priority / exclusions / mid-career fallback
  - PhD / `years_post_phd` rules
  - institution naming rules
  - publication counting + dedup rules

### Prompt Builder Modules

- `cv_collection/staged_prompts.py`
  - metadata prompt
  - publication prompt
  - combined metadata retry prompt
  - verification prompt
- `cv_collection/legacy_prompts.py`
  - legacy single-pass prompt builder (backup / reference)

### Compatibility Wrapper

- `cv_collection/prompt_templates.py`
  - kept as a compatibility layer for older imports
  - re-exports `JOURNALS` and legacy single-pass prompt access

## Step-Level Cache

The staged pipeline caches parsed JSON results for each LLM step (metadata / publications / retry / verification).

- Cache location: `output/cache/staged_extraction/`
- Cache key includes:
  - model key / model name
  - temperature
  - full message payload
  - cache version
- Cache is transparent: a cache hit returns the previously parsed JSON for that step

Disable cache temporarily:

```bash
CV_STAGE_CACHE_DISABLE=1 python3 -m scripts.smoke_test_extract
```

### Cache Cleanup

Use the cleanup script to remove:

- `__pycache__` directories
- `.pyc` files
- `output/cache/`

```bash
python3 -m scripts.clean_cache
```

Notes:

- Cache files are disposable / reproducible.
- `output/cache/` should be ignored by git (already in `.gitignore`).

## Core Scripts

### `scripts/extract_cvs.py`

- Main batch extraction pipeline
- Uses staged extraction (`cv_collection/staged_extraction.py`)
- Supports concurrency via `CV_CONCURRENCY` (default `4`)
- Resume mode: skips files already present in same-day output CSV
- Writes rows incrementally to reduce interruption risk

### `scripts/smoke_test_extract.py`

- Small-sample integration test (default `2` CVs per model)
- Uses staged pipeline
- Configure sample size with `CV_SMOKE_LIMIT`

### `scripts/clean_cache.py`

- Removes Python cache artifacts (`__pycache__`, `.pyc`)
- Removes project output cache (`output/cache/`)

### `scripts/compare_model_outputs.py`

- Compares same-date model outputs field-by-field
- Generates:
  - `compare_<date>_diffs.csv`
  - `compare_<date>_summary.csv`

### `scripts/aggregate_model_outputs.py`

- Aggregates same-date model outputs by field-level majority voting
- Marks unresolved fields and rows needing review

### `scripts/list_pending_docs.py`

- Helper script to inspect pending/remaining CVs (if used in your workflow)

## Core Modules

### `cv_collection/staged_extraction.py`

- Section detection
- Duplicate section preservation (same-name sections are concatenated)
- Publication entry splitting
- Metadata extraction with confidence scores
- Combined targeted retry for low-confidence metadata fields
- Conditional verification trigger
- Safe verification context construction (no risky truncation)
- Step-level LLM response cache

### `cv_collection/common_functions.py`

- `.docx` text extraction (paragraphs + tables, preserving document order where possible)
- JSON cleanup/parsing for LLM responses
- Shared CSV writer

### `cv_collection/llm_client.py`

- Unified OpenAI-compatible API wrapper across providers
- Exponential backoff retry
- Supports:
  - prompt + text calls (`chat_completion`, legacy-compatible wrapper)
  - multi-message calls (`chat_messages`, used by staged pipeline)

## Project Structure (Core)

```text
CV-Collection/
├── input/                              # Raw CV files (organized by school/rank)
├── output/
│   ├── output_<model>_<date>.csv       # Per-model extraction outputs (journal counts)
│   ├── cache/                          # Step-level cache (gitignored)
│   │   └── staged_extraction/
│   ├── compare/                        # Cross-model comparison outputs
│   └── aggregate/                      # Majority-vote aggregation outputs
├── scripts/
│   ├── extract_cvs.py
│   ├── smoke_test_extract.py
│   ├── clean_cache.py
│   ├── compare_model_outputs.py
│   ├── aggregate_model_outputs.py
│   └── list_pending_docs.py
├── cv_collection/
│   ├── config.py
│   ├── llm_client.py
│   ├── common_functions.py
│   ├── staged_extraction.py
│   ├── journal_taxonomy.py
│   ├── prompt_rules.py
│   ├── staged_prompts.py
│   ├── legacy_prompts.py
│   ├── prompt_templates.py             # Compatibility wrapper (legacy imports)
│   └── output_utils.py
├── local_api_keys.example.py           # API key template for collaborators
└── local_api_keys.py                   # Local private keys (gitignored)
```

## Requirements

- Python 3.10+
- Main dependencies:
  - `pandas`
  - `tqdm`
  - `python-docx`
  - `openai`
- Input requirement: `.docx` only (convert legacy `.doc` manually)

Install missing dependencies (example):

```bash
python3 -m pip install pandas tqdm python-docx openai
```

## API Keys (Collaborators)

- `local_api_keys.py` is local-only and gitignored
- Copy `local_api_keys.example.py` to `local_api_keys.py`
- Fill required keys:
  - `DEEPSEEK_API_KEY`
  - `KIMI_API_KEY`
  - `POE_API_KEY`
- Resolution order in `cv_collection/llm_client.py`:
  1. `local_api_keys.py`
  2. environment variables

## How to Run

### Smoke Test (Recommended First)

```bash
python3 -m scripts.smoke_test_extract
```

Optional (faster):

```bash
CV_SMOKE_LIMIT=1 python3 -m scripts.smoke_test_extract
```

### Full Extraction

```bash
python3 -m scripts.extract_cvs
```

Optional concurrency:

```bash
CV_CONCURRENCY=6 python3 -m scripts.extract_cvs
```

### Compare Model Outputs

```bash
python3 -m scripts.compare_model_outputs --input-dir output --output-dir output/compare
```

### Aggregate Model Outputs

```bash
python3 -m scripts.aggregate_model_outputs --date 2026-02-18 --input-dir output --output-dir output/aggregate
```

If `--date` is omitted in compare/aggregate scripts, they process today's outputs by default.

## Pre-Run Checklist (Before a New Full Extraction)

1. Confirm dependencies are installed (`python-docx`, `openai` are required).
2. Confirm API keys are configured (`local_api_keys.py` or environment variables).
3. Decide whether to clean caches:
   - `python3 -m scripts.clean_cache`
4. Decide whether to fully rerun today's outputs:
   - `scripts/extract_cvs.py` resumes from same-day output CSVs
   - delete same-day `output/output_<model>_<date>.csv` files if you want a clean rerun
5. Run a smoke test (`scripts/smoke_test_extract.py`) before the full batch.
6. Adjust `CV_CONCURRENCY` if your provider rate limits or errors increase.

## Notes / Known Constraints

- `.doc` files are not parsed directly.
- Section detection and publication splitting are heuristic (not guaranteed on every CV format).
- Verification is conditional and may be skipped when no safe context fits within the limit.
- Cache significantly helps repeated runs, interrupted resumes, and prompt/threshold tuning cycles.
