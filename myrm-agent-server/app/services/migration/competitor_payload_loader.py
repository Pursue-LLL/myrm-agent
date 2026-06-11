"""Load competitor discovery metadata into adapter-ready payloads.

[INPUT]
Wizard/discovery payload: ``{competitor, root, files}``.

[OUTPUT]
Adapter-ready dict (``soul_md``, ``openclaw_sessions``, ``cursor_rules``, etc.).

[POS]
Local/Tauri-only bridge between filesystem discovery and memory import adapters.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict

import yaml

from app.config.deploy_mode import is_local_mode

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


class CompetitorDiscoveryPayload(TypedDict, total=False):
    competitor: str
    root: str
    files: list[str]


def is_competitor_discovery_payload(payload: dict[str, object]) -> bool:
    """Return True when payload is a discovery stub rather than parsed export data."""

    competitor = payload.get("competitor")
    return isinstance(competitor, str) and bool(competitor.strip())


def load_competitor_payload(payload: dict[str, object]) -> dict[str, object]:
    """Read competitor files from disk and return an adapter-ready payload."""

    if not is_local_mode():
        msg = "Competitor payload loading requires local or Tauri deployment mode"
        raise ValueError(msg)

    competitor = str(payload.get("competitor", "")).strip().lower()
    root_raw = payload.get("root")
    root = Path(str(root_raw)) if isinstance(root_raw, str) and root_raw else Path()
    files_raw = payload.get("files")
    file_paths = [str(item) for item in files_raw if isinstance(item, str)] if isinstance(files_raw, list) else []

    loaders = {
        "hermes": _load_hermes,
        "openclaw": _load_openclaw,
        "cursor": _load_cursor,
        "codex": _load_codex,
        "claude": _load_claude,
        "windsurf": _load_windsurf,
        "trae": _load_trae,
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


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _read_yaml(path: Path) -> object | None:
    try:
        content = _read_text(path)
        return yaml.safe_load(content)
    except Exception:
        return None


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(_read_text(path))
    except (json.JSONDecodeError, OSError):
        return None


def _path_by_kind(file_paths: list[str], kind: str) -> Path | None:
    for raw in file_paths:
        path = Path(raw)
        if path.name.lower() == kind.lower() or path.stem.lower() == kind.lower():
            return path
    return None


def _find_file(root: Path, *relative_parts: str) -> Path | None:
    candidate = root.joinpath(*relative_parts)
    return candidate if candidate.is_file() else None


def _load_hermes(root: Path, file_paths: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}

    soul_path = _path_by_kind(file_paths, "SOUL.md") or _find_file(root, "SOUL.md")
    if soul_path:
        result["soul_md"] = _read_text(soul_path)

    memory_path = _path_by_kind(file_paths, "MEMORY.md") or _find_file(root, "memories", "MEMORY.md")
    if memory_path:
        result["memory_md"] = _read_text(memory_path)

    user_path = _path_by_kind(file_paths, "USER.md") or _find_file(root, "memories", "USER.md")
    if user_path:
        result["user_md"] = _read_text(user_path)

    agents_path = _path_by_kind(file_paths, "AGENTS.md") or _find_file(root, "AGENTS.md")
    if agents_path:
        result["agents_md"] = _read_text(agents_path)

    env_path = _path_by_kind(file_paths, ".env") or _find_file(root, ".env")
    if env_path:
        result["env_keys"] = _extract_env_key_names(env_path)

    config_path = _path_by_kind(file_paths, "config.yaml") or _find_file(root, "config.yaml")
    if config_path:
        config_data = _read_yaml(config_path)
        if isinstance(config_data, dict):
            result["hermes_config"] = config_data

            # Extract MCP configurations
            mcp_servers = config_data.get("mcp_servers") or config_data.get("mcp")
            if isinstance(mcp_servers, dict) and mcp_servers:
                result["mcp_servers"] = mcp_servers

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        skills = _load_skill_directories(skills_dir, source="hermes")
        if skills:
            result["skills"] = skills

    return result


def _load_openclaw(root: Path, file_paths: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}

    sessions_path = _path_by_kind(file_paths, "sessions.json") or _find_file(root, "sessions.json")
    if sessions_path:
        sessions_data = _read_json(sessions_path)
        sessions = _normalize_openclaw_sessions(sessions_data)
        if sessions:
            result["openclaw_sessions"] = sessions

    memory_path = _path_by_kind(file_paths, "memory.json") or _find_file(root, "memory.json")
    if memory_path:
        memory_data = _read_json(memory_path)
        entries = _normalize_openclaw_memory(memory_data)
        if entries:
            result["openclaw_memory"] = entries

    config_path = _path_by_kind(file_paths, "config.json") or _find_file(root, "config.json")
    if config_path:
        config_data = _read_json(config_path)
        if isinstance(config_data, dict):
            result["openclaw_config"] = config_data
            mcp_servers = config_data.get("mcp_servers") or config_data.get("mcp")
            if isinstance(mcp_servers, dict) and mcp_servers:
                result["mcp_servers"] = mcp_servers

    for md_name, key in (("MEMORY.md", "memory_md"), ("USER.md", "user_md"), ("SOUL.md", "soul_md")):
        md_path = _path_by_kind(file_paths, md_name)
        if md_path is not None and md_path.is_file():
            text = _read_text(md_path).strip()
        else:
            text = _collect_openclaw_workspace_text(root, md_name)
        if text:
            result[key] = text

    _merge_openclaw_markdown_into_memory(result)

    config_path = _path_by_kind(file_paths, "config.yaml") or _find_file(root, "config.yaml")
    if config_path:
        config_data = _read_yaml(config_path)
        if isinstance(config_data, dict):
            result["hermes_config"] = config_data

            # Extract MCP configurations
            mcp_servers = config_data.get("mcp_servers") or config_data.get("mcp")
            if isinstance(mcp_servers, dict) and mcp_servers:
                result["mcp_servers"] = mcp_servers

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        skills = _load_skill_directories(skills_dir, source="openclaw")
        if skills:
            result["openclaw_skills"] = skills

    for extra_skills in _discover_openclaw_skill_dirs(root):
        skills = _load_skill_directories(extra_skills, source="openclaw")
        if skills:
            existing_skills = result.get("openclaw_skills")
            merged_skills: list[dict[str, object]] = list(existing_skills) if isinstance(existing_skills, list) else []
            merged_skills.extend(skills)
            result["openclaw_skills"] = merged_skills

    return result


def _load_cursor(root: Path, file_paths: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    rules: list[dict[str, object]] = []

    for raw in file_paths:
        path = Path(raw)
        if path.suffix in {".md", ".mdc"} and path.is_file():
            rules.append(_cursor_rule_from_file(path))

    rules_dir = root / "rules"
    if rules_dir.is_dir():
        for path in rules_dir.iterdir():
            if path.suffix in {".md", ".mdc"} and path.is_file():
                rules.append(_cursor_rule_from_file(path))

    if rules:
        result["cursor_rules"] = rules

    settings_path = _path_by_kind(file_paths, "settings.json") or _find_file(root, "settings.json")
    if settings_path:
        settings_data = _read_json(settings_path)
        if isinstance(settings_data, dict):
            result["cursor_settings"] = settings_data

    return result


def _load_codex(root: Path, file_paths: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}

    instructions_path = _path_by_kind(file_paths, "instructions.md") or _find_file(root, "instructions.md")
    if instructions_path:
        result["codex_instructions"] = _read_text(instructions_path)

    for settings_name in ("config.json", "settings.json"):
        settings_path = _path_by_kind(file_paths, settings_name) or _find_file(root, settings_name)
        if settings_path:
            settings_data = _read_json(settings_path)
            if isinstance(settings_data, dict):
                result["codex_settings"] = settings_data
            break

    return result


def _load_claude(root: Path, file_paths: list[str]) -> dict[str, object]:
    """Load Claude Code CLAUDE.md, optional settings, and skill directories."""

    result: dict[str, object] = {}

    claude_md = _path_by_kind(file_paths, "CLAUDE.md") or _find_file(root, "CLAUDE.md")
    if claude_md:
        content = _read_text(claude_md).strip()
        if content:
            result["semantic"] = [
                {
                    "content": content,
                    "importance": 0.75,
                    "confidence": 0.75,
                    "tags": ["claude_code", "CLAUDE.md"],
                },
            ]

    settings_path = _path_by_kind(file_paths, "settings.json") or _find_file(root, "settings.json")
    if settings_path:
        settings_data = _read_json(settings_path)
        if isinstance(settings_data, dict):
            result["claude_settings"] = settings_data
            mcp_servers = settings_data.get("mcpServers") or settings_data.get("mcp_servers")
            if isinstance(mcp_servers, dict) and mcp_servers:
                result["mcp_servers"] = mcp_servers

    config_path = _path_by_kind(file_paths, "config.yaml") or _find_file(root, "config.yaml")
    if config_path:
        config_data = _read_yaml(config_path)
        if isinstance(config_data, dict):
            result["hermes_config"] = config_data

            # Extract MCP configurations
            mcp_servers = config_data.get("mcp_servers") or config_data.get("mcp")
            if isinstance(mcp_servers, dict) and mcp_servers:
                result["mcp_servers"] = mcp_servers

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        skills = _load_skill_directories(skills_dir, source="claude")
        if skills:
            result["skills"] = skills

    return result


def _load_skill_directories(skills_dir: Path, *, source: str) -> list[dict[str, object]]:
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
                "content": _read_text(skill_md),
                "path": str(entry),
                "source": source,
            },
        )
    return skills


def _cursor_rule_from_file(path: Path) -> dict[str, object]:
    return {
        "name": path.stem,
        "content": _read_text(path),
        "globs": "*.md",
        "path": str(path),
    }


def _extract_env_key_names(env_path: Path) -> list[dict[str, str]]:
    content = _read_text(env_path)
    keys: list[dict[str, str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in _ENV_API_KEY_NAMES:
            keys.append({"name": key})
    return keys


def _normalize_openclaw_sessions(data: object | None) -> list[dict[str, object]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        sessions = data.get("sessions")
        if isinstance(sessions, list):
            return [item for item in sessions if isinstance(item, dict)]
    return []


def _normalize_openclaw_memory(data: object | None) -> list[dict[str, object]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("memories", "entries", "items", "data"):
            nested = data.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def _markdown_bullets_to_openclaw_memory(content: str, *, category: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for match in _MEMORY_BULLET_PATTERN.finditer(content):
        text = match.group(1).strip()
        if text:
            entries.append({"content": text, "type": category, "category": category})
    stripped = content.strip()
    if not entries and stripped:
        entries.append({"content": stripped, "type": category, "category": category})
    return entries


def _collect_openclaw_workspace_text(root: Path, filename: str) -> str:
    """Merge the same markdown file from every OpenClaw workspace directory."""

    parts: list[str] = []
    for workspace_dir in _discover_openclaw_workspace_dirs(root):
        candidate = workspace_dir / filename
        if candidate.is_file():
            text = _read_text(candidate).strip()
            if text:
                parts.append(text)
    return "\n\n---\n\n".join(parts)


def _merge_openclaw_markdown_into_memory(result: dict[str, object]) -> None:
    """Convert workspace MEMORY.md / USER.md bullets into structured openclaw_memory entries."""

    existing = result.get("openclaw_memory")
    merged: list[dict[str, object]] = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []

    memory_md = result.get("memory_md")
    if isinstance(memory_md, str) and memory_md.strip():
        merged.extend(_markdown_bullets_to_openclaw_memory(memory_md, category="memory"))

    user_md = result.get("user_md")
    if isinstance(user_md, str) and user_md.strip():
        merged.extend(_markdown_bullets_to_openclaw_memory(user_md, category="user"))

    if merged:
        result["openclaw_memory"] = merged


def _discover_openclaw_workspace_dirs(root: Path) -> list[Path]:
    dirs: list[Path] = []
    for name in ("workspace", "workspace-main"):
        candidate = root / name
        if candidate.is_dir():
            dirs.append(candidate)
    try:
        for entry in root.iterdir():
            if entry.is_dir() and entry.name.startswith("workspace-"):
                dirs.append(entry)
    except OSError:
        return dirs
    return dirs


def _discover_openclaw_skill_dirs(root: Path) -> list[Path]:
    dirs: list[Path] = []
    for workspace_dir in _discover_openclaw_workspace_dirs(root):
        skills_dir = workspace_dir / "skills"
        if skills_dir.is_dir():
            dirs.append(skills_dir)
    return dirs


def _load_windsurf(root: Path, file_paths: list[str]) -> dict[str, object]:
    """Load Windsurf global_rules.md and workspace rules as cursor-compatible rules."""

    result: dict[str, object] = {}
    rules: list[dict[str, object]] = []
    seen_paths: set[str] = set()

    for raw in file_paths:
        path = Path(raw)
        if path.suffix == ".md" and path.is_file():
            resolved = str(path.resolve())
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                rules.append(_windsurf_rule_from_file(path))

    memories_dir = root / "memories"
    if memories_dir.is_dir():
        global_rules = memories_dir / "global_rules.md"
        if global_rules.is_file():
            resolved = str(global_rules.resolve())
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                rules.append(_windsurf_rule_from_file(global_rules))

    rules_dir = root / "rules"
    if rules_dir.is_dir():
        for path in rules_dir.iterdir():
            if path.suffix == ".md" and path.is_file():
                resolved = str(path.resolve())
                if resolved not in seen_paths:
                    seen_paths.add(resolved)
                    rules.append(_windsurf_rule_from_file(path))

    if rules:
        result["cursor_rules"] = rules

    return result


def _load_trae(root: Path, file_paths: list[str]) -> dict[str, object]:
    """Load Trae rules and skills as cursor-compatible rules."""

    result: dict[str, object] = {}
    rules: list[dict[str, object]] = []
    seen_paths: set[str] = set()

    for raw in file_paths:
        path = Path(raw)
        if path.suffix == ".md" and path.is_file():
            resolved = str(path.resolve())
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                rules.append(_trae_rule_from_file(path))

    rules_dir = root / "rules"
    if rules_dir.is_dir():
        for path in rules_dir.iterdir():
            if path.suffix == ".md" and path.is_file():
                resolved = str(path.resolve())
                if resolved not in seen_paths:
                    seen_paths.add(resolved)
                    rules.append(_trae_rule_from_file(path))

    if rules:
        result["cursor_rules"] = rules

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        skills = _load_skill_directories(skills_dir, source="trae")
        if skills:
            result["skills"] = skills

    return result


def _windsurf_rule_from_file(path: Path) -> dict[str, object]:
    return {
        "name": path.stem,
        "content": _read_text(path),
        "globs": "*.md",
        "path": str(path),
    }


def _trae_rule_from_file(path: Path) -> dict[str, object]:
    return {
        "name": path.stem,
        "content": _read_text(path),
        "globs": "*.md",
        "path": str(path),
    }
