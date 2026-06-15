"""Load source discovery metadata into adapter-ready payloads.

[INPUT]
Wizard/discovery payload: ``{competitor, root, files}``.

[OUTPUT]
Adapter-ready dict (``soul_md``, ``openclaw_sessions``, ``memory_md``, etc.).

[POS]
Local/Tauri-only bridge between filesystem discovery and memory import adapters.
Public API: load_source_payload, build_coverage_items, extract_pending_skills.
Loaders: hermes/claude/codex in source_payload_loaders_impl.py; openclaw in _loaders_openclaw.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from app.config.deploy_mode import is_local_mode

from .source_payload_loaders_impl import (
    load_claude,
    load_codex,
    load_hermes,
    load_openclaw,
)

_SUPPORTED_SOURCES = frozenset({"hermes", "openclaw", "claude", "codex"})


class SourceDiscoveryPayload(TypedDict, total=False):
    competitor: str
    root: str
    files: list[str]


def is_source_discovery_payload(payload: dict[str, object]) -> bool:
    """Return True when payload is a discovery stub rather than parsed export data."""

    competitor = payload.get("competitor")
    return isinstance(competitor, str) and bool(competitor.strip())


def load_source_payload(payload: dict[str, object]) -> dict[str, object]:
    """Read competitor files from disk and return an adapter-ready payload."""

    if not is_local_mode():
        msg = "External source payload loading requires local or Tauri deployment mode"
        raise ValueError(msg)

    competitor = str(payload.get("competitor", "")).strip().lower()
    root_raw = payload.get("root")
    root = Path(str(root_raw)) if isinstance(root_raw, str) and root_raw else Path()
    files_raw = payload.get("files")
    file_paths = [str(item) for item in files_raw if isinstance(item, str)] if isinstance(files_raw, list) else []

    loaders = {
        "hermes": load_hermes,
        "openclaw": load_openclaw,
        "codex": load_codex,
        "claude": load_claude,
    }
    loader = loaders.get(competitor)
    if loader is None:
        return {"_source": competitor, "_load_error": f"Unsupported competitor: {competitor}"}

    loaded = loader(root, file_paths)
    loaded["_source"] = competitor
    loaded["_discovery_root"] = str(root)
    return loaded


def build_coverage_items(loaded_payload: dict[str, object]) -> list[dict[str, str]]:
    """Build UI coverage matrix rows aligned with four migration lanes."""

    rows: list[dict[str, str]] = []
    instruction_keys = (
        "soul_md",
        "agents_md",
        "codex_instructions",
        "cursor_rules",
        "semantic",
    )
    memory_keys = ("memory_md", "user_md", "openclaw_sessions", "openclaw_memory")

    if any(loaded_payload.get(key) for key in instruction_keys):
        rows.append({"key": "instruction", "status": "ready", "label": "instruction_lane"})
    if any(loaded_payload.get(key) for key in memory_keys):
        rows.append({"key": "memory", "status": "ready", "label": "memory_lane"})

    skills = extract_pending_skills(loaded_payload)
    if skills:
        rows.append({"key": "skills", "status": "review", "label": "skills_review"})

    env_keys = loaded_payload.get("env_keys")
    if isinstance(env_keys, list) and env_keys:
        rows.append({"key": "api_keys", "status": "manual", "label": "api_keys_manual"})

    mcp_servers = loaded_payload.get("mcp_servers")
    if isinstance(mcp_servers, dict) and mcp_servers:
        rows.append({"key": "mcp", "status": "ready", "label": "mcp_ready"})
    else:
        rows.append({"key": "mcp", "status": "manual", "label": "mcp_manual"})
    rows.append({"key": "channels", "status": "manual", "label": "channels_manual"})

    if loaded_payload.get("_load_error"):
        rows.append({"key": "load_error", "status": "missing", "label": "no_importable_data"})
    elif not rows:
        rows.append({"key": "empty", "status": "missing", "label": "no_importable_data"})

    return rows


def extract_pending_skills(payload: dict[str, object]) -> list[dict[str, object]]:
    """Return skill bundles staged for the skill migration review pipeline."""

    hermes_skills = payload.get("skills")
    if isinstance(hermes_skills, list):
        return [item for item in hermes_skills if isinstance(item, dict)]

    openclaw_skills = payload.get("openclaw_skills")
    if isinstance(openclaw_skills, list):
        return [item for item in openclaw_skills if isinstance(item, dict)]

    return []


def supported_source_ids() -> frozenset[str]:
    """Return the closed set of wizard-discoverable migration source ids."""

    return _SUPPORTED_SOURCES
