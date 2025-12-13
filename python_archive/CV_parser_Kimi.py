#!/usr/bin/env python
"""
batch_cv_parser.py  — Kimi (Moonshot) edition using kimi-k2-0905-preview
"""

from __future__ import annotations

import json, os, sys, time, zipfile
from pathlib import Path

from openai import OpenAI
import pandas as pd
from docx import Document
from tqdm import tqdm

# ───────────────────────── USER SETTINGS ─────────────────────────────── #

ROOT_FOLDER = Path("/Users/lingfeilu/Documents/CV-Collection")
OUT_CSV     = Path("/Users/lingfeilu/Documents/CV-Collection/test.csv")

# Use the requested model:
MODEL_NAME  = "kimi-k2-0905-preview"
TEMPERATURE = 0.0
MAX_RETRIES = 5

# ───────────────────────── JOURNAL MASTER LIST ───────────────────────── #

JOURNALS = [
    "QUARTERLY JOURNAL OF ECONOMICS",
    "AMERICAN ECONOMIC REVIEW",
    "ECONOMETRICA",
    "REVIEW OF ECONOMIC STUDIES",
    "JOURNAL OF POLITICAL ECONOMY",
    "AMERICAN ECONOMIC JOURNAL-MACROECONOMICS",
    "AMERICAN ECONOMIC JOURNAL-APPLIED ECONOMICS",
    "JOURNAL OF THE EUROPEAN ECONOMIC ASSOCIATION",
    "AMERICAN ECONOMIC JOURNAL-ECONOMIC POLICY",
    "THEORETICAL ECONOMICS",
    "AMERICAN ECONOMIC JOURNAL-MICROECONOMICS",
    "QUANTITATIVE ECONOMICS",
    "REVIEW OF ECONOMICS AND STATISTICS",
    "ECONOMIC JOURNAL",
    "INTERNATIONAL ECONOMIC REVIEW",
    "JOURNAL OF ECONOMIC THEORY",
    "JOURNAL OF LABOR ECONOMICS",
    "JOURNAL OF MONETARY ECONOMICS",
    "RAND JOURNAL OF ECONOMICS",
    "JOURNAL OF INTERNATIONAL ECONOMICS",
    "JOURNAL OF PUBLIC ECONOMICS",
    "JOURNAL OF ECONOMETRICS",
    "JOURNAL OF DEVELOPMENT ECONOMICS",
]

# ───────────────────────────  API KEY  ───────────────────────────────── #

# Kimi’s OpenAI-compatible API endpoint:
client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY"),
    base_url="https://api.moonshot.cn/v1"
)

# ───────────────────────── PROMPT TEMPLATE ───────────────────────────── #

journal_schema_lines = ",\n      ".join(f'"{j}": <int | false>' for j in JOURNALS)

PROMPT_TEMPLATE = f"""
ONLY RETURN JSON. NO MARKDOWN. NO COMMENTARY.

TASK
-----
From the CV I provide, return:
• "name": faculty member’s full name
• "promotion_year": calendar year of promotion to Associate Professor OR Reader
• "promotion_university": institution where the promotion occurred
• "years_post_phd": years between PhD and the promotion
• "journals": object with EXACT journal titles shown below and integer >=1 or false.

IMPORTANT:
Return counts only up to and including the promotion year.
Use null for any unknown field and do NOT wrap JSON in backticks.

JOURNALS:
{chr(10).join('* ' + j for j in JOURNALS)}
"""

# ────────────────────────── HELPERS ───────────────────────────────────── #

def docx_to_text(path: Path) -> str | None:
    if path.name.startswith(".") or not zipfile.is_zipfile(path):
        return None
    try:
        document = Document(path)
    except Exception as e:
        print(f"⚠️  Cannot read {path}: {e}")
        return None
    return "\n".join(p.text for p in document.paragraphs)


def chat_completion(cv_text: str) -> str:
    """Query Kimi model with retries."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "user", "content": PROMPT_TEMPLATE.strip()},
                    {"role": "user", "content": cv_text},
                ]
            )
            return resp.choices[0].message.content.strip()

        except Exception as e:
            if attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            print(f"⚠️  API error: {e}. Retrying in {wait}s …", file=sys.stderr)
            time.sleep(wait)


def safe_json_load(raw: str, *, label: str):
    if not raw:
        print(f"⚠️  Empty response for {label}")
        return None
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.split("```", 2)[1]
    start, end = txt.find("{"), txt.rfind("}")
    if start == -1 or end == -1:
        print(f"⚠️  No JSON braces in response for {label}")
        return None
    try:
        return json.loads(txt[start : end + 1])
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON decode failed for {label}: {e}")
        return None


def flush_rows_to_csv(rows: list[dict]):
    df = pd.DataFrame(rows)
    first_cols = [
        "file",
        "name",
        "promotion_year",
        "promotion_university",
        "years_post_phd",
    ]
    if not df.empty:
        df = df[first_cols + JOURNALS]
    df.to_csv(OUT_CSV, index=False)

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
    docx_paths = docx_paths[135:]
    if not docx_paths:
        sys.exit(f"No .docx files found under {ROOT_FOLDER.resolve()}")

    for path in tqdm(docx_paths, desc="Processing CVs"):
        rel = str(path.relative_to(ROOT_FOLDER))
        if rel in processed_files:
            continue

        cv_text = docx_to_text(path)
        if cv_text is None:
            continue

        raw = chat_completion(cv_text)
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
            flush_rows_to_csv(rows)
        except Exception as e:
            print(f"⚠️  Could not write interim CSV: {e}", file=sys.stderr)

    print("\n✅  Finished! Consolidated table written to", OUT_CSV)


if __name__ == "__main__":
    main()