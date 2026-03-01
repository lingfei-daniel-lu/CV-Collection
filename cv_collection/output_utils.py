#!/usr/bin/env python3
"""
Shared helpers for output file discovery and value normalization.
"""

from __future__ import annotations

import csv
import os
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation


FILENAME_RE = re.compile(r"^output_(?P<model>.+)_(?P<date>\d{4}-\d{2}-\d{2})\.csv$")
SET_SEPARATORS_RE = re.compile(r"[;|\n；]+")
MISSING_TOKENS = {"", "missing", "n/a", "na", "none", "null", "unknown"}


def parse_output_files(input_dir: str) -> dict[str, dict[str, str]]:
    by_date: dict[str, dict[str, str]] = defaultdict(dict)
    for filename in os.listdir(input_dir):
        match = FILENAME_RE.match(filename)
        if not match:
            continue
        model = match.group("model")
        run_date = match.group("date")
        by_date[run_date][model] = os.path.join(input_dir, filename)
    return dict(by_date)


def read_output_rows(path: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    """
    Read one model output CSV using a consistent parser/encoding across tools.
    Returns a mapping keyed by the `file` column plus the original field order.
    """
    rows: dict[str, dict[str, str]] = {}
    fieldnames: list[str] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if "file" not in fieldnames:
            raise ValueError(f"Missing 'file' column in {path}")
        for row in reader:
            if row is None:
                continue
            normalized_row = {k: ("" if v is None else str(v)) for k, v in row.items()}
            key = normalized_row.get("file", "").strip()
            if not key:
                continue
            rows[key] = normalized_row
    return rows, fieldnames


def load_model_output_context(
    model_paths: list[tuple[str, str]],
) -> tuple[
    list[str],
    dict[str, dict[str, dict[str, str]]],
    list[str],
    list[str],
    dict[str, str],
]:
    """
    Load model output CSVs and derive the shared comparison/aggregation context.
    Returns ordered model keys, row mappings, ordered fields, ordered files, and
    inferred field types.
    """
    model_rows: dict[str, dict[str, dict[str, str]]] = {}
    all_fields = set()
    models: list[str] = []

    for model, path in model_paths:
        rows, fieldnames = read_output_rows(path)
        models.append(model)
        model_rows[model] = rows
        all_fields.update(fieldnames)

    all_fields.discard("file")
    ordered_fields = sorted(all_fields)
    all_files = sorted({file_key for rows in model_rows.values() for file_key in rows.keys()})

    field_types = {}
    for field in ordered_fields:
        values = []
        for model in models:
            for row in model_rows[model].values():
                values.append(row.get(field, ""))
        field_types[field] = detect_field_type(values)

    return models, model_rows, ordered_fields, all_files, field_types


def is_missing(value) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if text == "":
        return True
    return text.lower() in MISSING_TOKENS


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(value) -> str:
    if is_missing(value):
        return ""
    return _normalize_whitespace(str(value)).lower()


def _decimal_to_canonical(value: Decimal) -> str:
    if value == value.to_integral():
        return str(int(value))
    normalized = value.normalize()
    text = format(normalized, "f")
    return text.rstrip("0").rstrip(".")


def normalize_number(value) -> str:
    if is_missing(value):
        return ""
    text = str(value).strip()
    try:
        dec = Decimal(text)
    except InvalidOperation:
        return text
    return _decimal_to_canonical(dec)


def normalize_set(value) -> str:
    if is_missing(value):
        return ""
    items = [normalize_text(item) for item in SET_SEPARATORS_RE.split(str(value))]
    items = [item for item in items if item]
    if not items:
        return ""
    return " | ".join(sorted(set(items)))


def is_number_like(value) -> bool:
    if is_missing(value):
        return False
    try:
        Decimal(str(value).strip())
        return True
    except InvalidOperation:
        return False


def detect_field_type(values) -> str:
    non_empty = [v for v in values if not is_missing(v)]
    if not non_empty:
        return "text"
    if all(is_number_like(v) for v in non_empty):
        return "number"
    if any(SET_SEPARATORS_RE.search(str(v)) for v in non_empty):
        return "set"
    return "text"


def normalize_value(field_type: str, value) -> str:
    if field_type == "number":
        return normalize_number(value)
    if field_type == "set":
        return normalize_set(value)
    return normalize_text(value)
