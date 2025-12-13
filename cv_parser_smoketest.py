"""
Quick smoke test to verify model calls on a small CV sample.
"""

from __future__ import annotations

import json, os, sys
from pathlib import Path

from cv_parser_common import docx_to_text, safe_json_load
from llm_client import MODEL_CONFIGS, get_model_client
from prompt_templates import get_prompt


BASE_DIR = Path(__file__).resolve().parent
ROOT_FOLDER = BASE_DIR / "CV_word"

# Comma-separated env var (CV_MODELS) controls which providers run; defaults to deepseek + kimi.
MODEL_KEYS = tuple(
    m for m in os.getenv("CV_MODELS", "deepseek,kimi").split(",") if m
)

# Limit how many CVs are sent to each model (default: 2).
SAMPLE_LIMIT = int(os.getenv("CV_SMOKE_LIMIT", "2"))

PROMPT = get_prompt()


def smoke_model(model_key: str, docx_paths: list[Path]) -> None:
    client = get_model_client(model_key)

    for path in docx_paths:
        rel = str(path.relative_to(ROOT_FOLDER))
        cv_text = docx_to_text(path)
        if cv_text is None:
            print(f"⚠️  Skipping unreadable file: {rel}")
            continue

        print(f"\n── {model_key}: {rel} ──")
        try:
            raw = client.chat_completion(cv_text, PROMPT)
        except Exception as e:
            print(f"⚠️  API call failed for {rel}: {e}")
            continue

        data = safe_json_load(raw, label=rel)
        if data is None:
            print("Raw response:\n", raw)
            continue

        # Print a concise summary so we can quickly validate the model output.
        summary = {
            "name": data.get("name"),
            "promotion_year": data.get("promotion_year"),
            "promotion_university": data.get("promotion_university"),
            "years_post_phd": data.get("years_post_phd"),
        }
        print(json.dumps(summary, indent=2))


def main() -> None:
    docx_paths = sorted(ROOT_FOLDER.rglob("*.docx"))
    if not docx_paths:
        sys.exit(f"No .docx files found under {ROOT_FOLDER.resolve()}")

    sample = docx_paths[:SAMPLE_LIMIT]
    if not sample:
        sys.exit("No CVs selected for smoke test.")

    print(
        f"Running smoke test on {len(sample)} CV(s): "
        + ", ".join(str(p.relative_to(ROOT_FOLDER)) for p in sample)
    )

    for model_key in MODEL_KEYS:
        print(f"\n=== {model_key} ===")
        smoke_model(model_key, sample)

    print("\n✅  Smoke test completed.")


if __name__ == "__main__":
    main()
