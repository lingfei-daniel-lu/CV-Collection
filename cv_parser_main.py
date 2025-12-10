"""
cv_parser.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from cv_parser_common import docx_to_text, flush_rows_to_csv, safe_json_load
from llm_client import chat_completion
from prompt_templates import JOURNALS, get_prompt

# ───────────────────────── USER SETTINGS ─────────────────────────────── #

BASE_DIR    = Path(__file__).resolve().parent
ROOT_FOLDER = BASE_DIR / "CV_word"
OUT_CSV     = BASE_DIR / "output_sample.csv"

# LLM prompt kept separate for easy edits.
PROMPT = get_prompt()

# ───────────────────────────── MAIN ──────────────────────────────────── #

def main() -> None:
    rows: list[dict] = []
    processed_files: set[str] = set()

    if OUT_CSV.exists():
        old = pd.read_csv(OUT_CSV)
        rows.extend(old.to_dict("records"))
        processed_files.update(old["file"].astype(str))
        print(f"↻  Resuming run – {len(processed_files)} CVs already done.")

    docx_paths = sorted(ROOT_FOLDER.rglob("*.docx"))
##    docx_paths = docx_paths[135:]
    if not docx_paths:
        sys.exit(f"No .docx files found under {ROOT_FOLDER.resolve()}")

    for path in tqdm(docx_paths, desc="Processing CVs"):
        rel = str(path.relative_to(ROOT_FOLDER))
        if rel in processed_files:
            continue

        cv_text = docx_to_text(path)
        if cv_text is None:
            continue

        raw = chat_completion(cv_text, PROMPT)
        data = safe_json_load(raw, label=rel)
        if data is None:
            continue

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

        rows.append(row)
        processed_files.add(rel)

        try:
            flush_rows_to_csv(rows, OUT_CSV, JOURNALS)
        except Exception as e:
            print(f"⚠️  Could not write interim CSV: {e}", file=sys.stderr)

    print("\n✅  Finished! Consolidated table written to", OUT_CSV)

if __name__ == "__main__":
    main()
