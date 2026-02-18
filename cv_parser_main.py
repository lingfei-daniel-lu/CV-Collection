"""
cv_parser.py
"""

from __future__ import annotations

import os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import date

import pandas as pd
from tqdm import tqdm

from common_functions import docx_to_text, flush_rows_to_csv, safe_json_load
from llm_client import get_model_client
from prompt_templates import JOURNALS, get_prompt

# ───────────────────────── USER SETTINGS ─────────────────────────────── #

BASE_DIR    = Path(__file__).resolve().parent
ROOT_FOLDER = BASE_DIR / "CV_word"
OUTPUT_FOLDER = BASE_DIR / "output"
EXPORT_DATE = date.today().isoformat()

# Model selection (defaults to 5 independent outputs in one run).
MODEL_KEYS = ("deepseek", "kimi", "gpt", "gemini", "claude")

# LLM prompt kept separate for easy edits.
PROMPT = get_prompt()
CONCURRENCY = int(os.getenv("CV_CONCURRENCY", "4"))

# ───────────────────────────── MAIN ──────────────────────────────────── #

def build_row(rel: str, data: dict) -> dict:
    row = {
        "file": rel,
        "name": data.get("name"),
        "promotion_year": data.get("promotion_year"),
        "promotion_university": data.get("promotion_university"),
        "years_post_phd": data.get("years_post_phd"),
    }
    journals = {j: 0 for j in JOURNALS}
    raw_journals = data.get("journals", {})
    if not isinstance(raw_journals, dict):
        print(f"⚠️  Invalid journals payload for {rel}; expected object, got {type(raw_journals).__name__}")
        raw_journals = {}
    journals.update(raw_journals)
    row.update(journals)
    return row


def process_model(model_key: str, docs: list[tuple[str, str]]) -> None:
    client = get_model_client(model_key)
    out_csv = OUTPUT_FOLDER / f"output_{model_key}_{EXPORT_DATE}.csv"

    processed_files: set[str] = set()

    if out_csv.exists():
        old = pd.read_csv(out_csv)
        processed_files.update(old["file"].astype(str))
        print(f"↻  Resuming {model_key} – {len(processed_files)} CVs already done.")

    pending = [(rel, text) for rel, text in docs if rel not in processed_files]
    if not pending:
        print(f"✅  {model_key}: nothing new to process.")
        return

    if CONCURRENCY > 1:
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = {pool.submit(client.chat_completion, text, PROMPT): rel for rel, text in pending}
            for fut in tqdm(
                as_completed(futures),
                total=len(futures),
                desc=f"{model_key}: Processing CVs",
            ):
                rel = futures[fut]
                try:
                    raw = fut.result()
                except Exception as e:
                    print(f"⚠️  {model_key} failed on {rel}: {e}")
                    continue
                data = safe_json_load(raw, label=rel)
                if data is None:
                    continue

                row = build_row(rel, data)

                try:
                    flush_rows_to_csv([row], out_csv, JOURNALS)
                except Exception as e:
                    print(f"⚠️  Could not write interim CSV: {e}", file=sys.stderr)

                processed_files.add(rel)
    else:
        for rel, cv_text in tqdm(pending, desc=f"{model_key}: Processing CVs"):
            raw = client.chat_completion(cv_text, PROMPT)
            data = safe_json_load(raw, label=rel)
            if data is None:
                continue

            row = build_row(rel, data)

            try:
                flush_rows_to_csv([row], out_csv, JOURNALS)
            except Exception as e:
                print(f"⚠️  Could not write interim CSV: {e}", file=sys.stderr)

            processed_files.add(rel)

    print(f"\n✅  {model_key} finished. Consolidated table written to {out_csv}")


def main() -> None:
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    docx_paths = sorted(ROOT_FOLDER.rglob("*.docx"))
    if not docx_paths:
        sys.exit(f"No .docx files found under {ROOT_FOLDER.resolve()}")

    docs: list[tuple[str, str]] = []
    for path in docx_paths:
        txt = docx_to_text(path)
        if txt is None:
            continue
        docs.append((str(path.relative_to(ROOT_FOLDER)), txt))
    if not docs:
        sys.exit("No readable CVs to process.")

    for model_key in MODEL_KEYS:
        process_model(model_key, docs)

if __name__ == "__main__":
    main()
