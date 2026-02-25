# CV-Collection

Batch pipeline for parsing economics faculty CVs (`.docx`), extracting structured data with multiple LLMs, comparing cross-model outputs, and generating aggregated CSVs for review.

## Project Goals

- Read faculty CVs from `input/`
- Extract core fields
  - `name`
  - `promotion_year`
  - `promotion_university`
  - `years_post_phd`
  - publication counts for 23 economics journals
- Run multiple models and store per-model outputs separately
- Compare and aggregate outputs across models

## Current Extraction Flow (Staged Pipeline)

The extraction pipeline used by `scripts/extract_cvs.py` and `scripts/smoke_test_extract.py` now uses a staged workflow implemented in `cv_collection/staged_extraction.py`:

1. `.docx` -> structured text-like plain text (paragraphs + tables, preserving order as much as possible)
2. Heuristic section detection (`education`, `employment`, `publications`, etc.)
3. Publication section split into entry-level lines
4. Main extraction
   - metadata extraction with confidence fields
   - publication extraction as per-journal year lists (internal)
5. Targeted reprocessing for low-confidence metadata fields
6. Verification pass (LLM cross-check against original CV text)
7. Convert internal publication year lists back to journal counts for CSV output

Notes:
- Final CSV schema remains journal **counts** (compatible with existing compare/aggregate scripts).
- The staged pipeline performs multiple LLM calls per CV, so it is slower than a single-pass prompt but usually improves extraction robustness.

## Step-Level Cache (New)

The staged pipeline includes disk cache for LLM step results (metadata / publications / retries / verification).

- Cache location: `output/cache/staged_extraction/`
- Cache key includes:
  - model key/name
  - temperature
  - full message payload
  - cache version
- Cache is transparent: cache hit returns the previously parsed JSON for that step

Disable cache temporarily:

```bash
CV_STAGE_CACHE_DISABLE=1 python -m scripts.smoke_test_extract
```

## Core Scripts

### `scripts/extract_cvs.py`

- Main batch extraction pipeline
- Uses the staged extractor (`cv_collection/staged_extraction.py`)
- Supports concurrency via `CV_CONCURRENCY` (default `4`)
- Resume mode: skips files already present in same-day output CSV
- Writes rows incrementally to reduce interruption risk

### `scripts/smoke_test_extract.py`

- Small-sample integration test (default `2` CVs per model)
- Uses staged pipeline, so runtime can be non-trivial
- Configure sample size with `CV_SMOKE_LIMIT`

### `scripts/compare_model_outputs.py`

- Compares same-date model outputs field-by-field
- Generates:
  - `compare_<date>_diffs.csv`
  - `compare_<date>_summary.csv`

### `scripts/aggregate_model_outputs.py`

- Aggregates same-date model outputs by field-level majority voting
- Marks unresolved fields and rows needing review

## Core Modules

### `cv_collection/staged_extraction.py`

- Section detection
- Publication entry splitting
- Metadata extraction with confidence
- Targeted retry for low-confidence fields
- Verification pass
- Step-level LLM response cache

### `cv_collection/common_functions.py`

- `.docx` text extraction (paragraphs + tables, preserving document order where possible)
- JSON cleanup/parsing for LLM responses
- Shared CSV writer

### `cv_collection/llm_client.py`

- Unified OpenAI-compatible API wrapper across providers
- Exponential backoff retry
- Supports both:
  - simple prompt + text calls (`chat_completion`)
  - multi-message calls (`chat_messages`) for staged pipeline

### `cv_collection/prompt_templates.py`

- Canonical journal list (`JOURNALS`, 23 journals)
- Legacy single-pass prompt template (still kept in repo for reference/compatibility)

## Project Structure (Core)

```text
CV-Collection/
├── input/                            # Raw CV files (organized by school/rank)
├── output/
│   ├── output_<model>_<date>.csv     # Per-model extraction outputs (journal counts)
│   ├── cache/
│   │   └── staged_extraction/        # Step-level LLM cache
│   ├── compare/                      # Cross-model comparison outputs
│   └── aggregate/                    # Majority-vote aggregation outputs
├── scripts/
│   ├── extract_cvs.py
│   ├── smoke_test_extract.py
│   ├── compare_model_outputs.py
│   ├── aggregate_model_outputs.py
│   └── list_pending_docs.py
├── cv_collection/
│   ├── config.py
│   ├── llm_client.py
│   ├── staged_extraction.py
│   ├── prompt_templates.py
│   ├── common_functions.py
│   └── output_utils.py
├── local_api_keys.example.py         # API key template for collaborators
└── local_api_keys.py                 # Local private keys (gitignored)
```

## Requirements

- Python 3.10+
- Main dependencies:
  - `pandas`
  - `tqdm`
  - `python-docx`
  - `openai`
- Input requirement: `.docx` only (convert legacy `.doc` manually)

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

### Smoke Test

```bash
python -m scripts.smoke_test_extract
```

Optional (faster):

```bash
CV_SMOKE_LIMIT=1 python -m scripts.smoke_test_extract
```

### Full Extraction

```bash
python -m scripts.extract_cvs
```

Optional concurrency:

```bash
CV_CONCURRENCY=6 python -m scripts.extract_cvs
```

### Compare Model Outputs

```bash
python -m scripts.compare_model_outputs --input-dir output --output-dir output/compare
```

### Aggregate Model Outputs

```bash
python -m scripts.aggregate_model_outputs --date 2026-02-18 --input-dir output --output-dir output/aggregate
```

If `--date` is omitted in compare/aggregate scripts, they process today's outputs by default.

## Notes / Known Constraints

- `.doc` files are not parsed directly.
- Staged extraction may be slow on full runs because each CV can trigger multiple LLM calls.
- Cache significantly helps repeated runs, interrupted resumes, and prompt/threshold tuning cycles.
