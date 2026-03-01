"""
Helpers for safely parsing LLM JSON responses.
"""

from __future__ import annotations

import json
from typing import Any


def safe_json_load(raw: str, *, label: str) -> dict[str, Any] | None:
    if not raw:
        print(f"⚠️  Empty response for {label}")
        return None
    txt = raw.strip()
    if txt.startswith("```"):
        parts = txt.split("```", 2)
        if len(parts) >= 2:
            txt = parts[1]
            if txt.lower().startswith("json"):
                txt = txt[4:]
    start, end = txt.find("{"), txt.rfind("}")
    if start == -1 or end == -1:
        print(f"⚠️  No JSON braces in response for {label}")
        return None
    try:
        return json.loads(txt[start : end + 1])
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON decode failed for {label}: {e}")
        return None
