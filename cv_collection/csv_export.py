"""
Helpers for writing extraction rows to CSV.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


def flush_rows_to_csv(rows: list[dict], out_csv: Path, journals: Iterable[str]) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    first_cols = [
        "file",
        "name",
        "promotion_year",
        "promotion_university",
        "years_post_phd",
    ]
    journal_cols = list(journals)
    if not df.empty:
        df = df[first_cols + journal_cols]
    write_header = not out_csv.exists()
    df.to_csv(out_csv, index=False, mode="a", header=write_header)
