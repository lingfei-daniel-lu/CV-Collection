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
from cv_collection.research_field_taxonomy import normalize_research_fields
from cv_collection.section_taxonomy import (
    SECTION_PATTERNS,
    detect_sections,
    extract_local_research_fields,
)
from cv_collection.staged_prompts import (
    build_metadata_prompt,
    build_publication_prompt,
    build_targeted_retry_prompt,
    build_verification_prompt,
    metadata_fields_for_rank,
)
from cv_collection.json_parsing import safe_json_load


CONFIDENCE_THRESHOLD = 0.8
MAX_VERIFY_CHARS = 15000
STAGED_CACHE_VERSION = "v2"
CACHE_ROOT = OUTPUT_FOLDER / "cache" / "staged_extraction"


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


def _resolve_rank(label: str, rank: str | None) -> str:
    if rank is None:
        return infer_rank_from_label(label)
    provided_rank = rank.strip().lower()
    if provided_rank not in {"associate", "full"}:
        raise ValueError(f"Invalid rank '{rank}': expected 'associate' or 'full'.")
    return provided_rank


def _metadata_output_fields(rank: str) -> list[str]:
    fields = ["name", "research_fields", "promotion_year", "promotion_university", "years_post_phd"]
    if rank == "full":
        fields.extend(["full_promotion_year", "full_promotion_university", "years_post_phd_full"])
    return fields


def _build_merged_metadata(meta: dict[str, Any], *, rank: str) -> dict[str, Any]:
    merged = {
        "rank": rank,
        "name": meta.get("name"),
        "research_fields": normalize_research_fields(meta.get("research_fields", "")),
        "promotion_year": meta.get("promotion_year"),
        "promotion_university": meta.get("promotion_university"),
        "years_post_phd": meta.get("years_post_phd"),
    }
    if rank == "full":
        merged.update(
            {
                "full_promotion_year": meta.get("full_promotion_year"),
                "full_promotion_university": meta.get("full_promotion_university"),
                "years_post_phd_full": meta.get("years_post_phd_full"),
            }
        )
    else:
        merged.update(
            {
                "full_promotion_year": None,
                "full_promotion_university": None,
                "years_post_phd_full": None,
            }
        )
    return merged


def _apply_verified_metadata(
    merged: dict[str, Any],
    verified: dict[str, Any],
    *,
    rank: str,
    local_research_fields: str,
) -> None:
    for key in _metadata_output_fields(rank):
        if key not in verified:
            continue
        if key == "research_fields" and local_research_fields:
            continue
        if key == "research_fields":
            merged[key] = normalize_research_fields(verified.get(key, ""))
            continue
        merged[key] = verified.get(key)


def infer_rank_from_label(label: str | None) -> str:
    if not label:
        raise ValueError("Missing file label; expected path containing '/associate/' or '/full/'.")
    tokens = [token.strip().lower() for token in re.split(r"[\\/]+", label) if token.strip()]
    has_full = "full" in tokens
    has_associate = "associate" in tokens
    if has_full and has_associate:
        raise ValueError(
            f"Ambiguous rank path '{label}': contains both 'associate' and 'full'."
        )
    if has_full:
        return "full"
    if has_associate:
        return "associate"
    raise ValueError(
        f"Invalid rank path '{label}': expected directory token 'associate' or 'full'."
    )


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
    for key in ("research_interests", "education", "employment"):
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
    for key in ("research_interests", "education", "employment"):
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
    if isinstance(val, bool):
        return []
    if isinstance(val, (int, str)):
        try:
            year = int(val)
        except (TypeError, ValueError):
            return []
        return [year] if 1900 <= year <= 2100 else []
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


def extract_metadata(
    client, sections: dict[str, str], label: str, *, rank: str
) -> dict[str, Any]:
    data = _call_json(
        client,
        [
            {"role": "user", "content": build_metadata_prompt(rank)},
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
    client, fields: list[str], sections: dict[str, str], label: str, *, rank: str
) -> dict[str, Any] | None:
    conf_fields = set(metadata_fields_for_rank(rank))
    requested = [field for field in fields if field in conf_fields]
    if not requested:
        return None
    return _call_json(
        client,
        [
            {
                "role": "user",
                "content": build_targeted_retry_prompt(requested, rank=rank),
            },
            {"role": "user", "content": sections["full_text"]},
        ],
        label=f"{label}/retry_meta",
    )


def _verification_payload(extracted: dict[str, Any], *, rank: str) -> dict[str, Any]:
    journals_for_verify: dict[str, list[int] | bool] = {}
    raw_years = extracted.get("journal_years", {})
    for journal in JOURNALS:
        years = _normalise_years(raw_years.get(journal, [])) if isinstance(raw_years, dict) else []
        journals_for_verify[journal] = years if years else False
    payload = {
        "name": extracted.get("name"),
        "research_fields": normalize_research_fields(extracted.get("research_fields", "")),
        "promotion_year": extracted.get("promotion_year"),
        "promotion_university": extracted.get("promotion_university"),
        "years_post_phd": extracted.get("years_post_phd"),
        "journals": journals_for_verify,
    }
    if rank == "full":
        payload["full_promotion_year"] = extracted.get("full_promotion_year")
        payload["full_promotion_university"] = extracted.get("full_promotion_university")
        payload["years_post_phd_full"] = extracted.get("years_post_phd_full")
    return payload


def _should_run_verification(
    merged: dict[str, Any],
    sections: dict[str, str],
    *,
    confidence_fields: list[str],
    confidence_threshold: float,
) -> bool:
    """
    Simple risk-based trigger to avoid unnecessary verification calls.

    Run verification only when extraction looks uncertain or structurally risky.
    """
    meta_conf = merged.get("metadata_confidence", {})
    if isinstance(meta_conf, dict):
        for field in confidence_fields:
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
    *,
    rank: str,
) -> dict[str, Any] | None:
    verify_data = _verification_payload(extracted, rank=rank)
    verify_context = _build_verification_context(sections)
    if not verify_context:
        return None
    verified = _call_json(
        client,
        [
            {
                "role": "user",
                "content": build_verification_prompt(verify_data, rank=rank),
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
    rank: str | None = None,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    do_verification: bool = True,
) -> dict[str, Any]:
    resolved_rank = _resolve_rank(label, rank)
    conf_fields = metadata_fields_for_rank(resolved_rank)
    sections = detect_sections(cv_text)

    local_research_fields = normalize_research_fields(extract_local_research_fields(cv_text, sections))

    meta = extract_metadata(client, sections, label, rank=resolved_rank)
    if local_research_fields:
        meta["research_fields"] = local_research_fields
        meta["research_fields_confidence"] = 1.0
    else:
        meta["research_fields"] = normalize_research_fields(meta.get("research_fields", ""))
    pubs = extract_publications(client, sections, label)

    low_conf_fields: list[str] = []
    old_conf_by_field: dict[str, float] = {}
    for field in conf_fields:
        conf_key = f"{field}_confidence"
        conf = _parse_confidence(meta.get(conf_key, 0.0))
        old_conf_by_field[field] = conf
        if conf < confidence_threshold:
            low_conf_fields.append(field)

    if low_conf_fields:
        retry = targeted_reprocess(client, low_conf_fields, sections, label, rank=resolved_rank)
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

    merged: dict[str, Any] = _build_merged_metadata(meta, rank=resolved_rank)
    merged["journal_years"] = journal_years
    merged["metadata_confidence"] = {
        f: meta.get(f"{f}_confidence") for f in conf_fields if f"{f}_confidence" in meta
    }
    merged["sections_found"] = [key for key in sections.keys() if key != "full_text"]

    if do_verification:
        should_verify = _should_run_verification(
            merged,
            sections,
            confidence_fields=conf_fields,
            confidence_threshold=confidence_threshold,
        )
        verified = (
            verification_pass(client, merged, sections, label, rank=resolved_rank)
            if should_verify
            else None
        )
        if isinstance(verified, dict):
            _apply_verified_metadata(
                merged,
                verified,
                rank=resolved_rank,
                local_research_fields=local_research_fields,
            )
            verified_journals = verified.get("journals", {})
            if "publications" in sections and isinstance(verified_journals, dict):
                for journal in JOURNALS:
                    merged["journal_years"][journal] = _normalise_years(
                        verified_journals.get(journal, False)
                    )

    merged["research_fields"] = normalize_research_fields(merged.get("research_fields", ""))
    merged["journals"] = {journal: len(merged["journal_years"][journal]) for journal in JOURNALS}
    return merged
