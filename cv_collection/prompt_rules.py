"""
Shared prompt rule blocks (single source of truth) for CV extraction.

These blocks define extraction semantics only. Flow-specific prompt schemas live in
`staged_prompts.py` and `legacy_prompts.py`.
"""

from __future__ import annotations

from cv_collection.journal_taxonomy import format_journal_abbreviation_hints


def join_prompt_blocks(*blocks: str) -> str:
    return "\n\n".join(block.strip() for block in blocks if block and block.strip())


JSON_ONLY_GUARDRAILS = """\
ONLY RETURN JSON. NO MARKDOWN. NO COMMENTARY.
Do NOT wrap JSON in backticks.
"""


CONSERVATIVE_EXTRACTION_RULES = """\
- Be conservative. Only extract explicitly stated facts.
- If a field cannot be determined, return null (or false where the schema requires false).
- Do NOT infer or guess.
"""


TENURE_PROMOTION_RULES = """\
TENURE / PROMOTION RULES
- Promotion refers to the FIRST tenure-track promotion to Associate Professor or Reader.
- Treat Reader as equivalent to Associate Professor for this task.
- Source priority: use sections titled "Academic Appointments", "Employment", or "Positions"
  (or close variants) first. If none exist, then use other sections as fallback.
- Default rule: the first Assistant Professor -> Associate Professor/Reader move counts as the
  tenure event unless the line explicitly says "without tenure" / "untenured" / "non-tenure".
- If an Associate Professor/Reader appointment is explicitly "without tenure", do NOT use that
  year as the tenure event. Look for the next line/year that explicitly grants tenure.
- Treat wording like "promoted to Associate Professor", "awarded tenure", "continuous
  appointment", and "tenure-track Associate Professor" as tenure-relevant evidence.
- If an explicit tenure-granting year is given and differs from the Associate/Reader start year,
  use the explicit tenure year.
- Multiple institutions: if the person leaves Institution A as Assistant and starts at
  Institution B directly as Associate Professor/Reader (tenure-track or with tenure implied),
  use the FIRST year they appear as Associate/Reader at Institution B. If they later receive
  tenure after an Associate/Reader-without-tenure start, use the first year explicitly showing
  tenure.
- Mid-career hires: if the CV begins at Associate Professor/Reader (or tenured Associate) with
  no Assistant history shown, use the first listed year and institution of that Associate/Reader
  appointment unless it is marked "without tenure"; in that case, use the first later
  tenure-granting year.
- Partial/ambiguous dates: if only ranges are given (e.g., 2015-2020 Assistant; 2020-present
  Associate), use the start year of the Associate/Reader range, unless a different explicit
  tenure year is stated.
- Explicit exclusions for tenure decisions unless tenure is explicitly stated alongside the
  professor title: visiting, adjunct, clinical, of practice, professor of practice, research,
  teaching, lecturer, instructor, emeritus, honorary, affiliate, non-tenure, without tenure.
- Ignore purely administrative titles (e.g., Associate Director) unless paired with Associate
  Professor or Reader.
"""


PHD_AND_YEARS_POST_PHD_RULES = """\
PHD / YEARS-POST-PHD RULES
- Only accept a PhD year that is explicitly completed / received / earned.
- Treat "expected", "in progress", or incomplete degrees as missing.
- If multiple PhDs are listed, prefer Economics; otherwise use the earliest completed PhD year.
- years_post_phd = promotion_year - PhD completion year.
- If either year is missing, years_post_phd must be null.
- If promotion_year < PhD year, years_post_phd must be null.
"""


INSTITUTION_NAMING_RULES = """\
INSTITUTION NAMING RULES
- Output the full university name (no acronyms).
- If an acronym appears in parentheses, return the full name outside parentheses.
"""


PUBLICATION_COUNTING_RULES = """\
PUBLICATION COUNTING RULES
- Count only PUBLISHED peer-reviewed journal articles in the target journals.
- Do NOT count accepted, forthcoming, revise-and-resubmit, submitted, under review, conference
  proceedings, book chapters, books, reports, working papers, or referee/editorial service.
- Deduplicate the same paper if it appears multiple times in the CV (e.g., in "Publications" and
  "Selected Publications").
- If multiple different papers were published in the same journal in the same year, they count as
  multiple articles (the same year may appear more than once in staged year lists).
"""


PUBLICATION_MATCHING_RULES = (
    "PUBLICATION MATCHING RULES\n"
    "- Match common abbreviations and variants:\n"
    f"{format_journal_abbreviation_hints()}\n"
    "- Match italicized / abbreviated journal names where the mapping is clear.\n"
    "- Extract the publication year from each matched published article entry.\n"
)
