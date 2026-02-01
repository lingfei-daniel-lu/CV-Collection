"""
Faster CV parser with cached DOCX text and concurrent model calls.
"""

from __future__ import annotations

import os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from tqdm import tqdm

from common_functions import docx_to_text, flush_rows_to_csv, safe_json_load
from llm_client import get_model_client
from prompt_templates import JOURNALS, get_prompt

# ───────────────────────── USER SETTINGS ─────────────────────────────── #

BASE_DIR    = Path(__file__).resolve().parent
ROOT_FOLDER = BASE_DIR / "CV_word"
OUTPUT_FOLDER = BASE_DIR / "output"
EXPORT_DATE = date.today().isoformat()

MODEL_KEYS = tuple(m for m in os.getenv("CV_MODELS", "deepseek,kimi").split(",") if m)
PROMPT = get_prompt()

CONCURRENCY = int(os.getenv("CV_CONCURRENCY", "4"))  # parallel workers per model

# ───────────────────────────── HELPERS ───────────────────────────────── #


def load_doc_texts(docx_paths: list[Path]) -> list[tuple[str, str]]:
    """Load DOCX files to text once so multiple models reuse the result."""
    texts: list[tuple[str, str]] = []
    for path in docx_paths:
        txt = docx_to_text(path)
        if txt is None:
            continue
        rel = str(path.relative_to(ROOT_FOLDER))
        texts.append((rel, txt))
    return texts


def run_one(cv_text: str, rel: str, client):
    raw = client.chat_completion(cv_text, PROMPT)
    data = safe_json_load(raw, label=rel)
    if data is None:
        return None

    row = {
        "file": rel,
        "name": data.get("name"),
        "promotion_year": data.get("promotion_year"),
        "promotion_university": data.get("promotion_university"),
        "years_post_phd": data.get("years_post_phd"),
    }
    journals = {j: False for j in JOURNALS}
    journals.update(data.get("journals", {}))
    row.update(journals)
    return row


# ───────────────────────────── MAIN LOGIC ────────────────────────────── #


def process_model(model_key: str, docs: list[tuple[str, str]]) -> None:
    out_csv = OUTPUT_FOLDER / f"output_{model_key}_{EXPORT_DATE}.csv"
    client = get_model_client(model_key)

    rows: list[dict] = []
    processed_files: set[str] = set()

    if out_csv.exists():
        try:
            import pandas as pd

            old = pd.read_csv(out_csv)
            rows.extend(old.to_dict("records"))
            processed_files.update(old["file"].astype(str))
            print(f"↻  Resuming {model_key} – {len(processed_files)} CVs already done.")
        except Exception as e:
            print(f"⚠️  Could not load prior CSV for {model_key}: {e}")

    pending = [(rel, text) for rel, text in docs if rel not in processed_files]
    if not pending:
        print(f"✅  {model_key}: nothing new to process.")
        return

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(run_one, text, rel, client): rel for rel, text in pending}
        for fut in tqdm(as_completed(futures), total=len(futures), desc=f"{model_key}: CVs"):
            rel = futures[fut]
            try:
                row = fut.result()
            except Exception as e:
                print(f"⚠️  {model_key} failed on {rel}: {e}")
                continue
            if row is None:
                continue

            rows.append(row)
            processed_files.add(rel)
            flush_rows_to_csv(rows, out_csv, JOURNALS)

    print(f"✅  {model_key} finished. Consolidated table written to {out_csv}")


def main() -> None:
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    docx_paths = sorted(ROOT_FOLDER.rglob("*.docx"))
    if not docx_paths:
        sys.exit(f"No .docx files found under {ROOT_FOLDER.resolve()}")

    docs = load_doc_texts(docx_paths)
    if not docs:
        sys.exit("No readable CVs to process.")

    for model_key in MODEL_KEYS:
        process_model(model_key, docs)

    print("\n✅  All models completed.")


if __name__ == "__main__":
    main()
