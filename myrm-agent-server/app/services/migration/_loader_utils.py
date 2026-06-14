"""Shared utilities for competitor payload loaders.

[INPUT]
Path objects and raw file content from competitor data directories.

[OUTPUT]
Parsed text/JSON/YAML, path lookups, env key extraction, skill directory scanning.

[POS]
Shared module used by competitor_payload_loaders_impl.py and _loaders_openclaw_qwenpaw.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

_MEMORY_BULLET_PATTERN = re.compile(r"^[-*]\s+(.+)$", re.MULTILINE)

_ENV_API_KEY_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "XAI_API_KEY",
    "MISTRAL_API_KEY",
    "DEEPSEEK_API_KEY",
)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def read_yaml(path: Path) -> object | None:
    try:
        content = read_text(path)
        return yaml.safe_load(content)
    except Exception:
        return None


def read_json(path: Path) -> object | None:
    try:
        return json.loads(read_text(path))
    except (json.JSONDecodeError, OSError):
        return None


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
    content = read_text(env_path)
    keys: list[dict[str, str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in _ENV_API_KEY_NAMES:
            keys.append({"name": key})
    return keys


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
