"""[INPUT]
- .snapshots::_content_sha256_for_ref (POS: 证据快照哈希)
- wiki.core.structure::WikiStructure (POS: Wiki 文件系统抽象)

[OUTPUT]
- raw 哈希/元数据读写、resource URI 与 raw_supersede 血缘

[POS]
`claims_contract/` 的元数据与资源血缘；只读写 wiki metadata 文件。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from .snapshots import _content_sha256_for_ref, _utc_now_iso

LAST_COMPILE_RAW_HASHES_KEY = "last_compile_raw_hashes"

RAW_SUPERSEDE_KEY = "raw_supersede"

def raw_relative_storage_key(structure: WikiStructure, raw_file: Path) -> str:
    """Return portable raw storage key relative to vault (e.g. raw/notes/budget.md)."""
    rel = raw_file.relative_to(structure.raw_dir).as_posix()
    return f"raw/{rel}"

def sha256_raw_file(raw_file: Path) -> str:
    """Return SHA256 hex digest for a raw file."""
    return hashlib.sha256(raw_file.read_bytes()).hexdigest()

def collect_raw_content_hashes(structure: WikiStructure) -> dict[str, str]:
    """Collect SHA256 digests for all raw markdown files keyed by portable path."""
    hashes: dict[str, str] = {}
    for raw_file in structure.list_raw_files():
        key = raw_relative_storage_key(structure, raw_file)
        try:
            hashes[key] = sha256_raw_file(raw_file)
        except OSError:
            continue
    return hashes

def read_wiki_metadata_file(metadata_path: Path) -> dict[str, object]:
    """Load wiki `.metadata.json` as a mapping."""
    if not metadata_path.exists():
        return {}
    try:
        loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}

def write_wiki_metadata_merge(metadata_path: Path, updates: dict[str, object]) -> None:
    """Merge updates into wiki metadata JSON."""
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    current = read_wiki_metadata_file(metadata_path)
    current.update(updates)
    metadata_path.write_text(json.dumps(current, indent=2), encoding="utf-8")

def get_last_compile_raw_hashes(metadata: dict[str, object]) -> dict[str, str]:
    """Return last-compile raw hash snapshot from metadata."""
    raw = metadata.get(LAST_COMPILE_RAW_HASHES_KEY)
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items() if isinstance(value, str)}

def format_resource_uri(source_path: str, content_sha256: str) -> str:
    """Format portable resource@version URI from path and compile pin digest."""
    path = source_path.strip().replace("\\", "/")
    if path and not path.startswith("raw/"):
        path = f"raw/{path.lstrip('/')}"
    sha = content_sha256.strip()
    if not path or not sha:
        return ""
    return f"{path}@sha256:{sha}"

def normalize_raw_storage_path(source_ref: str) -> str:
    """Normalize evidence path to raw/ relative storage key."""
    cleaned = source_ref.strip().replace("\\", "/")
    if not cleaned:
        return ""
    if cleaned.startswith("raw/"):
        return cleaned
    return f"raw/{cleaned.lstrip('/')}"

def record_raw_supersede_entry(
    structure: WikiStructure,
    *,
    rel_path: str,
    previous_sha256: str,
    new_sha256: str,
    reason: str,
) -> None:
    """Record raw supersede lineage in wiki metadata for citation hints."""
    metadata_path = structure.get_wiki_metadata_path()
    current = read_wiki_metadata_file(metadata_path)
    supersede_raw = current.get(RAW_SUPERSEDE_KEY)
    if not isinstance(supersede_raw, dict):
        supersede_raw = {}
    normalized = normalize_raw_storage_path(rel_path)
    supersede_raw[normalized] = {
        "previous_sha256": previous_sha256,
        "current_sha256": new_sha256,
        "reason": reason,
        "superseded_at": _utc_now_iso(),
    }
    write_wiki_metadata_merge(metadata_path, {RAW_SUPERSEDE_KEY: supersede_raw})

def lookup_raw_supersede_uri(structure: WikiStructure | None, source_ref: str) -> str:
    """Return resource URI for the previous digest when raw was superseded."""
    if structure is None:
        return ""
    metadata = read_wiki_metadata_file(structure.get_wiki_metadata_path())
    supersede_raw = metadata.get(RAW_SUPERSEDE_KEY)
    if not isinstance(supersede_raw, dict):
        return ""
    key = normalize_raw_storage_path(source_ref)
    entry = supersede_raw.get(key)
    if not isinstance(entry, dict):
        return ""
    previous_sha256 = str(entry.get("previous_sha256") or "").strip()
    if not previous_sha256:
        return ""
    return format_resource_uri(key, previous_sha256)

def build_evidence_resource_uri(
    source_path: str,
    pinned_sha256: str,
    *,
    structure: WikiStructure | None = None,
) -> str:
    """Build display URI preferring compile pin, falling back to live raw digest."""
    pinned = pinned_sha256.strip()
    if pinned:
        return format_resource_uri(source_path, pinned)
    live = _content_sha256_for_ref(source_path, structure)
    if live:
        return format_resource_uri(source_path, live)
    return ""
