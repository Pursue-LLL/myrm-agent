"""Per-source payload loader implementations (basic loaders).

[INPUT]
Path root + file_paths from discovery.

[OUTPUT]
Adapter-ready dict per competitor (soul_md, memory, skills, env_keys, etc.).

[POS]
Basic loaders (hermes/codex/claude) live here.
OpenClaw loader lives in _loaders_openclaw.py and is re-exported from this module.
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


from ._loaders_openclaw import load_openclaw  # noqa: E402, F401
