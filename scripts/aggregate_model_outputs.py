#!/usr/bin/env python3
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from cv_collection.config import AGGREGATE_OUTPUT_FOLDER, DEFAULT_MODEL_KEYS, OUTPUT_FOLDER
from cv_collection.output_utils import (
    detect_field_type,
    is_missing,
    normalize_value,
    parse_output_files,
    read_output_rows,
)

def choose_output_value(raw_values: list[str]) -> str:
    counts = Counter(raw_values)
    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))[0][0]


def aggregate_date(date: str, model_paths: dict[str, str], models: list[str], output_dir: str, output_file: str | None):
    model_rows = {}
    all_fields = set()
    for model in models:
        rows, fieldnames = read_output_rows(model_paths[model])
        model_rows[model] = rows
        all_fields.update(fieldnames)

    all_fields.discard("file")
    all_fields = sorted(all_fields)
    all_files = sorted({f for rows in model_rows.values() for f in rows.keys()})

    field_types = {}
    for field in all_fields:
        values = []
        for model in models:
            for row in model_rows[model].values():
                values.append(row.get(field, ""))
        field_types[field] = detect_field_type(values)

    final_rows = []
    for file_key in all_files:
        out = {"file": file_key}
        unresolved = {}
        for field in all_fields:
            votes = defaultdict(list)
            for model in models:
                row = model_rows[model].get(file_key)
                raw = "" if row is None else row.get(field, "")
                if is_missing(raw):
                    continue
                norm = normalize_value(field_types[field], raw)
                if not norm:
                    continue
                votes[norm].append(str(raw).strip())

            if not votes:
                out[field] = ""
                unresolved[field] = "all_missing"
                continue

            max_count = max(len(v) for v in votes.values())
            winners = [k for k, v in votes.items() if len(v) == max_count]
            if len(winners) != 1:
                out[field] = ""
                unresolved[field] = "tie"
                continue

            winner_norm = winners[0]
            out[field] = choose_output_value(votes[winner_norm])

        out["unresolved_count"] = len(unresolved)
        out["unresolved_fields"] = "; ".join(sorted(unresolved.keys()))
        out["unresolved_details"] = json.dumps(unresolved, ensure_ascii=False, sort_keys=True)
        out["needs_review"] = 1 if unresolved else 0
        final_rows.append(out)

    out_name = output_file or f"aggregate_{date}.csv"
    out_path = os.path.join(output_dir, out_name)
    meta_cols = ["unresolved_count", "unresolved_fields", "unresolved_details", "needs_review"]
    ordered_cols = ["file"] + all_fields + meta_cols
    df_out = pd.DataFrame(final_rows)
    if df_out.empty:
        df_out = pd.DataFrame(columns=ordered_cols)
    else:
        for col in ordered_cols:
            if col not in df_out.columns:
                df_out[col] = ""
        df_out = df_out[ordered_cols]
    df_out.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_path, len(df_out), int((df_out["needs_review"] == 1).sum()) if not df_out.empty else 0


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate model outputs by majority voting for one target date."
    )
    parser.add_argument(
        "--date",
        help="Specific date (YYYY-MM-DD). If omitted, process today's date only.",
    )
    parser.add_argument(
        "--input-dir",
        default=str(OUTPUT_FOLDER),
        help="Directory containing output_*.csv files.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(AGGREGATE_OUTPUT_FOLDER),
        help="Directory to write aggregate_*.csv files.",
    )
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODEL_KEYS),
        help="Comma-separated model keys to aggregate (default: deepseek,kimi,gpt,claude,gemini).",
    )
    parser.add_argument(
        "--output-file",
        help="Optional output CSV filename for the target date.",
    )
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        raise SystemExit("No models specified.")

    by_date = parse_output_files(args.input_dir)
    os.makedirs(args.output_dir, exist_ok=True)

    target_date = args.date or date.today().isoformat()
    files = by_date.get(target_date, {})
    missing_models = [m for m in models if m not in files]
    if missing_models:
        raise SystemExit(
            f"Cannot aggregate {target_date}: missing models {', '.join(missing_models)}"
        )

    model_paths = {m: files[m] for m in models}
    out_path, total_rows, review_rows = aggregate_date(
        date=target_date,
        model_paths=model_paths,
        models=models,
        output_dir=args.output_dir,
        output_file=args.output_file,
    )
    print(f"{target_date}: wrote {out_path} (rows={total_rows}, needs_review={review_rows})")


if __name__ == "__main__":
    main()
