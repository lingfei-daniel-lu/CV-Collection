"""
Prompt builders for the staged (multi-step) CV extraction pipeline.
"""

from __future__ import annotations

import json
from typing import Any

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


def build_metadata_prompt() -> str:
    return join_prompt_blocks(
        JSON_ONLY_GUARDRAILS,
        """\
TASK
-----
Extract the following metadata from the academic CV text below.
For EVERY field also return a confidence score (0.0 = pure guess, 1.0 = unambiguous).

Return this exact JSON structure:
{
  "name": "full name or null",
  "name_confidence": 0.0,
  "promotion_year": null,
  "promotion_year_confidence": 0.0,
  "promotion_university": null,
  "promotion_university_confidence": 0.0,
  "years_post_phd": null,
  "years_post_phd_confidence": 0.0
}
""",
        """\
FIELD DEFINITIONS
- name: the CV owner's full name (usually near the top of the document)
- promotion_year: the tenure-track promotion year to Associate Professor or Reader
- promotion_university: the institution where that promotion occurred
- years_post_phd: integer years between PhD completion and that promotion
""",
        CONSERVATIVE_EXTRACTION_RULES,
        TENURE_PROMOTION_RULES,
        PHD_AND_YEARS_POST_PHD_RULES,
        INSTITUTION_NAMING_RULES,
    )


def build_publication_prompt() -> str:
    return join_prompt_blocks(
        JSON_ONLY_GUARDRAILS,
        """\
TASK
-----
Below are individual publication entries extracted from an academic CV.
For each target journal listed below, identify every PUBLISHED article and return the
PUBLICATION YEAR of each one.
""",
        "TARGET JOURNALS:\n" + format_journal_bullets(),
        PUBLICATION_COUNTING_RULES,
        PUBLICATION_MATCHING_RULES,
        """\
Return JSON:
{
  "journals": {
    "QUARTERLY JOURNAL OF ECONOMICS": [2005, 2012] or false,
    "AMERICAN ECONOMIC REVIEW": [2018] or false,
    ... (include ALL journals from the list)
  }
}

For each journal:
- If there are matching published articles, return a LIST of integer years (one year per article,
  in chronological order).
- If there are NO matching articles, return false.
- If a year cannot be determined for a specific matched article, use null in the list.
""",
    )


def build_targeted_retry_prompt(fields: list[str], hints: dict[str, str] | None = None) -> str:
    requested = [field for field in fields if field]
    if not requested:
        requested = ["name"]
    requested_set = set(requested)
    hint_map = hints or {}
    hint_block = "\n".join(
        f"- {field}: {(hint_map.get(field) or '').strip() or 'No extra field hint provided.'}"
        for field in requested
    )
    schema_lines = []
    for field in requested:
        schema_lines.append(f'  "{field}": <value or null>,')
        schema_lines.append(f'  "{field}_confidence": <float 0.0-1.0>,')
    schema_lines[-1] = schema_lines[-1].rstrip(",")
    fields_block = "\n".join(f"- {field}" for field in requested)
    needs_tenure_rules = bool({"promotion_year", "promotion_university"} & requested_set)
    needs_phd_rules = "years_post_phd" in requested_set
    needs_institution_rules = "promotion_university" in requested_set
    return join_prompt_blocks(
        JSON_ONLY_GUARDRAILS,
        f"""\
TASK
-----
Re-examine this CV very carefully and extract ONLY the following metadata fields:
{fields_block}
""",
        "FIELD HINT\n" + hint_block,
        CONSERVATIVE_EXTRACTION_RULES,
        TENURE_PROMOTION_RULES if needs_tenure_rules else "",
        PHD_AND_YEARS_POST_PHD_RULES if needs_phd_rules else "",
        INSTITUTION_NAMING_RULES if needs_institution_rules else "",
        "Return ONLY the requested fields and their confidence scores.",
        """\
Return JSON:
{
"""
        + "\n".join(schema_lines)
        + """
}
""",
    )


def build_verification_prompt(extracted_data: dict[str, Any]) -> str:
    extracted_json = json.dumps(extracted_data, indent=2, ensure_ascii=False)
    return join_prompt_blocks(
        JSON_ONLY_GUARDRAILS,
        """\
TASK
-----
Verify and correct the extracted data below against the original CV.
Keep correct fields unchanged. Fix wrong ones. Set unknowable fields to null.
""",
        "EXTRACTED DATA:\n" + extracted_json,
        CONSERVATIVE_EXTRACTION_RULES,
        TENURE_PROMOTION_RULES,
        PHD_AND_YEARS_POST_PHD_RULES,
        INSTITUTION_NAMING_RULES,
        "TARGET JOURNALS:\n" + format_journal_bullets(),
        PUBLICATION_COUNTING_RULES,
        PUBLICATION_MATCHING_RULES,
        """\
CHECK EACH FIELD
1. Is "name" correct?
2. Is "promotion_year" the actual tenure-track promotion year to Associate Professor or Reader?
3. Is "promotion_university" correct?
4. Is "years_post_phd" correctly calculated (promotion_year minus PhD year)?
5. For each target journal, verify:
   a) Every listed article actually appears in the CV
   b) The publication years are correct
   c) No published target-journal articles were missed
   d) Only published articles are counted

Return the CORRECTED JSON with the EXACT same structure as EXTRACTED DATA above.
For journals, return a list of integer years (one per article) or false.
""",
    )
