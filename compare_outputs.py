#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation


OUTPUT_DIR = "output/compare"
FILENAME_RE = re.compile(r"^output_(?P<model>.+)_(?P<date>\d{4}-\d{2}-\d{2})\.csv$")


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(value: str) -> str:
    if value is None:
        return ""
    value = _normalize_whitespace(str(value))
    return value.lower()


def _decimal_to_canonical(value: Decimal) -> str:
    if value == value.to_integral():
        return str(int(value))
    # Normalize without scientific notation.
    normalized = value.normalize()
    text = format(normalized, "f")
    return text.rstrip("0").rstrip(".")


def normalize_number(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text == "":
        return ""
    try:
        dec = Decimal(text)
    except InvalidOperation:
        return text
    return _decimal_to_canonical(dec)


SET_SEPARATORS_RE = re.compile(r"[;|\n；]+")
IGNORE_FIELDS = {
    "promotion_evidence",
    "phd_evidence",
}


def normalize_set(value: str) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.strip() == "":
        return ""
    items = [normalize_text(item) for item in SET_SEPARATORS_RE.split(text)]
    items = [item for item in items if item]
    if not items:
        return ""
    return " | ".join(sorted(set(items)))


def is_number_like(value: str) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if text == "":
        return False
    try:
        Decimal(text)
        return True
    except InvalidOperation:
        return False


def detect_field_type(values):
    non_empty = [v for v in values if v not in (None, "")]
    if not non_empty:
        return "text"
    if all(is_number_like(v) for v in non_empty):
        return "number"
    if any(SET_SEPARATORS_RE.search(str(v)) for v in non_empty):
        return "set"
    return "text"


def parse_output_files(output_dir: str):
    by_date = defaultdict(list)
    for filename in os.listdir(output_dir):
        match = FILENAME_RE.match(filename)
        if not match:
            continue
        model = match.group("model")
        date = match.group("date")
        by_date[date].append((model, os.path.join(output_dir, filename)))
    return by_date


def read_csv_rows(path: str):
    rows = {}
    fieldnames = []
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if "file" not in fieldnames:
            raise ValueError(f"Missing 'file' column in {path}")
        for row in reader:
            key = row.get("file", "").strip()
            if not key:
                continue
            rows[key] = row
    return rows, fieldnames


def compare_date(date, model_paths, output_dir):
    model_rows = {}
    all_fields = set()

    for model, path in model_paths:
        rows, fieldnames = read_csv_rows(path)
        model_rows[model] = rows
        all_fields.update(fieldnames)

    all_fields.discard("file")
    for field in IGNORE_FIELDS:
        all_fields.discard(field)
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

    def normalize_value(field, value):
        field_type = field_types.get(field, "text")
        if field_type == "number":
            return normalize_number(value)
        if field_type == "set":
            return normalize_set(value)
        return normalize_text(value)

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
                if raw in (None, ""):
                    missing_any = True
                raw_values[model] = "" if raw is None else str(raw)
                normalized.append(normalize_value(field, raw))
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
        help="Specific date (YYYY-MM-DD) to compare. If omitted, compare all dates with >=2 models.",
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help="Directory containing output_*.csv files.",
    )
    args = parser.parse_args()

    by_date = parse_output_files(args.output_dir)
    if args.date:
        dates = [args.date]
    else:
        dates = sorted([d for d, files in by_date.items() if len(files) >= 2])

    if not dates:
        print("No dates with at least two model outputs found.")
        return

    for date in dates:
        model_paths = by_date.get(date, [])
        if len(model_paths) < 2:
            print(f"Skipping {date}: need at least two models.")
            continue
        diffs_path, summary_path = compare_date(date, model_paths, args.output_dir)
        print(f"{date}: wrote {diffs_path} and {summary_path}")


if __name__ == "__main__":
    main()
