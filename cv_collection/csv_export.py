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
        "rank",
        "name",
        "research_fields",
        "promotion_year",
        "full_promotion_year",
        "full_promotion_university",
        "promotion_university",
        "years_post_phd",
        "years_post_phd_full",
    ]
    journal_cols = list(journals)
    if not df.empty:
        df = df[first_cols + journal_cols]
    write_header = not out_csv.exists()
    df.to_csv(out_csv, index=False, mode="a", header=write_header)
