"""
Prompt builders for the staged (multi-step) CV extraction pipeline.
"""

from __future__ import annotations

import json
from typing import Any

from cv_collection.journal_taxonomy import format_journal_bullets
from cv_collection.prompt_rules import (
    CONSERVATIVE_EXTRACTION_RULES,
    FULL_PROFESSOR_PROMOTION_RULES,
    INSTITUTION_NAMING_RULES,
    JSON_ONLY_GUARDRAILS,
    PHD_AND_YEARS_POST_PHD_RULES,
    PUBLICATION_COUNTING_RULES,
    PUBLICATION_MATCHING_RULES,
    RESEARCH_FIELDS_RULES,
    TENURE_PROMOTION_RULES,
    join_prompt_blocks,
)


BASE_METADATA_FIELDS = [
    "name",
    "promotion_year",
    "promotion_university",
    "years_post_phd",
]
FULL_ONLY_METADATA_FIELDS = [
    "full_promotion_year",
    "full_promotion_university",
    "years_post_phd_full",
]
BASE_FIELD_DEFINITIONS = [
    "- name: the CV owner's full name (usually near the top of the document)",
    "- promotion_year: the tenure-track promotion year to Associate Professor or Reader",
    "- promotion_university: the institution where that tenure-track promotion occurred",
    "- years_post_phd: integer years between PhD completion and promotion_year",
]
FULL_FIELD_DEFINITIONS = [
    "- full_promotion_year: first promotion/appointment year to Full Professor",
    "- full_promotion_university: institution where full_promotion_year occurred",
    "- years_post_phd_full: integer years between PhD completion and full_promotion_year",
]
VERIFICATION_CHECK_LINES = [
    '- "name" is correct',
    '- "promotion_year" is the tenure-track Associate/Reader promotion year',
    '- "promotion_university" is correct for promotion_year',
    '- "years_post_phd" = promotion_year minus PhD year',
]
FULL_VERIFICATION_CHECK_LINES = [
    '- "full_promotion_year" is the first explicit year at Full Professor rank',
    '- "full_promotion_university" matches the Full Professor appointment institution',
    '- "years_post_phd_full" = full_promotion_year minus PhD year',
]
TARGETED_RETRY_FIELD_HINTS = {
    "name": "The full name of the CV owner. Usually at the very top of the document.",
    "research_fields": (
        "The person's PRIMARY research fields/interests as explicitly listed in a "
        "Research Interests/Fields section. If Primary vs Secondary is shown, return "
        "ONLY Primary fields. If no such section exists, return an empty string."
    ),
    "promotion_year": (
        "The calendar year this person was promoted to Associate Professor or Reader. "
        "Look in the employment / positions / appointments section for dates next to "
        "'Associate Professor' or 'Reader'."
    ),
    "full_promotion_year": (
        "The first calendar year this person appears as Full Professor / Professor in "
        "employment or appointments sections. Do not confuse with Associate Professor."
    ),
    "full_promotion_university": (
        "The university or institution where the Full Professor appointment occurred. "
        "This may differ from the tenure-promotion university."
    ),
    "promotion_university": (
        "The university or institution where the promotion to Associate Professor "
        "or Reader occurred. Usually listed alongside the title in the employment section."
    ),
    "years_post_phd": (
        "Integer years between PhD completion and promotion to Associate Professor / Reader. "
        "PhD year is typically in the Education section; promotion year in Employment. "
        "Calculate: promotion_year minus phd_year."
    ),
    "years_post_phd_full": (
        "Integer years between PhD completion and first Full Professor appointment. "
        "Calculate: full_promotion_year minus phd_year. If either year is unknown, return null."
    ),
}


def normalize_rank(rank: str | None) -> str:
    return "full" if (rank or "").strip().lower() == "full" else "associate"


def metadata_fields_for_rank(rank: str | None) -> list[str]:
    resolved = normalize_rank(rank)
    fields = list(BASE_METADATA_FIELDS)
    if resolved == "full":
        fields.extend(FULL_ONLY_METADATA_FIELDS)
    return fields


def _schema_with_confidence(fields: list[str]) -> str:
    lines: list[str] = ["{"]
    for field in fields:
        if field == "name":
            lines.append('  "name": "full name or null",')
        elif field == "research_fields":
            lines.append('  "research_fields": "semicolon-separated fields or empty string",')
        else:
            lines.append(f'  "{field}": null,')
        lines.append(f'  "{field}_confidence": 0.0,')
    if len(lines) > 1:
        lines[-1] = lines[-1].rstrip(",")
    lines.append("}")
    return "\n".join(lines)


def _field_definitions(rank: str | None) -> list[str]:
    definitions = list(BASE_FIELD_DEFINITIONS)
    if normalize_rank(rank) == "full":
        definitions.extend(FULL_FIELD_DEFINITIONS)
    return definitions


def _requested_metadata_fields(fields: list[str], rank: str | None) -> list[str]:
    requested = [field for field in fields if field in set(metadata_fields_for_rank(rank))]
    return requested or ["name"]


def _metadata_rule_blocks(fields: list[str], rank: str | None) -> list[str]:
    requested = set(fields)
    blocks = [CONSERVATIVE_EXTRACTION_RULES]
    if "research_fields" in requested:
        blocks.append(RESEARCH_FIELDS_RULES)
    if {"promotion_year", "promotion_university"} & requested:
        blocks.append(TENURE_PROMOTION_RULES)
    if normalize_rank(rank) == "full" and set(FULL_ONLY_METADATA_FIELDS) & requested:
        blocks.append(FULL_PROFESSOR_PROMOTION_RULES)
    if {"years_post_phd", "years_post_phd_full"} & requested:
        blocks.append(PHD_AND_YEARS_POST_PHD_RULES)
    if {"promotion_university", "full_promotion_university"} & requested:
        blocks.append(INSTITUTION_NAMING_RULES)
    return blocks


def _verification_check_lines(rank: str | None) -> list[str]:
    lines = list(VERIFICATION_CHECK_LINES)
    if normalize_rank(rank) == "full":
        lines.extend(FULL_VERIFICATION_CHECK_LINES)
    return lines


def build_metadata_prompt(rank: str | None = None) -> str:
    resolved_rank = normalize_rank(rank)
    fields = metadata_fields_for_rank(resolved_rank)
    return join_prompt_blocks(
        JSON_ONLY_GUARDRAILS,
        """\
TASK
-----
Extract the following metadata from the academic CV text below.
For EVERY field also return a confidence score (0.0 = pure guess, 1.0 = unambiguous).

Return this exact JSON structure:
"""
        + _schema_with_confidence(fields),
        "FIELD DEFINITIONS\n" + "\n".join(_field_definitions(resolved_rank)),
        *_metadata_rule_blocks(fields, resolved_rank),
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


def build_targeted_retry_prompt(
    fields: list[str],
    *,
    rank: str | None = None,
) -> str:
    resolved_rank = normalize_rank(rank)
    requested = _requested_metadata_fields([field for field in fields if field], resolved_rank)
    hint_block = "\n".join(
        f"- {field}: "
        f"{(TARGETED_RETRY_FIELD_HINTS.get(field) or '').strip() or 'No extra field hint provided.'}"
        for field in requested
    )
    schema_lines = []
    for field in requested:
        schema_lines.append(f'  "{field}": <value or null>,')
        schema_lines.append(f'  "{field}_confidence": <float 0.0-1.0>,')
    schema_lines[-1] = schema_lines[-1].rstrip(",")
    fields_block = "\n".join(f"- {field}" for field in requested)
    return join_prompt_blocks(
        JSON_ONLY_GUARDRAILS,
        f"""\
TASK
-----
Re-examine this CV very carefully and extract ONLY the following metadata fields:
{fields_block}
""",
        "FIELD HINT\n" + hint_block,
        *_metadata_rule_blocks(requested, resolved_rank),
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


def build_verification_prompt(
    extracted_data: dict[str, Any], rank: str | None = None
) -> str:
    resolved_rank = normalize_rank(rank)
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
        *_metadata_rule_blocks(metadata_fields_for_rank(resolved_rank), resolved_rank),
        "TARGET JOURNALS:\n" + format_journal_bullets(),
        PUBLICATION_COUNTING_RULES,
        PUBLICATION_MATCHING_RULES,
        """\
CHECK EACH FIELD
"""
        + "\n".join(_verification_check_lines(resolved_rank))
        + """
For each target journal, verify:
   a) Every listed article actually appears in the CV
   b) The publication years are correct
   c) No published target-journal articles were missed
   d) Only published articles are counted

Return the CORRECTED JSON with the EXACT same structure as EXTRACTED DATA above.
For journals, return a list of integer years (one per article) or false.
""",
    )
