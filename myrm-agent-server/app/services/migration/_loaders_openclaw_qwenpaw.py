"""OpenClaw and QwenPaw/CoPaw payload loader implementations.

[INPUT]
Path root + file_paths from discovery (multi-workspace directory structures).

[OUTPUT]
Adapter-ready dict with sessions, memory, MCP servers, skills for openclaw/qwenpaw.

[POS]
Complex loaders handling multi-directory traversal (workspaces, agent.json parsing).
"""

from __future__ import annotations

from pathlib import Path

from ._loader_utils import (
    extract_env_key_names,
    find_file,
    load_skill_directories,
    markdown_bullets_to_memory,
    path_by_kind,
    read_json,
    read_text,
    read_yaml,
)


def load_openclaw(root: Path, file_paths: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}

    sessions_path = path_by_kind(file_paths, "sessions.json") or find_file(root, "sessions.json")
    if sessions_path:
        sessions_data = read_json(sessions_path)
        sessions = _normalize_openclaw_sessions(sessions_data)
        if sessions:
            result["openclaw_sessions"] = sessions

    memory_path = path_by_kind(file_paths, "memory.json") or find_file(root, "memory.json")
    if memory_path:
        memory_data = read_json(memory_path)
        entries = _normalize_openclaw_memory(memory_data)
        if entries:
            result["openclaw_memory"] = entries

    config_path = path_by_kind(file_paths, "config.json") or find_file(root, "config.json")
    if config_path:
        config_data = read_json(config_path)
        if isinstance(config_data, dict):
            result["openclaw_config"] = config_data
            mcp_servers = config_data.get("mcp_servers") or config_data.get("mcp")
            if isinstance(mcp_servers, dict) and mcp_servers:
                result["mcp_servers"] = mcp_servers

    for md_name, key in (("MEMORY.md", "memory_md"), ("USER.md", "user_md"), ("SOUL.md", "soul_md")):
        md_path = path_by_kind(file_paths, md_name)
        if md_path is not None and md_path.is_file():
            text = read_text(md_path).strip()
        else:
            text = _collect_openclaw_workspace_text(root, md_name)
        if text:
            result[key] = text

    _merge_openclaw_markdown_into_memory(result)

    config_yaml_path = path_by_kind(file_paths, "config.yaml") or find_file(root, "config.yaml")
    if config_yaml_path:
        config_data = read_yaml(config_yaml_path)
        if isinstance(config_data, dict):
            result["hermes_config"] = config_data
            mcp_servers = config_data.get("mcp_servers") or config_data.get("mcp")
            if isinstance(mcp_servers, dict) and mcp_servers:
                result["mcp_servers"] = mcp_servers

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        skills = load_skill_directories(skills_dir, source="openclaw")
        if skills:
            result["openclaw_skills"] = skills

    for extra_skills in _discover_openclaw_skill_dirs(root):
        skills = load_skill_directories(extra_skills, source="openclaw")
        if skills:
            existing_skills = result.get("openclaw_skills")
            merged_skills: list[dict[str, object]] = list(existing_skills) if isinstance(existing_skills, list) else []
            merged_skills.extend(skills)
            result["openclaw_skills"] = merged_skills

    return result


def load_qwenpaw(root: Path, file_paths: list[str]) -> dict[str, object]:
    """Load QwenPaw/CoPaw agent configs, prompts, memory, and plugins."""

    result: dict[str, object] = {}
    agents: list[dict[str, object]] = []
    mcp_clients: dict[str, object] = {}

    for workspace_dir in _discover_qwenpaw_workspace_dirs(root):
        agent_json = workspace_dir / "agent.json"
        if not agent_json.is_file():
            continue
        agent_data = read_json(agent_json)
        if not isinstance(agent_data, dict):
            continue

        agent_entry: dict[str, object] = {
            "name": agent_data.get("name", workspace_dir.name),
            "id": agent_data.get("id", workspace_dir.name),
        }

        prompt_parts: list[str] = []
        prompt_files = agent_data.get("system_prompt_files")
        if isinstance(prompt_files, list):
            for filename in prompt_files:
                if isinstance(filename, str):
                    prompt_path = workspace_dir / filename
                    if prompt_path.is_file():
                        prompt_parts.append(read_text(prompt_path))

        if prompt_parts:
            agent_entry["system_prompt"] = "\n\n---\n\n".join(prompt_parts)

        mcp_cfg = agent_data.get("mcp")
        if isinstance(mcp_cfg, dict):
            clients = mcp_cfg.get("clients")
            if isinstance(clients, dict):
                mcp_clients.update(clients)

        agents.append(agent_entry)

    if agents:
        result["qwenpaw_agents"] = agents
        combined_prompts = [
            a["system_prompt"] for a in agents if isinstance(a.get("system_prompt"), str)
        ]
        if combined_prompts:
            result["soul_md"] = "\n\n---\n\n".join(combined_prompts)

    if mcp_clients:
        result["mcp_servers"] = mcp_clients

    memory_dir = root / "memory"
    if memory_dir.is_dir():
        memory_entries: list[dict[str, object]] = []
        for entry in sorted(memory_dir.iterdir()):
            if not entry.is_file():
                continue
            if entry.suffix == ".json":
                data = read_json(entry)
                if isinstance(data, list):
                    memory_entries.extend(item for item in data if isinstance(item, dict))
                elif isinstance(data, dict):
                    memory_entries.append(data)
            elif entry.suffix in (".md", ".txt"):
                text = read_text(entry).strip()
                if text:
                    memory_entries.extend(
                        markdown_bullets_to_memory(text, category="memory")
                    )
        if memory_entries:
            result["openclaw_memory"] = memory_entries

    secret_dir = root / ".secret"
    if secret_dir.is_dir():
        env_file = secret_dir / ".env"
        if env_file.is_file():
            result["env_keys"] = extract_env_key_names(env_file)

    plugins_dir = root / "plugins"
    if plugins_dir.is_dir():
        skills = load_skill_directories(plugins_dir, source="qwenpaw")
        if skills:
            result["skills"] = skills

    return result


# --- Private helpers ---


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


def _collect_openclaw_workspace_text(root: Path, filename: str) -> str:
    parts: list[str] = []
    for workspace_dir in _discover_openclaw_workspace_dirs(root):
        candidate = workspace_dir / filename
        if candidate.is_file():
            text = read_text(candidate).strip()
            if text:
                parts.append(text)
    return "\n\n---\n\n".join(parts)


def _merge_openclaw_markdown_into_memory(result: dict[str, object]) -> None:
    existing = result.get("openclaw_memory")
    merged: list[dict[str, object]] = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []

    memory_md = result.get("memory_md")
    if isinstance(memory_md, str) and memory_md.strip():
        merged.extend(markdown_bullets_to_memory(memory_md, category="memory"))

    user_md = result.get("user_md")
    if isinstance(user_md, str) and user_md.strip():
        merged.extend(markdown_bullets_to_memory(user_md, category="user"))

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


def _discover_qwenpaw_workspace_dirs(root: Path) -> list[Path]:
    dirs: list[Path] = []
    try:
        for entry in root.iterdir():
            if entry.is_dir() and (entry / "agent.json").is_file():
                dirs.append(entry)
    except OSError:
        pass
    return dirs
