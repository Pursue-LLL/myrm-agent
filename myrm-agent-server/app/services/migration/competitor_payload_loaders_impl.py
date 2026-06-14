"""Per-competitor payload loader implementations (basic loaders).

[INPUT]
Path root + file_paths from discovery.

[OUTPUT]
Adapter-ready dict per competitor (soul_md, memory, skills, env_keys, etc.).

[POS]
Basic loaders (hermes/cursor/codex/claude/windsurf/trae) live here.
Complex loaders (openclaw/qwenpaw) live in _loaders_openclaw_qwenpaw.py and are
re-exported from this module for a single public import surface.
"""

from __future__ import annotations

from pathlib import Path

from ._loader_utils import (
    extract_env_key_names,
    find_file,
    load_skill_directories,
    path_by_kind,
    read_text,
    read_yaml,
)


# --- Per-competitor loaders ---


def load_hermes(root: Path, file_paths: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}

    soul_path = path_by_kind(file_paths, "SOUL.md") or find_file(root, "SOUL.md")
    if soul_path:
        result["soul_md"] = read_text(soul_path)

    memory_path = path_by_kind(file_paths, "MEMORY.md") or find_file(root, "memories", "MEMORY.md")
    if memory_path:
        result["memory_md"] = read_text(memory_path)

    user_path = path_by_kind(file_paths, "USER.md") or find_file(root, "memories", "USER.md")
    if user_path:
        result["user_md"] = read_text(user_path)

    agents_path = path_by_kind(file_paths, "AGENTS.md") or find_file(root, "AGENTS.md")
    if agents_path:
        result["agents_md"] = read_text(agents_path)

    env_path = path_by_kind(file_paths, ".env") or find_file(root, ".env")
    if env_path:
        result["env_keys"] = extract_env_key_names(env_path)

    config_path = path_by_kind(file_paths, "config.yaml") or find_file(root, "config.yaml")
    if config_path:
        config_data = read_yaml(config_path)
        if isinstance(config_data, dict):
            result["hermes_config"] = config_data
            mcp_servers = config_data.get("mcp_servers") or config_data.get("mcp")
            if isinstance(mcp_servers, dict) and mcp_servers:
                result["mcp_servers"] = mcp_servers

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        skills = load_skill_directories(skills_dir, source="hermes")
        if skills:
            result["skills"] = skills

    return result


def load_cursor(root: Path, file_paths: list[str]) -> dict[str, object]:
    from ._loader_utils import read_json

    result: dict[str, object] = {}
    rules: list[dict[str, object]] = []

    for raw in file_paths:
        path = Path(raw)
        if path.suffix in {".md", ".mdc"} and path.is_file():
            rules.append(_rule_from_file(path))

    rules_dir = root / "rules"
    if rules_dir.is_dir():
        for path in rules_dir.iterdir():
            if path.suffix in {".md", ".mdc"} and path.is_file():
                rules.append(_rule_from_file(path))

    if rules:
        result["cursor_rules"] = rules

    settings_path = path_by_kind(file_paths, "settings.json") or find_file(root, "settings.json")
    if settings_path:
        settings_data = read_json(settings_path)
        if isinstance(settings_data, dict):
            result["cursor_settings"] = settings_data

    return result


def load_codex(root: Path, file_paths: list[str]) -> dict[str, object]:
    from ._loader_utils import read_json

    result: dict[str, object] = {}

    instructions_path = path_by_kind(file_paths, "instructions.md") or find_file(root, "instructions.md")
    if instructions_path:
        result["codex_instructions"] = read_text(instructions_path)

    for settings_name in ("config.json", "settings.json"):
        settings_path = path_by_kind(file_paths, settings_name) or find_file(root, settings_name)
        if settings_path:
            settings_data = read_json(settings_path)
            if isinstance(settings_data, dict):
                result["codex_settings"] = settings_data
            break

    return result


def load_claude(root: Path, file_paths: list[str]) -> dict[str, object]:
    from ._loader_utils import read_json

    result: dict[str, object] = {}

    claude_md = path_by_kind(file_paths, "CLAUDE.md") or find_file(root, "CLAUDE.md")
    if claude_md:
        content = read_text(claude_md).strip()
        if content:
            result["semantic"] = [
                {
                    "content": content,
                    "importance": 0.75,
                    "confidence": 0.75,
                    "tags": ["claude_code", "CLAUDE.md"],
                },
            ]

    settings_path = path_by_kind(file_paths, "settings.json") or find_file(root, "settings.json")
    if settings_path:
        settings_data = read_json(settings_path)
        if isinstance(settings_data, dict):
            result["claude_settings"] = settings_data
            mcp_servers = settings_data.get("mcpServers") or settings_data.get("mcp_servers")
            if isinstance(mcp_servers, dict) and mcp_servers:
                result["mcp_servers"] = mcp_servers

    config_path = path_by_kind(file_paths, "config.yaml") or find_file(root, "config.yaml")
    if config_path:
        config_data = read_yaml(config_path)
        if isinstance(config_data, dict):
            result["hermes_config"] = config_data
            mcp_servers = config_data.get("mcp_servers") or config_data.get("mcp")
            if isinstance(mcp_servers, dict) and mcp_servers:
                result["mcp_servers"] = mcp_servers

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        skills = load_skill_directories(skills_dir, source="claude")
        if skills:
            result["skills"] = skills

    return result


def load_windsurf(root: Path, file_paths: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    extra_dirs: list[Path] = []
    memories_dir = root / "memories"
    if memories_dir.is_dir():
        extra_dirs.append(memories_dir)
    rules = _collect_rules(root, file_paths, extra_scan_dirs=extra_dirs)
    if rules:
        result["cursor_rules"] = rules
    return result


def load_trae(root: Path, file_paths: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    rules = _collect_rules(root, file_paths)
    if rules:
        result["cursor_rules"] = rules
    skills_dir = root / "skills"
    if skills_dir.is_dir():
        skills = load_skill_directories(skills_dir, source="trae")
        if skills:
            result["skills"] = skills
    return result


# --- Private helpers ---


def _collect_rules(
    root: Path,
    file_paths: list[str],
    *,
    extra_scan_dirs: list[Path] | None = None,
) -> list[dict[str, object]]:
    """Collect rule files from explicit paths, extra dirs, and root/rules/."""

    rules: list[dict[str, object]] = []
    seen: set[str] = set()

    for raw in file_paths:
        path = Path(raw)
        if path.suffix == ".md" and path.is_file():
            resolved = str(path.resolve())
            if resolved not in seen:
                seen.add(resolved)
                rules.append(_rule_from_file(path))

    scan_dirs = list(extra_scan_dirs or [])
    rules_dir = root / "rules"
    if rules_dir.is_dir():
        scan_dirs.append(rules_dir)

    for dir_path in scan_dirs:
        if not dir_path.is_dir():
            continue
        for path in dir_path.iterdir():
            if path.suffix == ".md" and path.is_file():
                resolved = str(path.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    rules.append(_rule_from_file(path))

    return rules


def _rule_from_file(path: Path) -> dict[str, object]:
    return {
        "name": path.stem,
        "content": read_text(path),
        "globs": "*.md",
        "path": str(path),
    }


# Re-export complex loaders for a unified import surface
from ._loaders_openclaw_qwenpaw import load_openclaw, load_qwenpaw  # noqa: E402, F401
