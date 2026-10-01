"""Per-source payload loader implementations (basic loaders).

[INPUT]
Path root + file_paths from discovery.

[OUTPUT]
Adapter-ready dict per competitor (soul_md, memory, skills, env_keys, etc.).

[POS]
Basic loaders (hermes/codex/claude/gbrain) live here.
OpenClaw loader lives in _loaders_openclaw.py and Pi loader in _loaders_pi.py;
both are re-exported from this module.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .._loader_utils import (
    extract_env_key_names,
    find_file,
    load_skill_directories,
    load_usage_sidecar,
    path_by_kind,
    read_json,
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
            usage_map = load_usage_sidecar(skills_dir)
            if usage_map:
                for skill_item in skills:
                    usage_record = usage_map.get(str(skill_item.get("name", "")))
                    if usage_record:
                        skill_item["usage_stats"] = usage_record
            result["skills"] = skills

    from ..hermes.hermes_cron_converter import (
        build_hermes_cron_migration_plan,
        load_hermes_cron_jobs,
    )

    raw_cron_jobs = load_hermes_cron_jobs(root, file_paths)
    if raw_cron_jobs:
        result["hermes_cron_jobs"] = raw_cron_jobs
        plan = build_hermes_cron_migration_plan(raw_cron_jobs)
        result["hermes_cron_plan"] = plan.to_metadata_dict()

    auth_path = path_by_kind(file_paths, "auth.json") or find_file(root, "auth.json")
    if auth_path:
        auth_data = read_json(auth_path)
        if isinstance(auth_data, dict):
            result["hermes_auth"] = auth_data
            pool_data = auth_data.get("credential_pool") or auth_data.get("credential_pools")
            if isinstance(pool_data, dict):
                result["credential_pool"] = pool_data
                raw_env_keys = result.get("env_keys")
                existing_env_keys: list[dict[str, str]] = [
                    item for item in raw_env_keys if isinstance(item, dict)
                ] if isinstance(raw_env_keys, list) else []
                existing_names = {k.get("name") for k in existing_env_keys if isinstance(k, dict)}
                for prov in pool_data:
                    norm = str(prov).strip().upper()
                    key_name = f"{norm}_API_KEY"
                    if key_name not in existing_names:
                        existing_env_keys.append({"name": key_name})
                        existing_names.add(key_name)
                result["env_keys"] = existing_env_keys
            strategies = auth_data.get("credential_pool_strategies") or auth_data.get("pool_strategies")
            if isinstance(strategies, dict):
                result["credential_pool_strategies"] = strategies

    from myrm_agent_harness.runtime.context.transcripts import HermesTranscriptParser

    hermes_sessions: list[dict[str, object]] = []
    hermes_parser = HermesTranscriptParser()
    session_files: list[Path] = [
        Path(fp)
        for fp in file_paths
        if (fp.endswith(".json") or fp.endswith(".jsonl"))
        and "session" in fp.lower()
        and Path(fp).is_file()
    ]
    if not session_files and root.is_dir():
        for cand_dir in [root / "sessions", root / "history", root]:
            if cand_dir.is_dir():
                for p in cand_dir.glob("*.json*"):
                    if p.is_file() and p.name not in ("auth.json", "config.json", "jobs.json", "settings.json"):
                        session_files.append(p)
    seen_hermes_paths: set[Path] = set()
    for sf in session_files:
        if sf in seen_hermes_paths:
            continue
        seen_hermes_paths.add(sf)
        try:
            parsed_res = hermes_parser.parse_file(sf)
            if parsed_res.turns:
                hermes_sessions.append(_serialize_transcript(parsed_res))
        except Exception:
            continue
    if hermes_sessions:
        result["sessions"] = hermes_sessions

    return result


def _serialize_transcript(parsed: object) -> dict[str, object]:
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


def load_codex(root: Path, file_paths: list[str]) -> dict[str, object]:
    from myrm_agent_harness.runtime.context.transcripts import CodexTranscriptParser

    from .._loader_utils import read_json
    from ..obsidian_vault_hints import collect_codex_obsidian_vault_hints

    result: dict[str, object] = {}
    settings_data: dict[str, object] | None = None

    instructions_path = path_by_kind(file_paths, "instructions.md") or find_file(root, "instructions.md")
    if instructions_path:
        result["codex_instructions"] = read_text(instructions_path)

    for settings_name in ("config.json", "settings.json"):
        settings_path = path_by_kind(file_paths, settings_name) or find_file(root, settings_name)
        if settings_path:
            parsed = read_json(settings_path)
            if isinstance(parsed, dict):
                settings_data = parsed
                result["codex_settings"] = parsed
            break

    vault_hints = collect_codex_obsidian_vault_hints(settings_data, discovery_root=root)
    if vault_hints:
        result["obsidian_vault_hints"] = vault_hints

    # Discover and parse Codex sessions
    codex_sessions: list[dict[str, object]] = []
    parser = CodexTranscriptParser()
    session_files: list[Path] = [
        Path(fp) for fp in file_paths if fp.endswith(".json") and "session" in fp.lower() and Path(fp).is_file()
    ]
    if not session_files and root.is_dir():
        for cand_dir in [root / "sessions", root]:
            if cand_dir.is_dir():
                for p in cand_dir.glob("*.json"):
                    if p.is_file() and p.name not in ("config.json", "settings.json"):
                        session_files.append(p)
    seen_paths: set[Path] = set()
    for sf in session_files:
        if sf in seen_paths:
            continue
        seen_paths.add(sf)
        try:
            parsed_res = parser.parse_file(sf)
            if parsed_res.turns:
                codex_sessions.append(_serialize_transcript(parsed_res))
        except Exception:
            continue
    if codex_sessions:
        result["sessions"] = codex_sessions

    return result


def load_claude(root: Path, file_paths: list[str]) -> dict[str, object]:
    from myrm_agent_harness.runtime.context.transcripts import ClaudeTranscriptParser

    from .._loader_utils import read_json

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

    # Discover and parse Claude Code session transcripts
    claude_sessions: list[dict[str, object]] = []
    claude_parser = ClaudeTranscriptParser()
    session_files: list[Path] = [
        Path(fp) for fp in file_paths if fp.endswith(".jsonl") and Path(fp).is_file()
    ]
    if not session_files and root.is_dir():
        for cand_dir in [root / "sessions", root / "projects", root]:
            if cand_dir.is_dir():
                for p in cand_dir.glob("*.jsonl"):
                    if p.is_file():
                        session_files.append(p)
                for p in cand_dir.glob("*/*.jsonl"):
                    if p.is_file():
                        session_files.append(p)
    seen_claude_paths: set[Path] = set()
    for sf in session_files:
        if sf in seen_claude_paths:
            continue
        seen_claude_paths.add(sf)
        try:
            parsed_res = claude_parser.parse_file(sf)
            if parsed_res.turns:
                claude_sessions.append(_serialize_transcript(parsed_res))
        except Exception:
            continue
    if claude_sessions:
        result["sessions"] = claude_sessions

    return result


def load_chatgpt(root: Path, file_paths: list[str]) -> dict[str, object]:
    """Load ChatGPT conversations.json into adapter-ready payload."""

    from .._loader_utils import read_json

    result: dict[str, object] = {}

    conversations_path = path_by_kind(file_paths, "conversations.json") or find_file(root, "conversations.json")
    if conversations_path:
        data = read_json(conversations_path)
        if isinstance(data, list):
            result["conversations"] = data

    return result


def load_gbrain(root: Path, file_paths: list[str]) -> dict[str, object]:
    """Load gbrain export directory (.md files with YAML frontmatter) into adapter-ready payload.

    gbrain export produces: {slug}.md files with YAML frontmatter (type, title, tags)
    + compiled_truth body + optional <!-- timeline --> section.
    """

    pages: list[dict[str, object]] = []

    md_paths: list[Path] = []
    if file_paths:
        md_paths = [Path(fp) for fp in file_paths if fp.endswith(".md")]
    else:
        for item in root.rglob("*.md"):
            if item.is_file() and ".raw" not in item.parts:
                md_paths.append(item)

    for md_path in md_paths:
        try:
            content = read_text(md_path)
        except OSError:
            continue
        if not content.startswith("---"):
            continue

        end_idx = content.find("\n---", 3)
        if end_idx == -1:
            continue

        frontmatter_raw = content[3:end_idx].strip()
        body = content[end_idx + 4 :].strip()

        try:
            frontmatter = yaml.safe_load(frontmatter_raw)
        except (yaml.YAMLError, ValueError):
            frontmatter = {}

        if not isinstance(frontmatter, dict) or "type" not in frontmatter:
            continue

        compiled_truth = body
        timeline = ""
        for delimiter in ("<!-- timeline -->", "<!-- timeline-->", "--- timeline ---"):
            if delimiter in body:
                parts = body.split(delimiter, 1)
                compiled_truth = parts[0].strip()
                timeline = parts[1].strip()
                break

        pages.append(
            {
                "slug": str(md_path.relative_to(root)).removesuffix(".md"),
                "type": str(frontmatter.get("type", "")),
                "title": str(frontmatter.get("title", "")),
                "tags": frontmatter.get("tags", []),
                "compiled_truth": compiled_truth,
                "timeline": timeline,
                "frontmatter": frontmatter,
            }
        )

    return {"gbrain_pages": pages, "_source": "gbrain"}


from .._loaders_openclaw import load_openclaw  # noqa: E402, F401
from .._loaders_pi import load_pi  # noqa: E402, F401
