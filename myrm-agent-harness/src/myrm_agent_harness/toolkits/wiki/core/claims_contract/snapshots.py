"""[INPUT]
- .models::WikiClaim / WikiEvidence (POS: claim/evidence 模型)
- .parsing (POS: claim 解析与合并)
- wiki.core.structure::WikiStructure (POS: Wiki 文件系统抽象)

[OUTPUT]
- 证据摘录/快照/哈希、原始字节 LRU、编译前置与证据修复

[POS]
`claims_contract/` 的证据快照阶段；负责 raw 文件读取与 LRU 缓存。
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from .models import (
    MAX_EVIDENCE_EXCERPT_CHARS,
    RAW_BYTES_LRU_MAX_BYTES,
    EvidenceSnapshotStatus,
    WikiClaim,
    WikiEvidence,
)
from .parsing import (
    _build_fallback_claims,
    merge_claims_into_content,
    parse_claims_from_content,
    validate_compile_claims,
)


@dataclass(frozen=True, slots=True)
class _RawBytesLruEntry:
    mtime_ns: int
    raw: bytes

_RAW_BYTES_LRU: OrderedDict[str, _RawBytesLruEntry] = OrderedDict()

_RAW_BYTES_LRU_TOTAL_BYTES = 0

def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()

def _resolve_raw_file(structure: WikiStructure, source_ref: str) -> Path | None:
    cleaned = source_ref.strip().replace("\\", "/").removeprefix("raw/")
    if not cleaned:
        return None
    candidates = (
        structure.get_raw_file_path(cleaned),
        structure.get_raw_file_path(Path(cleaned).name),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None

def _parse_evidence_line_range(lines: str) -> tuple[int | None, int | None]:
    cleaned = lines.strip()
    if not cleaned:
        return None, None
    if "-" in cleaned:
        start_part, _, end_part = cleaned.partition("-")
        start_text = start_part.strip()
        end_text = end_part.strip()
        start = int(start_text) if start_text.isdigit() else None
        end = int(end_text) if end_text.isdigit() else None
        return start, end
    if cleaned.isdigit():
        line_no = int(cleaned)
        return line_no, line_no
    return None, None

def _normalize_source_ref(source_ref: str) -> str:
    return source_ref.strip().replace("\\", "/")

def clear_raw_bytes_lru_cache() -> None:
    """Clear the process-wide raw bytes LRU cache (for tests)."""
    _RAW_BYTES_LRU.clear()
    global _RAW_BYTES_LRU_TOTAL_BYTES
    _RAW_BYTES_LRU_TOTAL_BYTES = 0

def _store_raw_bytes_lru(cache_key: str, mtime_ns: int, raw: bytes) -> None:
    global _RAW_BYTES_LRU_TOTAL_BYTES
    existing = _RAW_BYTES_LRU.pop(cache_key, None)
    if existing is not None:
        _RAW_BYTES_LRU_TOTAL_BYTES -= len(existing.raw)
    _RAW_BYTES_LRU[cache_key] = _RawBytesLruEntry(mtime_ns=mtime_ns, raw=raw)
    _RAW_BYTES_LRU_TOTAL_BYTES += len(raw)
    while _RAW_BYTES_LRU and _RAW_BYTES_LRU_TOTAL_BYTES > RAW_BYTES_LRU_MAX_BYTES:
        _, evicted = _RAW_BYTES_LRU.popitem(last=False)
        _RAW_BYTES_LRU_TOTAL_BYTES -= len(evicted.raw)

def _load_raw_bytes(
    source_ref: str,
    structure: WikiStructure | None,
    *,
    cache: dict[str, bytes] | None = None,
) -> bytes:
    if structure is None or not source_ref.strip():
        return b""
    normalized = _normalize_source_ref(source_ref)
    if Path(normalized).is_absolute():
        return b""
    path = _resolve_raw_file(structure, source_ref)
    if path is None:
        return b""
    cache_key = str(path.resolve())
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return b""
    lru_entry = _RAW_BYTES_LRU.get(cache_key)
    if lru_entry is not None and lru_entry.mtime_ns == mtime_ns:
        _RAW_BYTES_LRU.move_to_end(cache_key)
        raw = lru_entry.raw
    else:
        try:
            raw = path.read_bytes()
        except OSError:
            return b""
        _store_raw_bytes_lru(cache_key, mtime_ns, raw)
    if cache is not None:
        cache[cache_key] = raw
    return raw

def _digest_raw_bytes(raw: bytes) -> str:
    if not raw:
        return ""
    return hashlib.sha256(raw).hexdigest()

def _decode_raw_text(raw: bytes) -> str:
    if not raw:
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""

def _slice_excerpt_from_text(text: str, lines: str, max_chars: int) -> str:
    start, end = _parse_evidence_line_range(lines)
    if start is None:
        return ""
    file_lines = text.splitlines()
    start_idx = max(start - 1, 0)
    if end is None:
        selected = file_lines[start_idx:]
    else:
        end_idx = min(max(end, start), len(file_lines))
        selected = file_lines[start_idx:end_idx]
    excerpt = "\n".join(selected).strip()
    if not excerpt:
        return ""
    if len(excerpt) > max_chars:
        return excerpt[:max_chars].rstrip() + "…"
    return excerpt

def read_evidence_excerpt(
    source_ref: str,
    lines: str,
    structure: WikiStructure | None,
    *,
    max_chars: int = MAX_EVIDENCE_EXCERPT_CHARS,
) -> str:
    """Read a bounded excerpt from a raw evidence file using 1-based line ranges."""
    raw = _load_raw_bytes(source_ref, structure)
    text = _decode_raw_text(raw)
    if not text:
        return ""
    return _slice_excerpt_from_text(text, lines, max_chars)

def _content_sha256_for_ref(
    source_ref: str,
    structure: WikiStructure | None,
    *,
    cache: dict[str, bytes] | None = None,
) -> str:
    if structure is None or not source_ref.strip():
        return ""
    if Path(source_ref.strip()).is_absolute():
        return ""
    return _digest_raw_bytes(_load_raw_bytes(source_ref, structure, cache=cache))

def resolve_evidence_snapshot_and_excerpt(
    source_ref: str,
    lines: str,
    pinned_sha256: str,
    structure: WikiStructure | None,
    *,
    cache: dict[str, bytes] | None = None,
    max_chars: int = MAX_EVIDENCE_EXCERPT_CHARS,
) -> tuple[EvidenceSnapshotStatus, str]:
    """Resolve compile snapshot status and raw excerpt from a single raw file read."""
    pinned = pinned_sha256.strip()
    raw = _load_raw_bytes(source_ref, structure, cache=cache)
    digest = _digest_raw_bytes(raw)
    text = _decode_raw_text(raw)
    excerpt = _slice_excerpt_from_text(text, lines, max_chars) if text else ""

    if not pinned:
        status: EvidenceSnapshotStatus = "missing"
    elif not digest:
        status = "missing"
    elif digest == pinned:
        status = "verified"
    else:
        status = "stale"
    return status, excerpt

def resolve_evidence_snapshot_status(
    source_ref: str,
    pinned_sha256: str,
    structure: WikiStructure | None,
) -> EvidenceSnapshotStatus:
    """Compare pinned compile snapshot against the current raw file digest."""
    pinned = pinned_sha256.strip()
    if not pinned:
        return "missing"
    current = _content_sha256_for_ref(source_ref, structure)
    if not current:
        return "missing"
    if current == pinned:
        return "verified"
    return "stale"

def _pin_claims_with_source_snapshots(
    claims: tuple[WikiClaim, ...],
    structure: WikiStructure | None,
    stamped_at: str,
) -> tuple[WikiClaim, ...]:
    if not claims:
        return claims
    pinned: list[WikiClaim] = []
    for claim in claims:
        evidence_items: list[WikiEvidence] = []
        for evidence in claim.evidence:
            content_sha256 = evidence.content_sha256 or _content_sha256_for_ref(evidence.path, structure)
            evidence_items.append(
                replace(
                    evidence,
                    content_sha256=content_sha256,
                    updated_at=evidence.updated_at or (stamped_at if content_sha256 else ""),
                )
            )
        pinned.append(
            replace(
                claim,
                evidence=tuple(evidence_items),
                updated_at=claim.updated_at or stamped_at,
            )
        )
    return tuple(pinned)

def ensure_compile_claims(
    content: str,
    concept_name: str,
    source_files: list[str],
    *,
    structure: WikiStructure | None = None,
) -> str:
    """Ensure compiled concept content includes valid structured claims frontmatter."""
    stamped_at = _utc_now_iso()
    parsed = parse_claims_from_content(content)
    if validate_compile_claims(parsed):
        claims = parsed
    else:
        claims = _build_fallback_claims(content, concept_name, source_files)
    claims = _pin_claims_with_source_snapshots(claims, structure, stamped_at)
    return merge_claims_into_content(content, claims)

def heal_claim_evidence_snapshot(
    concept_name: str,
    structure: WikiStructure,
) -> tuple[bool, int]:
    """Auto-heal shifted line ranges and update content_sha256 for a concept's claims.

    When the referenced raw source file is modified externally, the line numbers
    may drift. This function attempts to fuzzy-locate the original claim text / note
    in the raw file, recalculates the line range, updates content_sha256 to the current
    file hash, and persists the healed claims back to concept frontmatter.

    Returns:
        (healed, count): Whether any claim evidence was updated, and the number of healed items.
    """
    article_path = structure.get_concept_file_path(concept_name)
    if not article_path.is_file():
        return False, 0

    try:
        content = article_path.read_text(encoding="utf-8")
    except OSError:
        return False, 0

    claims = parse_claims_from_content(content)
    if not claims:
        return False, 0

    now_iso = _utc_now_iso()
    healed_count = 0
    updated_claims: list[WikiClaim] = []

    for claim in claims:
        new_evidence: list[WikiEvidence] = []
        claim_changed = False
        for ev in claim.evidence:
            if not ev.path.strip():
                new_evidence.append(ev)
                continue

            raw = _load_raw_bytes(ev.path, structure)
            if not raw:
                new_evidence.append(ev)
                continue

            current_digest = _digest_raw_bytes(raw)
            if ev.content_sha256 and ev.content_sha256 == current_digest:
                # Already up to date
                new_evidence.append(ev)
                continue

            # Need healing: raw file digest changed
            raw_text = _decode_raw_text(raw)
            file_lines = raw_text.splitlines()
            old_start, old_end = _parse_evidence_line_range(ev.lines)
            healed_lines = ev.lines

            # Search target: use claim.text or ev.note
            search_needle = claim.text.strip()
            if len(search_needle) > 40:
                search_needle = search_needle[:40]

            if search_needle and file_lines:
                # Attempt to find best matching line in file
                best_line_idx: int | None = None
                for idx, line in enumerate(file_lines):
                    if search_needle in line:
                        best_line_idx = idx
                        break

                if best_line_idx is not None:
                    span = 1
                    if old_start is not None and old_end is not None:
                        span = max(1, old_end - old_start + 1)
                    new_start = best_line_idx + 1
                    new_end = min(len(file_lines), new_start + span - 1)
                    if "-" in ev.lines:
                        healed_lines = f"{new_start}-{new_end}"
                    else:
                        healed_lines = f"{new_start}-{new_end}" if new_end > new_start else str(new_start)

            healed_ev = replace(
                ev,
                lines=healed_lines,
                content_sha256=current_digest,
                updated_at=now_iso,
            )
            new_evidence.append(healed_ev)
            healed_count += 1
            claim_changed = True

        if claim_changed:
            updated_claims.append(
                replace(
                    claim,
                    evidence=tuple(new_evidence),
                    updated_at=now_iso,
                )
            )
        else:
            updated_claims.append(claim)

    if healed_count > 0:
        new_content = merge_claims_into_content(content, tuple(updated_claims))
        try:
            article_path.write_text(new_content, encoding="utf-8")
            return True, healed_count
        except OSError:
            return False, 0

    return False, 0
