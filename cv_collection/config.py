"""
Shared project configuration constants.
"""

from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_ROOT_FOLDER = BASE_DIR / "input"
OUTPUT_FOLDER = BASE_DIR / "output"
COMPARE_OUTPUT_FOLDER = OUTPUT_FOLDER / "compare"
AGGREGATE_OUTPUT_FOLDER = OUTPUT_FOLDER / "aggregate"

# Canonical model order used across scripts.
DEFAULT_MODEL_KEYS = ("deepseek", "kimi", "gpt", "gemini", "claude")
