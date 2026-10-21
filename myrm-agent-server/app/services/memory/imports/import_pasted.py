"""Pasted free-text memory import adapter (the "paste from any assistant" lane).

[INPUT]
Raw assistant output pasted by the user under the ``text`` key (``payload`` is
accepted as an alias). The app's export prompt asks the source assistant for one
code block of ``[YYYY-MM-DD] - entry`` lines grouped under the canonical
headings ``## RULES`` / ``## PROFILE`` / ``## FACTS`` / ``## PREFERENCES``.

[OUTPUT]
MemoryImportDryRunResult mapping parsed entries into procedural / profile /
semantic buckets; dates are lifted out of the entry text into the timestamp.
refusal_result(): explicit zero-item refusal with a user-readable reason.

[POS]
Deterministic lane of the paste import (sources without an export package). No
LLM calls: the export prompt is the schema, secrets are scrubbed before parsing,
oversized input is refused explicitly, and unparseable input never silently
imports nothing. The optional model-assisted lane lives in import_pasted_model.py
and reuses the vocabulary helpers defined here.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import NamedTuple

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportMappingItem,
)

from app.services.memory.imports.import_adapter_utils import (
    build_metadata,
    build_result,
    iso_or_now,
)
from app.services.memory.imports.secret_scrubber import scrub_sensitive_data

MAX_PASTED_TEXT_CHARS = 4_000_000
MAX_PASTED_ENTRIES = 5000

WARNING_PASTED_EMPTY = "pasted_empty"
WARNING_PASTED_TEXT_TOO_LARGE = "pasted_text_too_large"
WARNING_PASTED_ENTRIES_OVER_LIMIT = "pasted_entries_over_limit"
WARNING_PASTED_MODEL_FALLBACK = "pasted_model_extraction_failed"

BUCKET_PROCEDURAL = "procedural"
BUCKET_PROFILE = "profile"
BUCKET_SEMANTIC = "semantic"

_FENCE_PATTERN = re.compile(r"^\s*```")
_HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s*(?P<title>.+?)\s*$")
_DATED_ENTRY_PATTERN = re.compile(
    r"^\s*(?:[-*•·]|\d+[.)])?\s*"
    r"(?:[\[【]\s*(?P<year>\d{4})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})\s*[\]】]\s*(?:[-–—:：]\s*)?"
    r"|(?P<year_plain>\d{4})[-/.](?P<month_plain>\d{1,2})[-/.](?P<day_plain>\d{1,2})\s*[-–—:：]\s*)"
    r"(?P<body>\S.*?)\s*$",
)
_BULLET_PATTERN = re.compile(r"^\s*(?:[-*•·]|\d+[.)])\s*(?P<body>\S.*?)\s*$")

_PROCEDURAL_HEADINGS = frozenset(
    {
        "rules",
        "rule",
        "instructions",
        "directives",
        "constraints",
        "preferences",
        "preferences and corrections",
        "corrections",
        "指令",
        "规则",
        "要求",
        "偏好",
        "偏好与纠错",
        "纠错",
        "規則",
        "偏好與糾正",
        "指示",
        "ルール",
        "指示事項",
        "好み",
        "訂正",
        "지시",
        "규칙",
        "선호",
        "수정",
        "anweisungen",
        "regeln",
        "präferenzen",
        "korrekturen",
    },
)
_PROFILE_HEADINGS = frozenset(
    {
        "profile",
        "personal",
        "personal details",
        "identity",
        "个人信息",
        "个人资料",
        "画像",
        "个人信息与偏好",
        "個人資訊",
        "個人資料",
        "プロフィール",
        "個人情報",
        "프로필",
        "개인 정보",
        "profil",
        "persönliche daten",
    },
)
_SEMANTIC_HEADINGS = frozenset(
    {
        "facts",
        "projects",
        "projects and tools",
        "tools",
        "knowledge",
        "topics",
        "other",
        "事实",
        "项目",
        "项目与工具",
        "工具",
        "知识",
        "其他",
        "事實",
        "專案",
        "專案與工具",
        "知識",
        "その他",
        "事実",
        "プロジェクト",
        "ツール",
        "프로젝트",
        "도구",
        "사실",
        "지식",
        "기타",
        "fakten",
        "wissen",
        "projekte",
        "werkzeuge",
        "sonstiges",
    },
)


class _ParsedEntry(NamedTuple):
    """One parsed pasted entry with its lane bucket and optional date."""

    content: str
    bucket: str
    dated: str | None


def dry_run_pasted_memory(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Parse pasted assistant output into memory buckets without persisting."""

    raw_text = payload.get("text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        raw_text = payload.get("payload")
    if not isinstance(raw_text, str) or not raw_text.strip():
        return refusal_result(WARNING_PASTED_EMPTY, "No pasted text found in the payload.")

    if len(raw_text) > MAX_PASTED_TEXT_CHARS:
        return refusal_result(
            WARNING_PASTED_TEXT_TOO_LARGE,
            f"The pasted text exceeds the {MAX_PASTED_TEXT_CHARS // 1_000_000} MB limit; split the export into several pastes.",
        )

    entries, duplicate_count = _parse_entries(scrub_sensitive_data(raw_text))
    if not entries:
        return refusal_result(
            WARNING_PASTED_EMPTY,
            "No memory entries were recognized. Use the export prompt and paste the code block it produces.",
        )
    if len(entries) > MAX_PASTED_ENTRIES:
        return refusal_result(
            WARNING_PASTED_ENTRIES_OVER_LIMIT,
            f"The pasted text contains {len(entries)} entries, over the {MAX_PASTED_ENTRIES} limit; "
            "split the export into several pastes.",
        )

    normalized: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        normalized.setdefault(entry.bucket, []).append(_entry_item(entry))

    mappings: list[MemoryImportMappingItem] = []
    mapped_items = 0
    for bucket in (BUCKET_PROFILE, BUCKET_PROCEDURAL, BUCKET_SEMANTIC):
        bucket_items = normalized.get(bucket, [])
        if not bucket_items:
            continue
        mapped_items += len(bucket_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="pasted_entries",
                target_bucket=bucket,
                status="mapped",
                item_count=len(bucket_items),
                imported_count=len(bucket_items),
            ),
        )
    unmapped_items = duplicate_count
    if duplicate_count:
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="duplicate_entries",
                status="dropped",
                item_count=duplicate_count,
                unmapped_count=duplicate_count,
                reason="Repeated entries in the pasted text are imported once.",
            ),
        )

    return build_result(
        source="pasted_memory",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=unmapped_items,
        warnings=[WARNING_PASTED_MODEL_FALLBACK] if payload.get("_model_extraction_failed") else [],
    )


def refusal_result(warning_code: str, reason: str) -> MemoryImportDryRunResult:
    """Return an explicit zero-item refusal with a user-readable reason."""

    return build_result(
        source="pasted_memory",
        version="1",
        normalized={},
        mappings=[
            MemoryImportMappingItem(
                source_bucket="pasted_entries",
                status="unsupported",
                item_count=0,
                reason=reason,
            ),
        ],
        mapped_items=0,
        unmapped_items=0,
        warnings=[warning_code],
    )


def _parse_entries(text: str) -> tuple[list[_ParsedEntry], int]:
    """Parse the pasted text into unique entries plus a duplicate count."""

    entries: list[_ParsedEntry] = []
    seen: set[str] = set()
    duplicate_count = 0
    bucket = BUCKET_SEMANTIC

    for line in _code_block_lines(text):
        heading = _HEADING_PATTERN.match(line)
        if heading:
            resolved = _bucket_for_heading(heading.group("title"))
            if resolved:
                bucket = resolved
            continue

        dated = _DATED_ENTRY_PATTERN.match(line)
        if dated:
            content = dated.group("body").strip()
            parsed_date = _iso_date(
                dated.group("year") or dated.group("year_plain"),
                dated.group("month") or dated.group("month_plain"),
                dated.group("day") or dated.group("day_plain"),
            )
            candidate = _ParsedEntry(content, bucket, parsed_date)
        else:
            bullet = _BULLET_PATTERN.match(line)
            raw = bullet.group("body").strip() if bullet else line.strip()
            if len(raw) < 2:
                continue
            candidate = _ParsedEntry(raw, bucket, None)

        if len(candidate.content) < 2:
            continue
        fingerprint = _fingerprint(candidate.content)
        if fingerprint in seen:
            duplicate_count += 1
            continue
        seen.add(fingerprint)
        entries.append(candidate)

    return entries, duplicate_count


def _code_block_lines(text: str) -> list[str]:
    """Return the first fenced code block's lines, or every line when unfenced."""

    lines = text.splitlines()
    if not any(_FENCE_PATTERN.match(line) for line in lines):
        return lines
    inside = False
    collected: list[str] = []
    for line in lines:
        if _FENCE_PATTERN.match(line):
            inside = not inside
            continue
        if inside:
            collected.append(line)
    return collected or lines


def _bucket_for_heading(raw_title: str) -> str:
    """Map a heading (canonical or localized) to its memory bucket.

    Unknown headings keep the current bucket: the export prompt asks for the
    canonical ASCII headings, so an unrecognized title must not silently move a
    rules section into facts (or the other way around). Returns ``""`` when the
    caller should keep its current bucket.
    """

    title = raw_title.strip().rstrip(":").rstrip("：").strip().lower()
    title = re.sub(r"^\d+[.)]\s*", "", title)
    title = title.strip("*# ").strip()
    title = " ".join(title.split())
    if title in _PROCEDURAL_HEADINGS:
        return BUCKET_PROCEDURAL
    if title in _PROFILE_HEADINGS:
        return BUCKET_PROFILE
    if title in _SEMANTIC_HEADINGS:
        return BUCKET_SEMANTIC
    return ""


def _iso_date(year: str, month: str, day: str) -> str | None:
    """Return ``YYYY-MM-DD`` when the parsed date is real, else ``None``."""

    try:
        parsed = date(int(year), int(month), int(day))
    except ValueError:
        return None
    return parsed.isoformat()


def _fingerprint(content: str) -> str:
    """Stable dedup fingerprint for one entry's normalized text."""

    normalized = " ".join(content.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _entry_item(entry: _ParsedEntry) -> dict[str, object]:
    """Build the native bucket item for one parsed entry."""

    created_at = f"{entry.dated}T00:00:00+00:00" if entry.dated else iso_or_now(None)
    metadata = build_metadata(
        "pasted_memory",
        {"date": entry.dated or "", "bucket": entry.bucket},
        ("date", "bucket"),
    )
    if entry.bucket == BUCKET_PROCEDURAL:
        return {
            "content": entry.content,
            "priority": 5,
            "trigger_keywords": ["pasted_memory"],
            "tags": ["pasted_memory", "rule"],
            "created_at": created_at,
            "metadata": metadata,
        }
    if entry.bucket == BUCKET_PROFILE:
        return {
            "content": entry.content,
            "importance": 0.75,
            "confidence": 0.8,
            "tags": ["pasted_memory", "profile"],
            "created_at": created_at,
            "metadata": metadata,
        }
    return {
        "content": entry.content,
        "importance": 0.7,
        "confidence": 0.75,
        "tags": ["pasted_memory"],
        "created_at": created_at,
        "metadata": metadata,
    }
