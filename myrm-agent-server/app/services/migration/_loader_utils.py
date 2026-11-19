"""Shared utilities for competitor payload loaders.

[INPUT]
Path objects and raw file content from competitor data directories.

[OUTPUT]
Parsed text/JSON/YAML, path lookups, env key names, skill directory scanning.

[POS]
Shared module used by source_payload_loaders_impl.py, _loaders_openclaw.py, and _loaders_pi.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from app.services.migration.env_secrets import KEY_FROM_ENV, read_env_keys

_MEMORY_BULLET_PATTERN = re.compile(r"^[-*]\s+(.+)$", re.MULTILINE)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def read_yaml(path: Path) -> object | None:
    try:
        parsed: object | None = yaml.safe_load(read_text(path))
    except Exception:
        return None
    return parsed


def read_json(path: Path) -> object | None:
    try:
        parsed: object | None = json.loads(read_text(path))
    except (json.JSONDecodeError, OSError):
        return None
    return parsed


def path_by_kind(file_paths: list[str], kind: str) -> Path | None:
    for raw in file_paths:
        path = Path(raw)
        if path.name.lower() == kind.lower() or path.stem.lower() == kind.lower():
            return path
    return None


def find_file(root: Path, *relative_parts: str) -> Path | None:
    candidate = root.joinpath(*relative_parts)
    return candidate if candidate.is_file() else None


def extract_env_key_names(env_path: Path) -> list[dict[str, str]]:
    """The names of the provider keys a ``.env`` holds that the import reads, by the grammar and list it uses."""
    return [{"name": name, "source": KEY_FROM_ENV} for name in read_env_keys(env_path).importable]


def load_skill_directories(skills_dir: Path, *, source: str) -> list[dict[str, object]]:
    skills: list[dict[str, object]] = []
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            continue
        skills.append(
            {
                "name": entry.name,
                "content": read_text(skill_md),
                "path": str(entry),
                "source": source,
            },
        )
    return skills


def load_usage_sidecar(skills_dir: Path) -> dict[str, dict[str, object]]:
    """Read Hermes-style .usage.json sidecar from a skills directory.

    Returns a mapping of {skill_name: usage_record} where usage_record
    contains use_count, last_used_at, created_at, state, pinned, etc.
    Best-effort: returns empty dict on missing or corrupt file.
    """
    usage_path = skills_dir / ".usage.json"
    if not usage_path.is_file():
        return {}
    data = read_json(usage_path)
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def markdown_bullets_to_memory(content: str, *, category: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for match in _MEMORY_BULLET_PATTERN.finditer(content):
        text = match.group(1).strip()
        if text:
            entries.append({"content": text, "type": category, "category": category})
    stripped = content.strip()
    if not entries and stripped:
        entries.append({"content": stripped, "type": category, "category": category})
    return entries


def serialize_transcript(parsed: object) -> dict[str, object]:
    from myrm_agent_harness.runtime.context.transcripts import TranscriptParseResult

    if not isinstance(parsed, TranscriptParseResult):
        return {}
    return {
        "session_id": parsed.session_id,
        "title": parsed.title,
        "source_platform": parsed.source_platform,
        "created_at": parsed.created_at,
        "updated_at": parsed.updated_at,
        "detected_workspace_hint": parsed.detected_workspace_hint,
        "total_tool_calls": parsed.total_tool_calls,
        "total_tokens_approx": parsed.total_tokens_approx,
        "turns": [
            {
                "turn_id": t.turn_id,
                "role": t.role.value,
                "content": t.content,
                "thinking_trace": t.thinking_trace,
                "timestamp": t.timestamp,
                "source_event_type": t.source_event_type,
                "tool_calls": [
                    {
                        "call_id": tc.call_id,
                        "tool_name": tc.tool_name,
                        "arguments": tc.arguments,
                        "output": tc.output,
                        "exit_code": tc.exit_code,
                        "is_error": tc.is_error,
                        "compacted": tc.compacted,
                        "original_size_bytes": tc.original_size_bytes,
                    }
                    for tc in t.tool_calls
                ],
            }
            for t in parsed.turns
        ],
    }
