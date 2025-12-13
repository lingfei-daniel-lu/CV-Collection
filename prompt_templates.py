"""
Prompt templates and journal lists for CV parsing.
"""

from __future__ import annotations

JOURNALS = [
    "QUARTERLY JOURNAL OF ECONOMICS",
    "AMERICAN ECONOMIC REVIEW",
    "ECONOMETRICA",
    "REVIEW OF ECONOMIC STUDIES",
    "JOURNAL OF POLITICAL ECONOMY",
    "AMERICAN ECONOMIC JOURNAL-MACROECONOMICS",
    "AMERICAN ECONOMIC JOURNAL-APPLIED ECONOMICS",
    "JOURNAL OF THE EUROPEAN ECONOMIC ASSOCIATION",
    "AMERICAN ECONOMIC JOURNAL-ECONOMIC POLICY",
    "THEORETICAL ECONOMICS",
    "AMERICAN ECONOMIC JOURNAL-MICROECONOMICS",
    "QUANTITATIVE ECONOMICS",
    "REVIEW OF ECONOMICS AND STATISTICS",
    "ECONOMIC JOURNAL",
    "INTERNATIONAL ECONOMIC REVIEW",
    "JOURNAL OF ECONOMIC THEORY",
    "JOURNAL OF LABOR ECONOMICS",
    "JOURNAL OF MONETARY ECONOMICS",
    "RAND JOURNAL OF ECONOMICS",
    "JOURNAL OF INTERNATIONAL ECONOMICS",
    "JOURNAL OF PUBLIC ECONOMICS",
    "JOURNAL OF ECONOMETRICS",
    "JOURNAL OF DEVELOPMENT ECONOMICS",
]

journal_schema_lines = ",\n      ".join(f'"{j}": <int | false>' for j in JOURNALS)

PROMPT_TEMPLATE = f"""
ONLY RETURN JSON. NO MARKDOWN. NO COMMENTARY.

You are a careful research assistant. Read the full text of an economics faculty CV (from a Word document) and extract the first tenure-track promotion and journal publication counts.

Return ONE JSON object with:
• "name": full name of the faculty member
• "promotion_year": four-digit year of the FIRST promotion from Assistant Professor to (tenure-track) Associate Professor. If the CV starts at Associate/tenured, use the first year they are listed as Associate/tenured. Ignore visiting/adjunct titles and roles explicitly labeled "without tenure".
• "promotion_university": university where that promotion/tenure occurred (the institution named on the appointment line for that year), not later moves.
• "years_post_phd": promotion_year minus PhD completion year; null if either year is missing.
• "journals": object with EVERY journal key below and integer counts (0, 1, 2, ...). Never use booleans or null. Count peer-reviewed journal articles that are published/accepted/forthcoming. Do NOT count "under review", "revise and resubmit", "submitted", conference proceedings, book chapters, books, reports, or referee service. Deduplicate if the same paper appears twice. If a journal is absent, return 0.

Tenure/promotion identification guidance:
- Default rule: the first Assistant Professor -> Associate Professor promotion counts as tenure unless the line explicitly says "without tenure"/"untenured". If "without tenure" is present, treat that move as non-tenure; then look for the next Associate/tenure line with tenure.
- Fuzzy titles: treat wording like "promoted to Associate Professor", "awarded tenure", "continuous appointment", "tenure-track Associate Professor" as tenure events. Ignore purely administrative titles (e.g., "Associate Director") unless paired with Associate Professor.
- Multiple institutions: if someone leaves Institution A as Assistant and starts at Institution B directly as Associate (tenure-track/with tenure implied), use the FIRST year they appear as Associate/tenured at Institution B. If they later get tenure at Institution B after an Associate-without-tenure start, use the first year explicitly indicating tenure.
- Mid-career hires: if the CV begins at Associate/tenured with no Assistant history, use the first listed year and institution of that Associate/tenured appointment (unless marked "without tenure"; then look for the first tenure-granting year).
- Partial/ambiguous dates: if only a range is given (e.g., 2015-2020 Assistant; 2020- present Associate), use the start year of the Associate range.
- Ignore visiting/adjunct/clinical/emeritus/honorary titles for tenure decisions.

Do NOT wrap JSON in backticks.

JOURNALS:
{chr(10).join('* ' + j for j in JOURNALS)}
"""


def get_prompt() -> str:
    """Return the default prompt template."""
    return PROMPT_TEMPLATE.strip()
