#!/usr/bin/env python3
import argparse
import csv
import json
import os
import sys
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cv_collection.config import COMPARE_OUTPUT_FOLDER, OUTPUT_FOLDER
from cv_collection.output_utils import (
    detect_field_type,
    is_missing,
    normalize_value,
    parse_output_files,
    read_output_rows,
)

def compare_date(date, model_paths, output_dir):
    model_rows = {}
    all_fields = set()

    for model, path in model_paths:
        rows, fieldnames = read_output_rows(path)
        model_rows[model] = rows
        all_fields.update(fieldnames)

    all_fields.discard("file")
    all_files = sorted({f for rows in model_rows.values() for f in rows.keys()})
    models = sorted(model_rows.keys())

    # Determine field types using all values.
    field_types = {}
    for field in sorted(all_fields):
        values = []
        for model in models:
            for row in model_rows[model].values():
                values.append(row.get(field, ""))
        field_types[field] = detect_field_type(values)

    diffs = []
    summary = {field: {"diff": 0, "missing": 0} for field in all_fields}
    total_files = len(all_files)

    for file_key in all_files:
        diff_fields = []
        model_values = {}
        for field in sorted(all_fields):
            normalized = []
            raw_values = {}
            missing_any = False
            for model in models:
                row = model_rows[model].get(file_key)
                raw = "" if row is None else row.get(field, "")
                if is_missing(raw):
                    missing_any = True
                raw_values[model] = "" if raw is None else str(raw)
                normalized.append(normalize_value(field_types.get(field, "text"), raw))
            if missing_any:
                summary[field]["missing"] += 1
            if len(set(normalized)) > 1:
                summary[field]["diff"] += 1
                diff_fields.append(field)
                model_values[field] = raw_values
        if diff_fields:
            row = {
                "file": file_key,
                "diff_fields": "; ".join(diff_fields),
            }
            for model in models:
                model_field_values = {
                    field: model_values[field][model] for field in diff_fields
                }
                row[f"{model}_values"] = json.dumps(
                    model_field_values, ensure_ascii=True, sort_keys=True
                )
            diffs.append(row)

    diffs_path = os.path.join(output_dir, f"compare_{date}_diffs.csv")
    summary_path = os.path.join(output_dir, f"compare_{date}_summary.csv")

    if diffs:
        diff_fields = ["file", "diff_fields"] + [f"{m}_values" for m in models]
        with open(diffs_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=diff_fields)
            writer.writeheader()
            for row in diffs:
                writer.writerow(row)
    else:
        with open(diffs_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["file", "diff_fields"] + [f"{m}_values" for m in models])

    with open(summary_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "field",
                "field_type",
                "diff_count",
                "missing_count",
                "total_files",
                "diff_rate",
                "missing_rate",
            ],
        )
        writer.writeheader()
        for field in sorted(all_fields):
            diff_count = summary[field]["diff"]
            missing_count = summary[field]["missing"]
            diff_rate = diff_count / total_files if total_files else 0
            missing_rate = missing_count / total_files if total_files else 0
            writer.writerow(
                {
                    "field": field,
                    "field_type": field_types.get(field, "text"),
                    "diff_count": diff_count,
                    "missing_count": missing_count,
                    "total_files": total_files,
                    "diff_rate": f"{diff_rate:.4f}",
                    "missing_rate": f"{missing_rate:.4f}",
                }
            )

    return diffs_path, summary_path


def main():
    parser = argparse.ArgumentParser(
        description="Compare model outputs by date and flag differing CV rows."
    )
    parser.add_argument(
        "--date",
        help="Specific date (YYYY-MM-DD) to compare. If omitted, compare today's date only.",
    )
    parser.add_argument(
        "--input-dir",
        default=str(OUTPUT_FOLDER),
        help="Directory containing output_*.csv files.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(COMPARE_OUTPUT_FOLDER),
        help="Directory to write compare_*.csv files.",
    )
    args = parser.parse_args()

    by_date = parse_output_files(args.input_dir)
    os.makedirs(args.output_dir, exist_ok=True)
    target_date = args.date or date.today().isoformat()

    model_paths = sorted(by_date.get(target_date, {}).items())
    if len(model_paths) < 2:
        print(f"Skipping {target_date}: need at least two model outputs.")
        return

    diffs_path, summary_path = compare_date(target_date, model_paths, args.output_dir)
    print(f"{target_date}: wrote {diffs_path} and {summary_path}")


if __name__ == "__main__":
    main()
