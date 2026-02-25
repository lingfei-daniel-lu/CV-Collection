"""
Staged CV extraction pipeline adapted from collaborator prototype.

Keeps the existing project output schema (`journals` as counts) while using:
- section detection
- publication entry splitting
- metadata confidence scores
- targeted reprocessing for low-confidence metadata fields
- verification pass against original CV text
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from cv_collection.common_functions import safe_json_load
from cv_collection.config import OUTPUT_FOLDER
from cv_collection.prompt_templates import JOURNALS


CONFIDENCE_THRESHOLD = 0.8
MAX_VERIFY_CHARS = 15000
CONF_FIELDS = ["name", "promotion_year", "promotion_university", "years_post_phd"]
STAGED_CACHE_VERSION = "v1"
CACHE_ROOT = OUTPUT_FOLDER / "cache" / "staged_extraction"


SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "education": re.compile(
        r"(?i)^[#*\-_\s]*(?:education|academic\s+qualifications?|degrees?)\s*:?\s*$"
    ),
    "employment": re.compile(
        r"(?i)^[#*\-_\s]*(?:employment|academic\s+(?:positions?|appointments?)|"
        r"professional\s+experience|positions?\s+held|work\s+experience|"
        r"career\s+history|appointments?)\s*:?\s*$"
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
        r"(?i)^[#*\-_\s]*(?:awards?(?:\s+(?:and|&)\s+(?:honors?|honours?))?|"
        r"honors?|honours?|prizes?|fellowships?)\s*:?\s*$"
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


_NEW_ENTRY = re.compile(
    r"^(?:"
    r"\d{1,3}[\.\)]\s"
    r"|[-•●◦▪►]\s"
    r"|[\[\(]\d{1,3}[\]\)]\s"
    r")"
)


JOURNALS_BULLET = "\n".join("* " + j for j in JOURNALS)


METADATA_PROMPT = """\
ONLY RETURN JSON. NO MARKDOWN. NO COMMENTARY.

TASK
-----
Extract the following from the academic CV text below.
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

DEFINITIONS
- name: the CV owner's full name
- promotion_year: calendar year promoted to Associate Professor OR Reader
- promotion_university: institution where that promotion occurred
- years_post_phd: integer years between PhD completion and that promotion

RULES
- Be conservative. Only extract explicitly stated facts.
- If a field cannot be determined, return null with confidence 0.0.
- Do NOT infer or guess.
- Do NOT wrap output in backticks.
"""


PUBLICATION_PROMPT = (
    "ONLY RETURN JSON. NO MARKDOWN. NO COMMENTARY.\n\n"
    "TASK\n-----\n"
    "Below are individual publication entries extracted from an academic CV.\n"
    "For each of the journals listed below, identify every PUBLISHED article\n"
    "and return the PUBLICATION YEAR of each one.\n\n"
    + JOURNALS_BULLET
    + "\n\n"
    "MATCHING RULES\n"
    "- Match common abbreviations:\n"
    "  AER = AMERICAN ECONOMIC REVIEW, QJE = QUARTERLY JOURNAL OF ECONOMICS,\n"
    "  JPE = JOURNAL OF POLITICAL ECONOMY, RES/RESTUD = REVIEW OF ECONOMIC STUDIES,\n"
    "  RESTAT = REVIEW OF ECONOMICS AND STATISTICS,\n"
    "  AEJ: Macro/Applied/Policy/Micro = corresponding AEJ variants,\n"
    "  IER = INTERNATIONAL ECONOMIC REVIEW, JET = JOURNAL OF ECONOMIC THEORY,\n"
    "  JDE = JOURNAL OF DEVELOPMENT ECONOMICS,\n"
    "  JEEA = JOURNAL OF THE EUROPEAN ECONOMIC ASSOCIATION,\n"
    "  JME = JOURNAL OF MONETARY ECONOMICS, JIE = JOURNAL OF INTERNATIONAL ECONOMICS,\n"
    "  JPubE = JOURNAL OF PUBLIC ECONOMICS, JLE = JOURNAL OF LABOR ECONOMICS,\n"
    "  RAND = RAND JOURNAL OF ECONOMICS.\n"
    "- Match italicised or abbreviated journal names.\n"
    "- Only count PUBLISHED articles (not forthcoming, R&R, working papers, or under review).\n"
    "- Extract the publication year from each matching entry.\n\n"
    "Return JSON:\n"
    "{\n"
    '  "journals": {\n'
    '    "QUARTERLY JOURNAL OF ECONOMICS": [2005, 2012] or false,\n'
    '    "AMERICAN ECONOMIC REVIEW": [2018] or false,\n'
    "    ... (include ALL journals from the list)\n"
    "  }\n"
    "}\n\n"
    "For each journal:\n"
    "- If there are matching published articles, return a LIST of integer years\n"
    "  (one year per article, in chronological order). Duplicates are allowed\n"
    "  if multiple articles were published in the same journal in the same year.\n"
    "- If there are NO matching articles, return false.\n"
    "- If a year cannot be determined for a specific article, use null in the list.\n"
    "Do NOT wrap JSON in backticks."
)


FIELD_HINTS: dict[str, str] = {
    "name": "The full name of the CV owner. Usually at the very top of the document.",
    "promotion_year": (
        "The calendar year this person was promoted to Associate Professor or Reader. "
        "Look in the employment / positions / appointments section for dates next to "
        "'Associate Professor' or 'Reader'."
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
}


def detect_sections(text: str) -> dict[str, str]:
    lines = text.split("\n")
    hits: list[tuple[str, int]] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) > 100:
            continue
        for sec_name, pattern in SECTION_PATTERNS.items():
            if pattern.match(stripped):
                hits.append((sec_name, idx))
                break

    hits.sort(key=lambda item: item[1])
    result: dict[str, str] = {"full_text": text}
    for idx, (name, start) in enumerate(hits):
        end = hits[idx + 1][1] if idx + 1 < len(hits) else len(lines)
        result[name] = "\n".join(lines[start:end])
    return result


def split_publications(pub_text: str) -> list[str]:
    if not pub_text:
        return []

    lines = pub_text.split("\n")
    entries: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                entries.append(" ".join(current))
                current = []
            continue

        is_header = False
        for pat in (SECTION_PATTERNS.get("publications"), SECTION_PATTERNS.get("working_papers")):
            if pat and pat.match(stripped):
                is_header = True
                break
        if is_header:
            if current:
                entries.append(" ".join(current))
                current = []
            continue

        if _NEW_ENTRY.match(stripped) and current:
            entries.append(" ".join(current))
            current = [stripped]
        else:
            current.append(stripped)

    if current:
        entries.append(" ".join(current))

    return [entry for entry in entries if len(entry) > 25]
def _cache_path(client, messages: list[dict[str, str]]) -> Path | None:
    if os.getenv("CV_STAGE_CACHE_DISABLE", "").strip().lower() in {"1", "true", "yes"}:
        return None

    model_name = getattr(client, "model", "")
    model_key = getattr(getattr(client, "config", None), "key", "")
    temperature = getattr(getattr(client, "config", None), "temperature", None)
    payload = {
        "cache_version": STAGED_CACHE_VERSION,
        "model_key": model_key,
        "model_name": model_name,
        "temperature": temperature,
        "messages": messages,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    key = hashlib.sha256(blob).hexdigest()
    return CACHE_ROOT / key[:2] / f"{key}.json"


def _cache_get(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _cache_set(path: Path | None, response: dict[str, Any]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(response, ensure_ascii=False, sort_keys=True)
        tmp_path = path.with_suffix(
            path.suffix + f".tmp.{os.getpid()}.{threading.get_ident()}"
        )
        tmp_path.write_text(payload, encoding="utf-8")
        tmp_path.replace(path)
    except OSError:
        return


def _call_json(client, messages: list[dict[str, str]], *, label: str) -> dict[str, Any] | None:
    cache_path = _cache_path(client, messages)
    cached = _cache_get(cache_path)
    if cached is not None:
        return cached

    raw = client.chat_messages(messages)
    parsed = safe_json_load(raw or "", label=label)
    if parsed is not None:
        _cache_set(cache_path, parsed)
    return parsed


def _metadata_input(sections: dict[str, str]) -> str:
    chunks: list[str] = []
    top = "\n".join(sections["full_text"].split("\n")[:30])
    chunks.append("=== TOP OF CV ===\n" + top)
    for key in ("education", "employment"):
        if key in sections:
            chunks.append(f"=== {key.upper()} ===\n" + sections[key])
    if len(chunks) == 1:
        return sections["full_text"]
    return "\n\n".join(chunks)


def _normalise_years(val: Any) -> list[int]:
    if val is None or val is False or val == 0:
        return []
    if isinstance(val, int):
        return []
    if isinstance(val, list):
        years: list[int] = []
        for item in val:
            try:
                year = int(item)
            except (TypeError, ValueError):
                continue
            if 1900 <= year <= 2100:
                years.append(year)
        return sorted(years)
    return []


def extract_metadata(client, sections: dict[str, str], label: str) -> dict[str, Any]:
    data = _call_json(
        client,
        [
            {"role": "user", "content": METADATA_PROMPT},
            {"role": "user", "content": _metadata_input(sections)},
        ],
        label=f"{label}/meta",
    )
    return data or {}


def extract_publications(client, sections: dict[str, str], label: str) -> dict[str, Any]:
    pub_text = sections.get("publications", sections["full_text"])
    entries = split_publications(pub_text)
    if not entries:
        return {"journals": {j: False for j in JOURNALS}}
    numbered = "\n".join(f"{i + 1}. {entry}" for i, entry in enumerate(entries))
    data = _call_json(
        client,
        [
            {"role": "user", "content": PUBLICATION_PROMPT},
            {"role": "user", "content": "PUBLICATION ENTRIES:\n\n" + numbered},
        ],
        label=f"{label}/pubs",
    )
    return data or {"journals": {}}


def targeted_reprocess(client, field: str, sections: dict[str, str], label: str) -> dict[str, Any] | None:
    hint = FIELD_HINTS.get(field, "")
    prompt = (
        "ONLY RETURN JSON. NO MARKDOWN. NO COMMENTARY.\n\n"
        f"TASK: Re-examine this CV VERY carefully to extract ONE field: {field}\n\n"
        f"{hint}\n\n"
        "Return JSON:\n"
        "{\n"
        f'  "{field}": <value or null>,\n'
        f'  "{field}_confidence": <float 0.0-1.0>\n'
        "}\n\n"
        "Be extremely precise. Only state what is explicitly written.\n"
        "Do NOT wrap output in backticks."
    )
    return _call_json(
        client,
        [
            {"role": "user", "content": prompt},
            {"role": "user", "content": sections["full_text"]},
        ],
        label=f"{label}/retry_{field}",
    )


def verification_pass(
    client,
    extracted: dict[str, Any],
    sections: dict[str, str],
    label: str,
) -> dict[str, Any] | None:
    journals_for_verify: dict[str, list[int] | bool] = {}
    raw_years = extracted.get("journal_years", {})
    for journal in JOURNALS:
        years = _normalise_years(raw_years.get(journal, [])) if isinstance(raw_years, dict) else []
        journals_for_verify[journal] = years if years else False

    verify_data = {
        "name": extracted.get("name"),
        "promotion_year": extracted.get("promotion_year"),
        "promotion_university": extracted.get("promotion_university"),
        "years_post_phd": extracted.get("years_post_phd"),
        "journals": journals_for_verify,
    }

    cv_text = sections["full_text"]
    if len(cv_text) > MAX_VERIFY_CHARS:
        cv_text = cv_text[:MAX_VERIFY_CHARS] + "\n[... truncated ...]"

    prompt = (
        "ONLY RETURN JSON. NO MARKDOWN. NO COMMENTARY.\n\n"
        "TASK: Verify and correct the extracted data below against the original CV.\n\n"
        "EXTRACTED DATA:\n"
        + json.dumps(verify_data, indent=2)
        + "\n\n"
        "CHECK EACH FIELD:\n"
        "1. Is 'name' correct?\n"
        "2. Is 'promotion_year' the actual year of promotion to Associate Professor or Reader?\n"
        "3. Is 'promotion_university' correct?\n"
        "4. Is 'years_post_phd' correctly calculated (promotion_year minus PhD year)?\n"
        "5. For each journal, verify that:\n"
        "   a) Every listed article actually appears in the CV\n"
        "   b) The publication years are correct\n"
        "   c) No published articles in these journals were missed\n"
        "   d) Only PUBLISHED articles are counted (not forthcoming, R&R, etc.)\n"
        "   Target journals:\n"
        + JOURNALS_BULLET
        + "\n\n"
        "Return the CORRECTED JSON with the EXACT same structure as above.\n"
        "For journals, return a list of integer years (one per article) or false.\n"
        "Keep correct fields unchanged. Fix wrong ones. Set unknowable fields to null.\n"
        "Do NOT wrap output in backticks."
    )
    return _call_json(
        client,
        [
            {"role": "user", "content": prompt},
            {"role": "user", "content": "ORIGINAL CV:\n\n" + cv_text},
        ],
        label=f"{label}/verify",
    )


def extract_cv_staged(
    client,
    cv_text: str,
    label: str,
    *,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    do_verification: bool = True,
) -> dict[str, Any]:
    sections = detect_sections(cv_text)

    meta = extract_metadata(client, sections, label)
    pubs = extract_publications(client, sections, label)

    for field in CONF_FIELDS:
        conf_key = f"{field}_confidence"
        try:
            conf = float(meta.get(conf_key, 0.0) or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf >= confidence_threshold:
            continue
        retry = targeted_reprocess(client, field, sections, label)
        if not isinstance(retry, dict):
            continue
        try:
            new_conf = float(retry.get(conf_key, 0.0) or 0.0)
        except (TypeError, ValueError):
            new_conf = 0.0
        if new_conf > conf:
            meta[field] = retry.get(field)
            meta[conf_key] = new_conf

    journal_years: dict[str, list[int]] = {}
    raw_journals = pubs.get("journals", {}) if isinstance(pubs, dict) else {}
    if not isinstance(raw_journals, dict):
        raw_journals = {}
    for journal in JOURNALS:
        journal_years[journal] = _normalise_years(raw_journals.get(journal, False))

    merged: dict[str, Any] = {
        "name": meta.get("name"),
        "promotion_year": meta.get("promotion_year"),
        "promotion_university": meta.get("promotion_university"),
        "years_post_phd": meta.get("years_post_phd"),
        "journal_years": journal_years,
        "metadata_confidence": {
            f: meta.get(f"{f}_confidence") for f in CONF_FIELDS if f"{f}_confidence" in meta
        },
        "sections_found": [key for key in sections.keys() if key != "full_text"],
    }

    if do_verification:
        verified = verification_pass(client, merged, sections, label)
        if isinstance(verified, dict):
            for key in ("name", "promotion_year", "promotion_university", "years_post_phd"):
                if key in verified:
                    merged[key] = verified.get(key)
            verified_journals = verified.get("journals", {})
            if isinstance(verified_journals, dict):
                for journal in JOURNALS:
                    merged["journal_years"][journal] = _normalise_years(
                        verified_journals.get(journal, False)
                    )

    merged["journals"] = {journal: len(merged["journal_years"][journal]) for journal in JOURNALS}
    return merged
