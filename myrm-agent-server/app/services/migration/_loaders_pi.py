"""Pi payload loader implementation.

[INPUT]
Path root + file_paths from discovery (Pi agent directory: ~/.pi/agent/).

[OUTPUT]
Adapter-ready dict with agents_md, pi_settings, pi_sessions, skills, env_keys.

[POS]
Pi loader handling AGENTS.md, settings.json, auth.json, sessions/*.jsonl, skills/.
Pi uses JSONL session format (version 3 header) distinct from OpenClaw's JSON.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ._loader_utils import (
    find_file,
    load_skill_directories,
    path_by_kind,
    read_json,
    read_text,
)

logger = logging.getLogger(__name__)

_SUPPORTED_SESSION_VERSIONS = frozenset({3})

_PI_AUTH_KEY_PROVIDERS = frozenset(
    {
        "anthropic",
        "openai",
        "google",
        "groq",
        "xai",
        "mistral",
        "deepseek",
        "openrouter",
    }
)


def load_pi(root: Path, file_paths: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}

    agents_path = path_by_kind(file_paths, "AGENTS.md") or find_file(root, "AGENTS.md")
    if agents_path:
        result["agents_md"] = read_text(agents_path)

    settings_path = path_by_kind(file_paths, "settings.json") or find_file(root, "settings.json")
    if settings_path:
        settings_data = read_json(settings_path)
        if isinstance(settings_data, dict):
            result["pi_settings"] = settings_data

    auth_path = path_by_kind(file_paths, "auth.json") or find_file(root, "auth.json")
    if auth_path:
        env_keys = _extract_pi_auth_keys(auth_path)
        if env_keys:
            result["env_keys"] = env_keys

    sessions_dir = root / "sessions"
    if sessions_dir.is_dir():
        sessions = _load_pi_sessions(sessions_dir)
        if sessions:
            result["pi_sessions"] = sessions

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        skills = load_skill_directories(skills_dir, source="pi")
        if skills:
            result["skills"] = skills

    return result


def _extract_pi_auth_keys(auth_path: Path) -> list[dict[str, str]]:
    """Extract provider names from Pi's auth.json as env_keys for the credentials lane."""
    data = read_json(auth_path)
    if not isinstance(data, dict):
        return []
    keys: list[dict[str, str]] = []
    for provider_id in sorted(data):
        normalized = provider_id.strip().lower()
        if normalized in _PI_AUTH_KEY_PROVIDERS:
            keys.append({"name": f"{normalized.upper()}_API_KEY"})
    return keys


def _load_pi_sessions(sessions_dir: Path) -> list[dict[str, object]]:
    """Parse Pi JSONL session files into summary dicts for the memory lane."""
    sessions: list[dict[str, object]] = []
    jsonl_files = sorted(
        (f for f in sessions_dir.iterdir() if f.suffix == ".jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for jsonl_path in jsonl_files:
        session = _parse_pi_session_file(jsonl_path)
        if session is not None:
            sessions.append(session)

    return sessions


def _parse_pi_session_file(jsonl_path: Path) -> dict[str, object] | None:
    """Parse a single Pi .jsonl session file into a summary dict."""
    try:
        content = jsonl_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return None

    try:
        header = json.loads(lines[0])
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(header, dict) or header.get("type") != "session":
        return None

    version = header.get("version")
    if isinstance(version, int) and version not in _SUPPORTED_SESSION_VERSIONS:
        logger.warning("Pi session %s has unsupported version %d, skipping", jsonl_path.name, version)
        return None

    messages: list[dict[str, str]] = []
    for line in lines[1:]:
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(entry, dict) or entry.get("type") != "message":
            continue
        msg = entry.get("message")
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", ""))
        msg_content = msg.get("content", "")
        if isinstance(msg_content, list):
            text_parts = [
                str(block.get("text", "")) for block in msg_content if isinstance(block, dict) and block.get("type") == "text"
            ]
            msg_content = "\n".join(text_parts)
        if not isinstance(msg_content, str):
            msg_content = str(msg_content)
        if role and msg_content.strip():
            messages.append({"role": role, "content": msg_content.strip()})

    if not messages:
        return None

    return {
        "id": str(header.get("id", jsonl_path.stem)),
        "timestamp": str(header.get("timestamp", "")),
        "cwd": str(header.get("cwd", "")),
        "message_count": len(messages),
        "messages": messages,
    }
