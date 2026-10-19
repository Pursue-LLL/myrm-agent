"""Claude Code payload loader.

[INPUT]
Path root + file_paths from discovery (POS: Claude Code 数据目录)
app.services.migration.source.source_probes::collect_claude_auto_memory_files (POS: 本地 Claude Code 自动记忆采集)
app.services.migration._loader_utils (POS: 迁移载荷读取与转录序列化工具)

[OUTPUT]
load_claude: adapter-ready dict with claude_md, semantic (auto-memory items),
claude_settings, mcp_servers, skills and sessions.
load_claude_auto_memory: semantic memory items from the store's memory files.

[POS]
Claude Code lane of the migration loader: CLAUDE.md rules, the auto-memory
directory, settings/MCP config, skills and session transcripts. Probe, loader
and payload contract stay in one place and the impl module re-exports both
entry points.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from ._loader_utils import (
    find_file,
    load_skill_directories,
    markdown_bullets_to_memory,
    path_by_kind,
    read_text,
    read_yaml,
    serialize_transcript,
)
from .source.source_probes import collect_claude_auto_memory_files

_FRONTMATTER_BOUNDARY = "\n---"
_CLAUDE_MEMORY_INDEX_NAME = "MEMORY.md"


def load_claude(root: Path, file_paths: list[str]) -> dict[str, object]:
    from myrm_agent_harness.runtime.context.transcripts import ClaudeTranscriptParser

    from ._loader_utils import read_json

    result: dict[str, object] = {}

    claude_md_sections: list[str] = []
    claude_md = path_by_kind(file_paths, "CLAUDE.md") or find_file(root, "CLAUDE.md")
    if claude_md:
        content = read_text(claude_md).strip()
        if content:
            claude_md_sections.append(content)
    claude_local_md = path_by_kind(file_paths, "CLAUDE.local.md") or find_file(root, "CLAUDE.local.md")
    if claude_local_md:
        content = read_text(claude_local_md).strip()
        if content:
            claude_md_sections.append(content)
    if claude_md_sections:
        result["claude_md"] = "\n\n---\n\n".join(claude_md_sections)

    memory_items = load_claude_auto_memory(root)
    if memory_items:
        result["semantic"] = memory_items

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
    session_files: list[Path] = [Path(fp) for fp in file_paths if fp.endswith(".jsonl") and Path(fp).is_file()]
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
                claude_sessions.append(serialize_transcript(parsed_res))
        except Exception:
            continue
    if claude_sessions:
        result["sessions"] = claude_sessions

    return result


def load_claude_auto_memory(root: Path) -> list[dict[str, object]]:
    """Read Claude Code auto-memory files into semantic memory items.

    Individual memory files carry YAML frontmatter (``name`` / ``description`` /
    ``metadata.type``); ``MEMORY.md`` is the link index and is only used as a
    fallback when no individual memory file exists.
    """

    memory_files = collect_claude_auto_memory_files(root)
    if not memory_files:
        return []

    items: list[dict[str, object]] = []
    index_files: list[Path] = []
    for path in memory_files:
        if path.name == _CLAUDE_MEMORY_INDEX_NAME:
            index_files.append(path)
            continue
        item = _parse_claude_memory_file(path)
        if item is not None:
            items.append(item)

    if not items:
        for index_path in index_files:
            for entry in markdown_bullets_to_memory(read_text(index_path), category="claude_code_memory"):
                content = str(entry.get("content", "")).strip()
                if not content:
                    continue
                items.append(_claude_memory_item(content, {"file": index_path.name}, "index"))

    return items


def _parse_claude_memory_file(path: Path) -> dict[str, object] | None:
    """Parse one Claude Code memory file (frontmatter + body) into an item."""

    text = read_text(path).strip()
    if not text:
        return None

    front: dict[str, object] = {}
    body = text
    if text.startswith("---"):
        boundary = text.find(_FRONTMATTER_BOUNDARY, 3)
        if boundary != -1:
            raw_front = text[3:boundary].strip()
            try:
                parsed = yaml.safe_load(raw_front)
            except yaml.YAMLError:
                parsed = None
            if isinstance(parsed, dict):
                front = parsed
                body = text[boundary + 4 :].strip()

    description = str(front.get("description", "")).strip()
    content = body or description
    if not content:
        return None

    memory_type = ""
    metadata_block = front.get("metadata")
    if isinstance(metadata_block, dict):
        memory_type = str(metadata_block.get("type", "")).strip().lower()

    return _claude_memory_item(
        content,
        {
            "file": path.name,
            "name": str(front.get("name", "")).strip(),
            "description": description[:200],
            "type": memory_type,
        },
        memory_type or "memory",
    )


def _claude_memory_item(content: str, fields: dict[str, str], category: str) -> dict[str, object]:
    """Build the semantic memory item for one Claude Code memory entry."""

    tags = ["claude_code_memory"]
    if category:
        tags.append(category)
    metadata: dict[str, str] = {"external_source": "claude"}
    for key, value in fields.items():
        if value:
            metadata[f"external_{key}"] = value
    return {
        "content": content,
        "importance": 0.7,
        "confidence": 0.75,
        "tags": tags,
        "created_at": datetime.now(UTC).isoformat(),
        "metadata": metadata,
    }
