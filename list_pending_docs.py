#!/usr/bin/env python3
"""
List legacy .doc files that still need manual conversion to .docx.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def list_doc_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() == ".doc" and not p.name.startswith(".")
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List .doc files under a CV root folder."
    )
    parser.add_argument(
        "--root",
        default="CV_word",
        help="Root folder to scan (default: CV_word).",
    )
    parser.add_argument(
        "--absolute",
        action="store_true",
        help="Print absolute paths instead of paths relative to root.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Root folder not found: {root}")

    pending = list_doc_files(root)
    if not pending:
        print(f"No .doc files found under {root}")
        return

    print(f"Found {len(pending)} .doc file(s) under {root}:")
    for path in pending:
        print(path if args.absolute else path.relative_to(root))


if __name__ == "__main__":
    main()
