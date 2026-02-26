"""
Backward-compatible prompt exports.

New code should use:
- `cv_collection.journal_taxonomy` for journal lists
- `cv_collection.legacy_prompts` for the single-pass backup prompt
- `cv_collection.staged_prompts` for the staged extraction prompts
"""

from __future__ import annotations

from cv_collection.journal_taxonomy import JOURNALS
from cv_collection.legacy_prompts import build_single_pass_prompt

PROMPT_TEMPLATE = build_single_pass_prompt()


def get_prompt() -> str:
    """Return the legacy single-pass prompt template (compatibility wrapper)."""
    return PROMPT_TEMPLATE.strip()
