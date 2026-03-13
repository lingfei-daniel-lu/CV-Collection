"""
Canonical economics research-field labels and matching helpers.
"""

from __future__ import annotations

import re


RESEARCH_FIELD_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("Applied Econometrics", (r"applied econometrics",)),
    ("Econometrics", (r"econometrics", r"theoretical econometrics")),
    ("Applied Microeconomics", (r"(?:applied|empirical)\s+micro(?:economics)?",)),
    ("Applied Macroeconomics", (r"(?:applied|empirical)\s+macro(?:economics)?",)),
    ("Microeconomic Theory", (r"micro(?:economic)? theory",)),
    ("Macroeconomic Theory", (r"macro(?:economic)? theory",)),
    ("Microeconomics", (r"microeconomics",)),
    ("Macroeconomics", (r"macroeconomics",)),
    ("Development Economics", (r"development economics", r"economic development")),
    ("International Economics", (r"international economics",)),
    ("International Trade", (r"international trade",)),
    ("International Finance", (r"international finance",)),
    ("Labor Economics", (r"labou?r economics",)),
    ("Public Economics", (r"public economics", r"public finance")),
    ("Industrial Organization", (r"industrial organi[sz]ation",)),
    ("Organizational Economics", (r"organizational economics",)),
    ("Political Economy", (r"political economy",)),
    ("Behavioral Economics", (r"behaviou?ral economics",)),
    ("Experimental Economics", (r"experimental economics",)),
    ("Health Economics", (r"health economics",)),
    ("Education Economics", (r"education economics", r"economics of education")),
    ("Urban Economics", (r"urban economics",)),
    ("Regional Economics", (r"regional economics",)),
    ("Environmental Economics", (r"environmental economics",)),
    ("Resource Economics", (r"resource economics", r"natural resource economics")),
    ("Agricultural Economics", (r"agricultural economics",)),
    ("Economic History", (r"economic history", r"cliometrics")),
    ("Law and Economics", (r"law and economics",)),
    ("Financial Economics", (r"financial economics",)),
    ("Behavioral Finance", (r"behaviou?ral finance",)),
    ("Experimental Finance", (r"experimental finance",)),
    ("Household Finance", (r"household finance",)),
    ("Game Theory", (r"game theory",)),
    ("Mechanism Design", (r"mechanism design", r"market design", r"auction theory")),
    ("Information Economics", (r"information economics", r"economics of information")),
    ("Contract Theory", (r"contract theory", r"incomplete contracts?")),
    ("Decision Theory", (r"decision theory",)),
    ("Monetary Economics", (r"monetary economics",)),
    ("Demography", (r"demography",)),
    ("Family Economics", (r"family economics",)),
    ("Real Estate Economics", (r"real estate economics",)),
]

RESEARCH_FIELD_SPECIAL_CASES = {
    "game theory",
    "mechanism design",
    "decision theory",
}

RESEARCH_FIELD_FALLBACK_KEYWORDS = (
    "economics",
    "econometric",
    "econometrics",
    "economic history",
    "finance",
    "theory",
    "organization",
    "organisation",
    "trade",
)

RESEARCH_FIELD_NOISE_FRAGMENTS = set(
    "association award board college committee conference department editor employment faculty "
    "fellow held honor honour journal member office offices position positions present "
    "president professor program school service student teaching university".split()
)


def _compile_alias_pattern(*aliases: str) -> re.Pattern[str]:
    joined = "|".join(aliases)
    return re.compile(rf"(?i)\b(?:{joined})\b")


RESEARCH_FIELD_PATTERN_SPECS: list[tuple[str, re.Pattern[str]]] = [
    (canonical, _compile_alias_pattern(*aliases))
    for canonical, aliases in RESEARCH_FIELD_ALIASES
]


def normalize_research_fields(value: object) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""

    fields: list[str] = []
    for candidate in _split_research_field_candidates(raw):
        matches = _extract_known_research_fields(candidate)
        if matches:
            for field in matches:
                if field not in fields:
                    fields.append(field)
            continue
        if _is_plausible_research_field(candidate):
            formatted = _format_research_field(candidate)
            if formatted and formatted not in fields:
                fields.append(formatted)
    return "; ".join(fields)


def _split_research_field_candidates(value: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", value.replace("|", ";")).strip()
    coarse_parts = re.split(r"\s*[;\n]\s*", cleaned)
    candidates: list[str] = []
    for part in coarse_parts:
        chunk = part.strip(" ,;:.")
        if not chunk:
            continue
        if chunk.count(",") >= 1 and len(chunk) <= 120 and ":" not in chunk and "." not in chunk:
            pieces = [piece.strip(" ,;:.") for piece in re.split(r"\s*,\s*", chunk)]
            candidates.extend(piece for piece in pieces if piece)
            continue
        candidates.append(chunk)
    return candidates


def _extract_known_research_fields(candidate: str) -> list[str]:
    matches: list[tuple[int, int, str]] = []
    for canonical, pattern in RESEARCH_FIELD_PATTERN_SPECS:
        match = pattern.search(candidate)
        if match:
            matches.append((match.start(), match.end(), canonical))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    ordered: list[str] = []
    covered_spans: list[tuple[int, int]] = []
    for start, end, canonical in matches:
        if any(start < span_end and end > span_start for span_start, span_end in covered_spans):
            continue
        if canonical not in ordered:
            ordered.append(canonical)
            covered_spans.append((start, end))
    return ordered


def _is_plausible_research_field(candidate: str) -> bool:
    cleaned = candidate.strip(" ,;:.")
    if not cleaned or len(cleaned) > 80:
        return False
    lowered = cleaned.lower()
    if re.search(r"\d", lowered) or "http" in lowered:
        return False
    if ":" in cleaned or '"' in cleaned:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z&/-]*", cleaned)
    if not words or len(words) > 6:
        return False
    if any(fragment in lowered for fragment in RESEARCH_FIELD_NOISE_FRAGMENTS):
        return False
    if lowered in RESEARCH_FIELD_SPECIAL_CASES:
        return True
    return any(keyword in lowered for keyword in RESEARCH_FIELD_FALLBACK_KEYWORDS)


def _format_research_field(candidate: str) -> str:
    small_words = {"and", "of", "the", "in", "for", "to"}
    parts = re.split(r"(\s+)", candidate.strip())
    formatted: list[str] = []
    for index, part in enumerate(parts):
        if not part or part.isspace():
            formatted.append(part)
            continue
        lowered = part.lower()
        if index != 0 and lowered in small_words:
            formatted.append(lowered)
        elif part.isupper() and len(part) <= 4:
            formatted.append(part)
        else:
            formatted.append(lowered.capitalize())
    return "".join(formatted).strip()
