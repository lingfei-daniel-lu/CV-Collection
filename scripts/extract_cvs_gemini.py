"""
Mini entrypoint for Gemini-only batch CV extraction.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cv_collection.config import OUTPUT_FOLDER
from scripts.extract_cvs import load_docs, process_model

MODEL_KEY = "gemini"


def main() -> None:
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    docs = load_docs()
    process_model(MODEL_KEY, docs)


if __name__ == "__main__":
    main()
