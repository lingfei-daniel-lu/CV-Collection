"""
Prompt builder for the legacy single-pass extraction flow (kept as backup).
"""

from __future__ import annotations

from cv_collection.journal_taxonomy import format_journal_bullets
from cv_collection.prompt_rules import (
    CONSERVATIVE_EXTRACTION_RULES,
    INSTITUTION_NAMING_RULES,
    JSON_ONLY_GUARDRAILS,
    PHD_AND_YEARS_POST_PHD_RULES,
    PUBLICATION_COUNTING_RULES,
    PUBLICATION_MATCHING_RULES,
    TENURE_PROMOTION_RULES,
    join_prompt_blocks,
)


def build_single_pass_prompt() -> str:
    return join_prompt_blocks(
        JSON_ONLY_GUARDRAILS,
        """\
You are a careful research assistant. Read the full text of an economics faculty CV (from a Word
document) and extract the first tenure-track promotion and target journal publication counts.

Return ONE JSON object with:
- "name": full name of the faculty member
- "promotion_year": four-digit year of the first tenure-track promotion to Associate Professor or
  Reader; if the CV starts at Associate/Reader with tenure implied, use the first qualifying year;
  if tenure is later explicit, use the tenure-granting year
- "promotion_university": university where that tenure-track promotion occurred
- "years_post_phd": promotion_year minus PhD completion year; null if missing or invalid
- "journals": object with EVERY target journal key below and integer counts (0, 1, 2, ...)
""",
        CONSERVATIVE_EXTRACTION_RULES,
        TENURE_PROMOTION_RULES,
        PHD_AND_YEARS_POST_PHD_RULES,
        INSTITUTION_NAMING_RULES,
        PUBLICATION_COUNTING_RULES,
        PUBLICATION_MATCHING_RULES,
        "TARGET JOURNALS:\n" + format_journal_bullets(),
        """\
JOURNAL OUTPUT RULES
- Include EVERY journal key from the target list.
- The value for each journal must be an integer count (0, 1, 2, ...).
- If a journal is absent, return 0.
""",
    )
