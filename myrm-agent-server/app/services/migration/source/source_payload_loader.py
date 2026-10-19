"""Load source discovery metadata into adapter-ready payloads.

[INPUT]
Wizard/discovery payload: ``{competitor, root, files}``.

[OUTPUT]
Adapter-ready dict (``soul_md``, ``openclaw_sessions``, ``memory_md``, ``conversations``, etc.).

[POS]
Local/Tauri-only bridge between filesystem discovery and memory import adapters.
Public API: load_source_payload, build_coverage_items, extract_pending_skills.
Loaders: hermes/claude/codex/chatgpt/gbrain/plur in source_payload_loaders_impl.py;
openclaw in _loaders_openclaw.py; pi in _loaders_pi.py.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import TypedDict

from app.config.deploy_mode import is_local_mode

from .source_payload_loaders_impl import (
    load_chatgpt,
    load_claude,
    load_codex,
    load_gbrain,
    load_hermes,
    load_openclaw,
    load_pi,
    load_plur,
)

MIGRATION_UPLOAD_DIR_PREFIX = "myrm_migration_"
MIGRATION_UPLOAD_TTL_SECONDS = 6 * 3600
# Skill bundles travel to the client and back (the wizard submits them to the
# skill review pipeline), so the review payload is capped; the response reports
# the real total so the UI can say how many were left out.
MAX_PENDING_SKILLS = 500


class MigrationSourceAccessError(ValueError):
    """Raised when a discovery payload asks for a path the deployment forbids."""


class SourceDiscoveryPayload(TypedDict, total=False):
    competitor: str
    root: str
    files: list[str]


def is_source_discovery_payload(payload: dict[str, object]) -> bool:
    """Return True when payload is a discovery stub rather than parsed export data."""

    competitor = payload.get("competitor")
    return isinstance(competitor, str) and bool(competitor.strip())


def load_source_payload(payload: dict[str, object]) -> dict[str, object]:
    """Read competitor files from disk and return an adapter-ready payload.

    Sandbox deployments may only read inside a migration ZIP extraction
    directory (``myrm_migration_*`` under the system temp root): the archive is
    the user's own upload, while any other host path stays off limits, and
    client-provided ``files`` paths are dropped unless they resolve inside that
    directory. Local and Tauri deployments keep unrestricted reads because the
    user owns the machine.
    """

    competitor = str(payload.get("competitor", "")).strip().lower()
    root_raw = payload.get("root")
    root = Path(str(root_raw)) if isinstance(root_raw, str) and root_raw else Path()
    sandbox_upload = not is_local_mode()
    if sandbox_upload and not is_migration_upload_path(root):
        msg = "External source files can only be read from the archive uploaded in this session"
        raise MigrationSourceAccessError(msg)

    files_raw = payload.get("files")
    file_paths = [str(item) for item in files_raw if isinstance(item, str)] if isinstance(files_raw, list) else []
    if sandbox_upload:
        file_paths = _keep_upload_contained_paths(file_paths, root)

    loaders = {
        "hermes": load_hermes,
        "openclaw": load_openclaw,
        "codex": load_codex,
        "claude": load_claude,
        "chatgpt": load_chatgpt,
        "gbrain": load_gbrain,
        "pi": load_pi,
        "plur": load_plur,
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
        "claude_md",
        "codex_instructions",
        "cursor_rules",
    )
    memory_keys = (
        "memory_md",
        "user_md",
        "openclaw_sessions",
        "openclaw_memory",
        "pi_sessions",
        "semantic",
        "codex_memory",
        "conversations",
        "engrams",
    )

    if any(loaded_payload.get(key) for key in instruction_keys):
        rows.append({"key": "instruction", "status": "ready", "label": "instruction_lane"})
    if any(loaded_payload.get(key) for key in memory_keys):
        rows.append({"key": "memory", "status": "ready", "label": "memory_lane"})

    session_keys = ("sessions", "claude_sessions", "codex_sessions", "openclaw_sessions", "pi_sessions")
    if any(loaded_payload.get(key) for key in session_keys):
        rows.append({"key": "session", "status": "ready", "label": "session_lane"})

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

    source = str(loaded_payload.get("_source", "")).strip().lower()
    if source == "hermes":
        rows.append({"key": "kanban", "status": "manual", "label": "kanban_not_migrated"})
        cron_plan_raw = loaded_payload.get("hermes_cron_plan")
        cron_importable = 0
        if isinstance(cron_plan_raw, dict):
            importable_raw = cron_plan_raw.get("importable")
            if isinstance(importable_raw, list):
                cron_importable = len(importable_raw)
        if cron_importable > 0:
            rows.append({"key": "cron", "status": "ready", "label": "cron_lane"})
        else:
            rows.append({"key": "cron", "status": "missing", "label": "cron_lane"})
        if loaded_payload.get("credential_pool") or loaded_payload.get("hermes_auth"):
            rows.append({"key": "credential_pool", "status": "ready", "label": "credential_pool_migration"})

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


def is_migration_upload_path(path: Path) -> bool:
    """True when ``path`` lives inside a migration ZIP extraction directory."""

    try:
        resolved = path.resolve()
    except OSError:
        return False
    temp_root = Path(tempfile.gettempdir()).resolve()
    for candidate in (resolved, *resolved.parents):
        if not candidate.name.startswith(MIGRATION_UPLOAD_DIR_PREFIX):
            continue
        try:
            candidate.relative_to(temp_root)
        except ValueError:
            continue
        return True
    return False


def sweep_stale_migration_uploads(*, now: float | None = None) -> int:
    """Delete expired migration extraction directories and return how many went.

    The review session keeps its extraction directory readable for the whole
    dry-run window, so the TTL is far larger than a session's lifetime; anything
    older than that belongs to an abandoned upload and only occupies disk.
    """

    temp_root = Path(tempfile.gettempdir()).resolve()
    cutoff = (time.time() if now is None else now) - MIGRATION_UPLOAD_TTL_SECONDS
    try:
        entries = list(temp_root.iterdir())
    except OSError:
        return 0
    removed = 0
    for entry in entries:
        if not entry.name.startswith(MIGRATION_UPLOAD_DIR_PREFIX) or entry.is_symlink():
            continue
        if not entry.is_dir():
            continue
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
        except OSError:
            continue
        shutil.rmtree(entry, ignore_errors=True)
        removed += 1
    return removed


def _keep_upload_contained_paths(file_paths: list[str], root: Path) -> list[str]:
    """Drop discovery file paths that escape the uploaded archive directory.

    ``files`` arrives from the client, and the loaders read those paths as-is,
    so a sandbox request could otherwise name any host file whose basename looks
    like a known asset (``.env``, ``MEMORY.md``, ...). Only paths inside the
    validated upload root survive.
    """

    try:
        resolved_root = root.resolve()
    except OSError:
        return []
    contained: list[str] = []
    for raw in file_paths:
        try:
            Path(raw).resolve().relative_to(resolved_root)
        except (OSError, ValueError):
            continue
        contained.append(raw)
    return contained
