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

from cv_collection.config import OUTPUT_FOLDER
from cv_collection.journal_taxonomy import JOURNALS
from cv_collection.staged_prompts import (
    build_metadata_prompt,
    build_publication_prompt,
    build_targeted_retry_prompt,
    build_verification_prompt,
)
from cv_collection.json_parsing import safe_json_load


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

_INLINE_PUB_HEADER = re.compile(
    r"(?i)^(?:"
    r"publications?(?:\s+(?:and|&)\s+\w+)*|"
    r"refereed\s+(?:journal\s+)?publications?|"
    r"selected\s+publications?|"
    r"published\s+papers?|"
    r"journal\s+articles?|"
    r"research\s+papers?|"
    r"peer[- ]reviewed\s+(?:journal\s+)?(?:publications?|articles?)|"
    r"working\s+papers?|"
    r"(?:papers?\s+)?under\s+review(?:\s+and\s+working\s+papers?)?|"
    r"in\s+progress"
    r")(?:\s+(?:and|&)\s+\w+)*"
    r"\s*[:.]?\s+"
)


def _strip_inline_header(line: str) -> str:
    match = _INLINE_PUB_HEADER.match(line)
    if match:
        return line[match.end() :]
    return line

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
        chunk = "\n".join(lines[start:end])
        if name in result:
            # Some CVs contain multiple sections with the same header (e.g., "Selected Publications"
            # and a later "Publications" block). Preserve all matched chunks instead of overwriting.
            result[name] += "\n\n" + chunk
        else:
            result[name] = chunk
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

        cleaned = _strip_inline_header(stripped)
        if cleaned != stripped:
            if current:
                entries.append(" ".join(current))
                current = []
            if cleaned:
                current = [cleaned]
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


def _parse_confidence(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _format_verification_block(title: str, content: str) -> str:
    body = content.strip()
    return f"=== {title} ===\n{body}" if body else f"=== {title} ==="


def _build_verification_context(sections: dict[str, str]) -> str | None:
    """
    Build a section-aware verification context without risky truncation.

    Long-CV fallback strategy:
    - prefer metadata + publications evidence
    - then publications-only evidence
    - if no publications section exists, allow metadata-only context
    - otherwise return None and skip verification
    """
    full_text = sections["full_text"]
    if len(full_text) <= MAX_VERIFY_CHARS:
        return full_text

    top = "\n".join(full_text.split("\n")[:40]).strip()
    base_blocks: list[str] = []
    if top:
        base_blocks.append(_format_verification_block("TOP OF CV", top))
    for key in ("education", "employment"):
        value = sections.get(key, "").strip()
        if value:
            base_blocks.append(_format_verification_block(key.upper(), value))
    base_context = "\n\n".join(base_blocks).strip()

    pub_value = sections.get("publications", "").strip()
    if not pub_value:
        if base_context and len(base_context) <= MAX_VERIFY_CHARS:
            return base_context
        return None
    pub_block = _format_verification_block("PUBLICATIONS", pub_value)

    working_value = sections.get("working_papers", "").strip()
    working_block = (
        _format_verification_block("WORKING_PAPERS", working_value) if working_value else ""
    )

    candidates: list[str] = []
    if base_context:
        if working_block:
            candidates.append("\n\n".join([base_context, pub_block, working_block]).strip())
        candidates.append("\n\n".join([base_context, pub_block]).strip())
    if working_block:
        candidates.append("\n\n".join([pub_block, working_block]).strip())
    candidates.append(pub_block)

    for candidate in candidates:
        if candidate and len(candidate) <= MAX_VERIFY_CHARS:
            return candidate
    return None


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
            {"role": "user", "content": build_metadata_prompt()},
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
            {"role": "user", "content": build_publication_prompt()},
            {"role": "user", "content": "PUBLICATION ENTRIES:\n\n" + numbered},
        ],
        label=f"{label}/pubs",
    )
    return data or {"journals": {}}


def targeted_reprocess(
    client, fields: list[str], sections: dict[str, str], label: str
) -> dict[str, Any] | None:
    requested = [field for field in fields if field in CONF_FIELDS]
    if not requested:
        return None
    hint_by_field = {field: FIELD_HINTS.get(field, "") for field in requested}
    return _call_json(
        client,
        [
            {
                "role": "user",
                "content": build_targeted_retry_prompt(requested, hint_by_field),
            },
            {"role": "user", "content": sections["full_text"]},
        ],
        label=f"{label}/retry_meta",
    )


def _verification_payload(extracted: dict[str, Any]) -> dict[str, Any]:
    journals_for_verify: dict[str, list[int] | bool] = {}
    raw_years = extracted.get("journal_years", {})
    for journal in JOURNALS:
        years = _normalise_years(raw_years.get(journal, [])) if isinstance(raw_years, dict) else []
        journals_for_verify[journal] = years if years else False
    return {
        "name": extracted.get("name"),
        "promotion_year": extracted.get("promotion_year"),
        "promotion_university": extracted.get("promotion_university"),
        "years_post_phd": extracted.get("years_post_phd"),
        "journals": journals_for_verify,
    }


def _should_run_verification(
    merged: dict[str, Any],
    sections: dict[str, str],
    *,
    confidence_threshold: float,
) -> bool:
    """
    Simple risk-based trigger to avoid unnecessary verification calls.

    Run verification only when extraction looks uncertain or structurally risky.
    """
    meta_conf = merged.get("metadata_confidence", {})
    if isinstance(meta_conf, dict):
        for field in CONF_FIELDS:
            if _parse_confidence(meta_conf.get(field, 0.0)) < confidence_threshold:
                return True

    # If key sections are missing, upstream extraction had to rely on weaker context.
    if "employment" not in sections or "publications" not in sections:
        return True

    # Broaden the gate without full verification: verify whenever we extracted any target-journal hits.
    journal_years = merged.get("journal_years", {})
    if isinstance(journal_years, dict) and any(
        isinstance(v, list) and len(v) > 0 for v in journal_years.values()
    ):
        return True

    return False


def verification_pass(
    client,
    extracted: dict[str, Any],
    sections: dict[str, str],
    label: str,
) -> dict[str, Any] | None:
    verify_data = _verification_payload(extracted)
    verify_context = _build_verification_context(sections)
    if not verify_context:
        return None
    verified = _call_json(
        client,
        [
            {
                "role": "user",
                "content": build_verification_prompt(verify_data),
            },
            {"role": "user", "content": "ORIGINAL CV:\n\n" + verify_context},
        ],
        label=f"{label}/verify",
    )
    return verified


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

    low_conf_fields: list[str] = []
    old_conf_by_field: dict[str, float] = {}
    for field in CONF_FIELDS:
        conf_key = f"{field}_confidence"
        conf = _parse_confidence(meta.get(conf_key, 0.0))
        old_conf_by_field[field] = conf
        if conf < confidence_threshold:
            low_conf_fields.append(field)

    if low_conf_fields:
        retry = targeted_reprocess(client, low_conf_fields, sections, label)
        if isinstance(retry, dict):
            for field in low_conf_fields:
                conf_key = f"{field}_confidence"
                conf = old_conf_by_field.get(field, 0.0)
                new_conf = _parse_confidence(retry.get(conf_key, 0.0))
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
        should_verify = _should_run_verification(
            merged,
            sections,
            confidence_threshold=confidence_threshold,
        )
        verified = verification_pass(client, merged, sections, label) if should_verify else None
        if isinstance(verified, dict):
            for key in ("name", "promotion_year", "promotion_university", "years_post_phd"):
                if key in verified:
                    merged[key] = verified.get(key)
            verified_journals = verified.get("journals", {})
            if "publications" in sections and isinstance(verified_journals, dict):
                for journal in JOURNALS:
                    merged["journal_years"][journal] = _normalise_years(
                        verified_journals.get(journal, False)
                    )

    merged["journals"] = {journal: len(merged["journal_years"][journal]) for journal in JOURNALS}
    return merged
