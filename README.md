# CV-Collection

Batch pipeline for parsing economics faculty CVs (`.docx`), extracting structured data with multiple LLMs, comparing cross-model outputs, and generating aggregated CSVs for human review.

## 1. Project Goals

- Batch-read faculty CVs from `input/`.
- Extract and normalize core fields:
  - `name`
  - `promotion_year` (first Assistant -> Associate/tenure-track promotion year)
  - `promotion_university`
  - `years_post_phd`
  - Publication counts for 23 economics journals
- Run multiple models in parallel and keep each model output separately.
- Compare model outputs and aggregate by majority voting, with explicit flags for manual review.

## 2. Current Code Functionality

### `scripts/extract_cvs.py`

- Main pipeline script.
- Default model keys: `deepseek,kimi,gpt,gemini,claude`.
- Supports concurrent calls (`CV_CONCURRENCY`, default `4`).
- Supports resume mode: if a same-day output CSV exists for a model, processed files are skipped.
- Writes rows incrementally to CSV to reduce interruption risk.

### `cv_collection/llm_client.py`

- Unified wrapper for OpenAI-compatible APIs across providers.
- Currently configured models:
  - `deepseek-chat`
  - `kimi-k2-thinking`
  - `gpt-5.2` (via Poe)
  - `claude-sonnet-4-6` (via Poe) (used `claude-opus-4-6` for Feb 19th version)
  - `gemini-3-flash` (via Poe)
- Includes exponential-backoff retries (up to 5 attempts).

### `cv_collection/prompt_templates.py`

- Defines the target journal list `JOURNALS` (23 journals).
- Defines the extraction prompt with JSON-only output, tenure/promotion rules, and counting criteria.

### `scripts/compare_model_outputs.py`

- Reads same-date model outputs and compares normalized field-level values.
- Default behavior (without `--date`): process today's outputs only.
- Generates:
  - `compare_<date>_diffs.csv`
  - `compare_<date>_summary.csv`
- Auto-detects field type (`text/number/set`) and compares values by type.

### `scripts/aggregate_model_outputs.py`

- Aggregates same-date outputs by field-level majority voting.
- Default behavior (without `--date`): process today's outputs only.
- If vote ties or all values are missing, marks fields unresolved and writes:
  - `unresolved_count`
  - `unresolved_fields`
  - `unresolved_details`
  - `needs_review`

### `scripts/smoke_test_extract.py`

- Quick small-sample integration test script (default: 2 CVs per model; configurable via `CV_SMOKE_LIMIT`).

### `cv_collection/common_functions.py`

- `.docx` text reader (skips hidden and invalid/non-zip files).
- JSON cleaning/parsing for LLM responses.
- Shared CSV flushing helper.

## 3. Project Structure (Core)

```text
CV-Collection/
├── input/                        # Raw CV files (organized by school/rank)
├── output/
│   ├── output_<model>_<date>.csv # Per-model raw extraction outputs
│   ├── compare/                  # Cross-model comparison outputs
│   └── aggregate/                # Majority-vote aggregation outputs
├── scripts/
│   ├── extract_cvs.py
│   ├── smoke_test_extract.py
│   ├── compare_model_outputs.py
│   ├── aggregate_model_outputs.py
│   └── list_pending_docs.py
├── cv_collection/
│   ├── config.py
│   ├── output_utils.py
│   ├── llm_client.py
│   ├── prompt_templates.py
│   └── common_functions.py
├── local_api_keys.example.py     # API key template for collaborators
└── local_api_keys.py             # Local private keys (gitignored)
```

## 4. How to Run

### 4.1 Requirements

- Python 3.10+
- Main dependencies:
  - `pandas`
  - `tqdm`
  - `python-docx`
  - `openai`
- Input requirement: this pipeline reads `.docx` only. Convert any legacy `.doc` files to `.docx` manually before running.

### 4.2 API Key Rules for Collaborators

- `local_api_keys.py` is the local private key file and is ignored by Git.
- Never commit real API keys to the repository.
- Copy `local_api_keys.example.py` to `local_api_keys.py`, then fill your own keys:
  - `DEEPSEEK_API_KEY`
  - `KIMI_API_KEY`
  - `POE_API_KEY`
- Key resolution order in `cv_collection/llm_client.py`: `local_api_keys.py` first, environment variables second.
- If a required key is missing, the program raises a clear runtime error at import time.

### 4.3 Smoke Test

```bash
python -m scripts.smoke_test_extract
```

Optional:

```bash
CV_SMOKE_LIMIT=3 python -m scripts.smoke_test_extract
```

### 4.4 Full Extraction

```bash
python -m scripts.extract_cvs
```

Optional concurrency:

```bash
CV_CONCURRENCY=6 python -m scripts.extract_cvs
```

### 4.5 Output Comparison (explicit output dir recommended)

```bash
python -m scripts.compare_model_outputs --input-dir output --output-dir output/compare
```

By default, this command only compares output files for today's date.

### 4.6 Multi-Model Aggregation (explicit output dir recommended)

```bash
python -m scripts.aggregate_model_outputs --date 2026-02-18 --input-dir output --output-dir output/aggregate
```

If `--date` is omitted, aggregation runs for today's date only.

## 5. Progress Snapshot (as of 2026-02-19)

### Dataset Scale

- `input/` currently contains `789` `.docx` files.
- There are `2` `.doc` files (not read by code). Convert them to `.docx` manually before extraction.

### Model Output Files

- `2025-12-30`: `deepseek(285)`, `kimi(283)`.
- `2026-02-02`: `deepseek(798)`, `kimi(809)`, `poe(866)` (historical batch; naming not fully aligned with current setup).
- `2026-02-18`:
  - `deepseek(789)`
  - `gpt(789)`
  - `gemini(789)`
  - `kimi(783)` (missing 6)
  - `claude(777)` (missing 12)

### Comparison Results

- Existing `compare` dates: `2025-12-30`, `2026-02-02`, `2026-02-18`.
- `2026-02-18` comparison base size: `789` files.
- Highest-diff fields (`2026-02-18`):
  - `promotion_university`: `diff_rate=0.2801`
  - `AMERICAN ECONOMIC REVIEW`: `diff_rate=0.2433`
  - `years_post_phd`: `diff_rate=0.2357`
  - `promotion_year`: `diff_rate=0.2117`

### Aggregation Results

- Generated: `output/aggregate/aggregate_2026-02-18.csv` (`789` rows).
- Rows with `needs_review=1`: `200` (~`25.35%`).
- Unresolved reason counts (field-level): `tie=209`, `all_missing=142`.

## 6. Known Issues and Risks (Dev Memo)

- Output quality still varies by model; `promotion_*` and `years_post_phd` are the main disagreement fields.
- `.doc` files are not parsed directly; manual conversion to `.docx` is required.

## 7. Next Steps (Priority)

- P1: Add a manual-review workflow script (export subsets where `needs_review=1`).
- P1: Add a lightweight preflight check that lists remaining `.doc` files before run.
- P2: Build a small human-labeled benchmark set to quantify per-field model accuracy.
