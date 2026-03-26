# CV-Collection

Batch pipeline for parsing economics faculty CVs (`.docx`) with multiple LLMs, extracting structured metadata, comparing model outputs, and aggregating them for review.

## What It Extracts

For each CV, the current pipeline writes:

- `name`
- `research_fields`
- `promotion_year`
- `promotion_university`
- `years_post_phd`
- `full_promotion_year`
- `full_promotion_university`
- `years_post_phd_full`
- journal publication counts and matched years for the target economics journal list

`research_fields` is intentionally conservative:

- prefer explicit CV evidence over topic inference
- use local section/fallback rules first when possible
- normalize to standard economics field labels
- keep primary fields only when the CV distinguishes primary vs secondary

## Environment

Dependencies are declared in `environment.yml`.

Current environment file targets:

- Python `3.13`
- `openai`
- `python-docx`
- `pandas`
- `tqdm`

Create or update the conda environment as usual from `environment.yml`.

## API Keys

The active model configuration in `cv_collection/llm_client.py` currently routes all configured models through Poe's OpenAI-compatible API.

Required:

- `POE_API_KEY`

Resolution order:

1. `local_api_keys.py`
2. environment variables

`local_api_keys.example.py` provides the template for local-only configuration.

## Current Extraction Flow

The main staged pipeline lives in `cv_collection/staged_extraction.py`.

High-level flow:

1. Read `.docx` files in document order with `cv_collection/docx_io.py`
2. Detect local sections with `cv_collection/section_taxonomy.py`
3. Extract local `research_fields` from:
   - explicit `research_interests` sections
   - cautious explicit-label fallback when no usable section is found
4. Run metadata extraction for the promotion / institution fields
5. For full professors, extract the additional full-promotion fields from the same promotion-focused context
6. Keep `research_fields` on the local section/fallback path; it does not participate in metadata verification
7. Split publications heuristically and extract target-journal publication years
8. Retry low-confidence metadata fields in one targeted LLM call
9. Run verification only when extraction appears risky
10. Write per-model CSV output

Important current behavior:

- repeated section headers are preserved and concatenated
- verification is conditional, not mandatory
- promotion metadata and verification stay close to the older `education + employment` logic
- journal years are normalized from lists and scalar year responses
- final CSV keeps journal counts, while internal extraction keeps matched year lists

## Research Field Logic

Research field behavior is split cleanly across two modules:

- `cv_collection/research_field_taxonomy.py`
  - canonical economics field labels
  - alias matching
  - normalization and noise filtering
- `cv_collection/section_taxonomy.py`
  - section header rules
  - explicit-label fallback rules
  - local research-field extraction helpers

The fallback is deliberately narrow. It is meant to improve recall on CVs with explicit labels such as `Fields of Interest:` or `Major Fields of Interest` without opening the door to publication-title noise.

## Prompt Architecture

Prompt content is split into:

- `cv_collection/prompt_rules.py`
  - shared extraction rules
  - promotion and institution rules
  - research-field rules
  - publication counting / matching rules
- `cv_collection/staged_prompts.py`
  - staged metadata prompt
  - publication prompt
  - targeted retry prompt
  - verification prompt

## Cache

The staged pipeline caches parsed JSON for each LLM step under:

```text
output/cache/staged_extraction/
```

Cache keys include:

- model key
- model name
- temperature
- full message payload
- cache version

Disable cache for one run:

```bash
CV_STAGE_CACHE_DISABLE=1 python -m scripts.smoke_test_extract
```

Clean cache and Python bytecode:

```bash
python -m scripts.clean_cache
```

## Main Scripts

### `scripts/smoke_test_extract.py`

Small-sample integration test.

- default sample size: `1`
- uses the first sorted `.docx` files under `input/`
- prints both final `research_fields` and `local_research_fields` for debugging

Example:

```bash
python -m scripts.smoke_test_extract
CV_SMOKE_LIMIT=2 python -m scripts.smoke_test_extract
```

### `scripts/extract_cvs.py`

Main multi-model batch extractor.

- resumes from same-day per-model CSVs when schema matches
- writes rows incrementally
- supports `CV_CONCURRENCY`

Example:

```bash
python -m scripts.extract_cvs
CV_CONCURRENCY=6 python -m scripts.extract_cvs
```

### `scripts/extract_cvs_gemini.py`

Gemini-only entrypoint that reuses the same batch logic.

Example:

```bash
python -m scripts.extract_cvs_gemini
```

### `scripts/compare_model_outputs.py`

Compares same-date model outputs field by field.

Outputs:

- `output/compare/compare_<date>_diffs.csv`
- `output/compare/compare_<date>_summary.csv`

Example:

```bash
python -m scripts.compare_model_outputs --input-dir output --output-dir output/compare
```

### `scripts/aggregate_model_outputs.py`

Aggregates same-date model outputs by field-level voting.

Current rule:

- at least 3 non-empty votes
- one value must win strictly more than half of non-empty votes
- otherwise the field stays blank and is marked unresolved

Example:

```bash
python -m scripts.aggregate_model_outputs --date 2026-03-01 --input-dir output --output-dir output/aggregate
```

### `scripts/list_pending_docs.py`

Helper for identifying remaining legacy `.doc` files that still need conversion.

## Repository Layout

```text
CV-Collection/
├── input/
├── output/
│   ├── output_<model>_<date>.csv
│   ├── cache/
│   │   └── staged_extraction/
│   ├── compare/
│   └── aggregate/
├── scripts/
│   ├── extract_cvs.py
│   ├── extract_cvs_gemini.py
│   ├── smoke_test_extract.py
│   ├── clean_cache.py
│   ├── compare_model_outputs.py
│   ├── aggregate_model_outputs.py
│   └── list_pending_docs.py
├── cv_collection/
│   ├── config.py
│   ├── csv_export.py
│   ├── docx_io.py
│   ├── journal_taxonomy.py
│   ├── json_parsing.py
│   ├── llm_client.py
│   ├── output_utils.py
│   ├── prompt_rules.py
│   ├── staged_prompts.py
│   ├── research_field_taxonomy.py
│   ├── section_taxonomy.py
│   └── staged_extraction.py
├── environment.yml
├── local_api_keys.example.py
└── local_api_keys.py
```

## Practical Notes

- Input format is `.docx` only. Legacy `.doc` files should be converted first.
- Section detection and publication splitting are heuristic by design.
- `research_fields` is restricted to explicit, economics-style field labels, not inferred publication topics.
- Smoke testing is the fastest way to validate prompt or taxonomy changes before a larger rerun.
- If you want a clean rerun for today's date, remove the corresponding `output/output_<model>_<date>.csv` files first; otherwise batch extraction resumes.
