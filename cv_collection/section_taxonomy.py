"""
Section-header patterns used by staged CV extraction.
"""

from __future__ import annotations

import re


_SECTION_RESEARCH_HEADER_BODY = (
    r"(?:primary\s+)?research\s+(?:interests?|fields?|areas?)"
    r"(?:\s+(?:and|&)\s+(?:teaching\s+)?interests?)?|"
    r"current\s+research\s+interests?|"
    r"research\s+(?:focus|foci)|"
    r"primary\s+fields?|"
    r"fields?\s+of\s+(?:interest|specialization|expertise)|"
    r"areas?\s+of\s+(?:interest|specialization|expertise|research)|"
    r"research\s+and\s+teaching\s+interests?|"
    r"fields?"
)

_INLINE_RESEARCH_HEADER_BODY = (
    r"(?:(?:major|current|primary)\s+)?research\s+(?:interests?|fields?|areas?)"
    r"(?:\s+(?:and|&)\s+(?:teaching\s+)?interests?)?|"
    r"current\s+research\s+interests?|"
    r"research\s+(?:focus|foci)|"
    r"primary\s+fields?|"
    r"research\s+and\s+teaching\s+interests?|"
    r"(?:(?:major|current|primary)\s+)?fields?\s+of\s+(?:interest|specialization|expertise)|"
    r"areas?\s+of\s+(?:interest|specialization|expertise|research)|"
    r"fields?"
)


SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "research_interests": re.compile(
        rf"(?i)^[#*\-_\s]*(?:{_SECTION_RESEARCH_HEADER_BODY})\s*:?\s*$"
    ),
    "education": re.compile(
        r"(?i)^[#*\-_\s]*(?:education|academic\s+qualifications?|degrees?)\s*:?\s*$"
    ),
    "employment": re.compile(
        r"(?i)^[#*\-_\s]*(?:"
        r"(?:academic|professional|economic)?\s*employment(?:\s+history)?|"
        r"employment(?:\s+history)?|"
        r"academic\s+(?:positions?|appointments?)|"
        r"positions?\s+held|"
        r"work\s+experience|"
        r"career\s+history|"
        r"appointments?"
        r")\s*:?\s*$"
    ),
    "publications": re.compile(
        r"(?i)^[#*\-_\s]*(?:publications?|published\s+papers?|"
        r"journal\s+articles?|research\s+papers?|selected\s+publications?|"
        r"refereed\s+(?:journal\s+)?publications?|"
        r"peer[- ]reviewed\s+(?:journal\s+)?(?:publications?|articles?))\s*:?\s*$"
    ),
    "working_papers": re.compile(
        r"(?i)^[#*\-_\s]*(?:working\s+papers?|work\s+in\s+progress|"
        r"papers?\s+under\s+review|unpublished\s+manuscripts?|"
        r"research\s+in\s+progress)\s*:?\s*$"
    ),
    "awards": re.compile(
        r"(?i)^[#*\-_\s]*(?:"
        r"(?:general|research)?\s*awards?(?:\s+for\s+\w+)?|"
        r"awards?\s+for\s+\w+|"
        r"awards?(?:\s+(?:and|&)\s+(?:honors?|honours?))?|"
        r"honors?\s+and\s+offices\s+held|"
        r"honours?\s+and\s+offices\s+held|"
        r"honors?|honours?|prizes?|fellowships?"
        r")\s*:?\s*$"
    ),
    "teaching": re.compile(
        r"(?i)^[#*\-_\s]*(?:teaching(?:\s+experience)?|courses?\s+taught)\s*:?\s*$"
    ),
    "grants": re.compile(
        r"(?i)^[#*\-_\s]*(?:grants?(?:\s+(?:and|&)\s+funding)?|"
        r"research\s+funding|external\s+funding)\s*:?\s*$"
    ),
    "service": re.compile(
        r"(?i)^[#*\-_\s]*(?:(?:professional\s+)?service|"
        r"professional\s+activities|editorial|refereeing)\s*:?\s*$"
    ),
    "references": re.compile(r"(?i)^[#*\-_\s]*(?:references?|referees?)\s*:?\s*$"),
}

RESEARCH_INTEREST_HEADER_PATTERN = re.compile(
    rf"(?i)^(?:{_INLINE_RESEARCH_HEADER_BODY})\s*[:.]?\s*"
)

EXPLICIT_RESEARCH_FIELD_INLINE_PATTERN = re.compile(
    r"(?i)(?:^|\||\t|\s{2,})"
    rf"(?P<label>{_INLINE_RESEARCH_HEADER_BODY})\s*:\s*(?P<content>.+?)\s*$"
)

PRIMARY_PREFIX_PATTERN = re.compile(r"(?i)^primary\s*[:.]?\s*")
SECONDARY_PREFIX_PATTERN = re.compile(r"(?i)^secondary\s*[:.]?\s*")

RESEARCH_HEADER_FRAGMENT_WORDS = {
    "research",
    "interests",
    "interest",
    "fields",
    "field",
    "current",
    "areas",
    "area",
    "focus",
    "foci",
    "specialization",
    "expertise",
    "teaching",
    "and",
    "of",
    "primary",
}

SECTION_HEADER_HINT = re.compile(
    r"(?i)\b(?:"
    r"academic|activities?|affiliations?|appointments?|articles?|awards?|board|books?|"
    r"committee|education|editor(?:ial)?|employment|experience|fields?|grants?|history|"
    r"focus|foci|specialization|expertise|current|"
    r"honou?rs?|offices?|papers?|positions?|professional|publications?|references?|"
    r"research|service|teaching|working"
    r")\b"
)

DETECT_SECTION_TITLE_PATTERNS: dict[str, re.Pattern[str]] = {
    "research_interests": re.compile(
        rf"(?i)^(?:{_SECTION_RESEARCH_HEADER_BODY})\s*[:.]?\s*$"
    ),
    "education": re.compile(r"(?i)^education\s*[:.]?\s*$"),
    "employment": re.compile(
        r"(?i)^(?:professional\s+experience|work\s+experience|employment|current\s+position)"
        r"\s*[:.]?\s*$"
    ),
}


def extract_caps_prefix(line: str) -> str:
    words = line.strip().split()
    prefix: list[str] = []
    has_caps = False
    for word in words:
        if word == "|":
            break
        clean = re.sub(r"[^A-Za-z]", "", word)
        if not clean:
            if word in {"&", ",", "-", "/", "(", ")"} and has_caps:
                prefix.append(word)
            else:
                break
        elif clean.isupper() and len(clean) >= 2:
            prefix.append(word)
            has_caps = True
        elif has_caps and clean.lower() in {"and", "of", "the", "in", "for", "a"}:
            prefix.append(word)
        else:
            break
    return " ".join(prefix).strip().rstrip(":.,;& ")


def is_research_header_fragment(line: str) -> bool:
    tokens = re.findall(r"[A-Za-z]+", line.lower())
    if not tokens:
        return False
    if not any(token in {"research", "interests", "interest", "fields", "field", "areas"} for token in tokens):
        return False
    return all(token in RESEARCH_HEADER_FRAGMENT_WORDS for token in tokens)


def looks_like_section_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    for sec_name, pattern in SECTION_PATTERNS.items():
        if sec_name != "research_interests" and pattern.match(stripped):
            return True

    tokens = re.findall(r"[A-Za-z]+", stripped.lower())
    if not tokens or len(tokens) > 10:
        return False
    if not SECTION_HEADER_HINT.search(stripped):
        return False

    letters = [ch for ch in stripped if ch.isalpha()]
    is_mostly_caps = bool(letters) and sum(ch.isupper() for ch in letters) / len(letters) >= 0.7
    if stripped.endswith(":") or is_mostly_caps:
        return True
    return all(SECTION_HEADER_HINT.fullmatch(token) for token in tokens)


def _looks_like_generic_title(line: str) -> bool:
    stripped = line.strip().rstrip(":")
    if not stripped or len(stripped) > 60:
        return False
    if re.search(r'[\d,;."“”()]', stripped):
        return False
    words = re.findall(r"[A-Za-z]+", stripped)
    if not 2 <= len(words) <= 6:
        return False
    small_words = {"and", "of", "the", "in", "for", "to"}
    return all(word[0].isupper() or word.lower() in small_words for word in stripped.split())


def extract_research_fields_from_section(section_text: str) -> str:
    if not section_text:
        return ""

    lines = section_text.strip().split("\n")
    content_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if content_lines:
                break
            continue
        if "|" in stripped:
            first_cell, remainder = stripped.split("|", 1)
            if RESEARCH_INTEREST_HEADER_PATTERN.match(first_cell.strip()) or is_research_header_fragment(first_cell.strip()):
                stripped = remainder.strip()
                if not stripped:
                    continue
        cleaned = RESEARCH_INTEREST_HEADER_PATTERN.sub("", stripped).strip()
        if not content_lines and is_research_header_fragment(cleaned):
            continue
        if content_lines and looks_like_section_header(cleaned):
            break
        if cleaned:
            content_lines.append(cleaned)

    if not content_lines:
        return ""

    primary_lines: list[str] = []
    has_primary_label = False
    for line in content_lines:
        if PRIMARY_PREFIX_PATTERN.match(line):
            has_primary_label = True
            primary_lines.append(PRIMARY_PREFIX_PATTERN.sub("", line).strip())
        elif SECONDARY_PREFIX_PATTERN.match(line):
            break
        elif has_primary_label:
            primary_lines.append(line)
        else:
            primary_lines.append(line)

    result = "; ".join(part for part in primary_lines if part).strip()
    result = re.sub(r"\s*[;,]\s*$", "", result)
    result = re.sub(r"\s*;\s*;+\s*", "; ", result)
    return result


def extract_explicit_research_fields_fallback(text: str) -> str:
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) > 240:
            continue
        if any(quote in stripped for quote in {'"', "“", "”"}):
            continue
        match = EXPLICIT_RESEARCH_FIELD_INLINE_PATTERN.search(stripped)
        if match:
            content = match.group("content").strip(" ,;:.")
            if content and len(content) <= 180 and not looks_like_section_header(content):
                return extract_research_fields_from_section(f"{match.group('label')}: {content}")

        if not RESEARCH_INTEREST_HEADER_PATTERN.fullmatch(stripped):
            continue
        content_lines: list[str] = []
        for follow in lines[idx + 1 : idx + 4]:
            candidate = follow.strip()
            if not candidate:
                if content_lines:
                    break
                continue
            if len(candidate) > 140 or looks_like_section_header(candidate) or _looks_like_generic_title(candidate):
                break
            if any(quote in candidate for quote in {'"', "“", "”"}):
                break
            content_lines.append(candidate)
            if len(content_lines) >= 2:
                break
        if content_lines:
            return extract_research_fields_from_section(f"{stripped}\n" + "\n".join(content_lines))
    return ""


def extract_local_research_fields(text: str, sections: dict[str, str] | None = None) -> str:
    local_sections = sections or detect_sections(text)
    section_text = local_sections.get("research_interests", "")
    extracted = extract_research_fields_from_section(section_text)
    if extracted:
        return extracted
    return extract_explicit_research_fields_fallback(text)


def detect_sections(text: str) -> dict[str, str]:
    lines = text.split("\n")
    hits: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()

    def register(name: str, idx: int) -> None:
        key = (name, idx)
        if key not in seen:
            hits.append(key)
            seen.add(key)

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) > 120:
            continue
        for sec_name, pattern in SECTION_PATTERNS.items():
            if pattern.match(stripped):
                register(sec_name, idx)
                break

    # Inline research headers like "Fields of Specialization: Micro..., Game Theory..."
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) > 240:
            continue
        if RESEARCH_INTEREST_HEADER_PATTERN.match(stripped):
            remainder = RESEARCH_INTEREST_HEADER_PATTERN.sub("", stripped).strip()
            if remainder:
                register("research_interests", idx)

    for idx in range(len(lines) - 1):
        first = lines[idx].strip()
        if not first or len(first) > 40:
            continue
        first_prefix = extract_caps_prefix(first)
        if not first_prefix or first_prefix != first.rstrip(":., ;"):
            continue
        for look_ahead in range(idx + 1, min(idx + 3, len(lines))):
            second = lines[look_ahead].strip()
            if not second:
                continue
            second_prefix = extract_caps_prefix(second)
            if second_prefix:
                combined = f"{first_prefix} {second_prefix}".strip()
                for sec_name, pattern in SECTION_PATTERNS.items():
                    if pattern.match(combined):
                        register(sec_name, idx)
                        break
            break

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        prefix = extract_caps_prefix(stripped)
        if not prefix or len(prefix) < 4:
            continue
        for sec_name, pattern in SECTION_PATTERNS.items():
            if pattern.match(prefix):
                register(sec_name, idx)
                break

    for idx, line in enumerate(lines):
        if "|" not in line:
            continue
        first_cell = line.split("|", 1)[0].strip()
        if not first_cell or len(first_cell) >= 50:
            continue
        for sec_name, pattern in SECTION_PATTERNS.items():
            if pattern.match(first_cell):
                register(sec_name, idx)
                break

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) > 80:
            continue
        for sec_name, pattern in DETECT_SECTION_TITLE_PATTERNS.items():
            if pattern.match(stripped):
                register(sec_name, idx)
                break

    hits.sort(key=lambda item: item[1])
    result: dict[str, str] = {"full_text": text}
    for idx, (name, start) in enumerate(hits):
        end = hits[idx + 1][1] if idx + 1 < len(hits) else len(lines)
        chunk = "\n".join(lines[start:end])
        if name in result:
            result[name] += "\n\n" + chunk
        else:
            result[name] = chunk
    return result
