"""
Batch CV extraction pipeline.
"""

from __future__ import annotations

import os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from tqdm import tqdm

from cv_collection.config import DEFAULT_MODEL_KEYS, INPUT_ROOT_FOLDER, OUTPUT_FOLDER
from cv_collection.journal_taxonomy import JOURNALS
from cv_collection.llm_client import get_model_client
from cv_collection.research_field_taxonomy import normalize_research_fields
from cv_collection.staged_extraction import extract_cv_staged, infer_rank_from_label
from cv_collection.csv_export import flush_rows_to_csv
from cv_collection.docx_io import docx_to_text

# ───────────────────────── USER SETTINGS ─────────────────────────────── #

EXPORT_DATE = date.today().isoformat()

CONCURRENCY = int(os.getenv("CV_CONCURRENCY", "4"))

JOURNAL_EXPORT_COLS = [f"{j}_count" for j in JOURNALS] + [f"{j}_year" for j in JOURNALS]

# ───────────────────────────── MAIN ──────────────────────────────────── #

def build_row(rel: str, data: dict) -> dict:
    row = {
        "file": rel,
        "rank": data.get("rank") or infer_rank_from_label(rel),
        "name": data.get("name"),
        "research_fields": normalize_research_fields(data.get("research_fields", "")),
        "promotion_year": data.get("promotion_year"),
        "full_promotion_year": data.get("full_promotion_year"),
        "full_promotion_university": data.get("full_promotion_university"),
        "promotion_university": data.get("promotion_university"),
        "years_post_phd": data.get("years_post_phd"),
        "years_post_phd_full": data.get("years_post_phd_full"),
    }
    raw_journal_years = data.get("journal_years", {})
    if not isinstance(raw_journal_years, dict):
        print(
            f"⚠️  Invalid journal_years payload for {rel}; expected object, "
            f"got {type(raw_journal_years).__name__}"
        )
        raw_journal_years = {}

    for journal in JOURNALS:
        years = raw_journal_years.get(journal, [])
        if not isinstance(years, list):
            years = []
        row[f"{journal}_count"] = len(years)
        row[f"{journal}_year"] = "; ".join(str(y) for y in years)
    return row


def fetch_model_response(client, model_key: str, rel: str, cv_text: str) -> dict | None:
    rank = infer_rank_from_label(rel)
    try:
        return extract_cv_staged(client, cv_text, rel, rank=rank)
    except Exception as e:
        print(f"⚠️  {model_key} failed on {rel}: {e}")
        return None


def write_model_result(rel: str, data: dict | None, out_csv: Path) -> bool:
    if data is None:
        return False

    row = build_row(rel, data)

    try:
        flush_rows_to_csv([row], out_csv, JOURNAL_EXPORT_COLS)
    except Exception as e:
        print(f"⚠️  Could not write interim CSV: {e}", file=sys.stderr)
        return False

    return True


def process_model(model_key: str, docs: list[tuple[str, str]]) -> None:
    client = get_model_client(model_key)
    out_csv = OUTPUT_FOLDER / f"output_{model_key}_{EXPORT_DATE}.csv"
    expected_cols = [
        "file",
        "rank",
        "name",
        "research_fields",
        "promotion_year",
        "full_promotion_year",
        "full_promotion_university",
        "promotion_university",
        "years_post_phd",
        "years_post_phd_full",
        *JOURNAL_EXPORT_COLS,
    ]

    processed_files: set[str] = set()

    if out_csv.exists():
        old = pd.read_csv(out_csv)
        old_cols = list(old.columns)
        if old_cols != expected_cols:
            out_csv.unlink()
            print(f"↻  {model_key}: schema changed, overwriting {out_csv.name}")
        else:
            processed_files.update(old["file"].astype(str))
            print(f"↻  Resuming {model_key} – {len(processed_files)} CVs already done.")

    pending = [(rel, text) for rel, text in docs if rel not in processed_files]
    if not pending:
        print(f"✅  {model_key}: nothing new to process.")
        return

    if CONCURRENCY > 1:
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = {
                pool.submit(fetch_model_response, client, model_key, rel, text): rel
                for rel, text in pending
            }
            for fut in tqdm(
                as_completed(futures),
                total=len(futures),
                desc=f"{model_key}: Processing CVs",
            ):
                rel = futures[fut]
                raw = fut.result()
                if write_model_result(rel, raw, out_csv):
                    processed_files.add(rel)
    else:
        for rel, cv_text in tqdm(pending, desc=f"{model_key}: Processing CVs"):
            raw = fetch_model_response(client, model_key, rel, cv_text)
            if write_model_result(rel, raw, out_csv):
                processed_files.add(rel)

    print(f"\n✅  {model_key} finished. Consolidated table written to {out_csv}")


def load_docs() -> list[tuple[str, str]]:
    docx_paths = sorted(INPUT_ROOT_FOLDER.rglob("*.docx"))
    if not docx_paths:
        sys.exit(f"No .docx files found under {INPUT_ROOT_FOLDER.resolve()}")

    docs: list[tuple[str, str]] = []
    for path in docx_paths:
        txt = docx_to_text(path)
        if txt is None:
            continue
        docs.append((str(path.relative_to(INPUT_ROOT_FOLDER)), txt))

    if not docs:
        sys.exit("No readable CVs to process.")

    return docs


def main() -> None:
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    docs = load_docs()

    for model_key in DEFAULT_MODEL_KEYS:
        process_model(model_key, docs)

if __name__ == "__main__":
    main()
