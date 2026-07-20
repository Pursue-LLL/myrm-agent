"""Per-source filesystem probe implementations.

[INPUT]
source_discovery::_get_search_paths (POS: 外部助手数据目录路径解析)

[OUTPUT]
ExternalSource | None for hermes, claude, openclaw, codex.

[POS]
Local/Tauri filesystem probes for the four supported migration sources only.
"""

from __future__ import annotations

from pathlib import Path

from .source_discovery import (
    ConfidenceLevel,
    DiscoveredFile,
    ExternalSource,
    _count_md_bullets,
    _detect_api_keys_in_env,
    _get_search_paths,
)

_HERMES_FILES = {
    "config.yaml": "config",
    "SOUL.md": "soul",
    "AGENTS.md": "agents",
    ".env": "env",
}
_HERMES_MEMORY_FILES = {
    "MEMORY.md": "memory",
    "USER.md": "user",
}

_CLAUDE_HOME_FILES = {
    "CLAUDE.md": "memory",
    "settings.json": "settings",
    "settings.local.json": "settings_local",
}


def discover_hermes(explicit_home: Path | None) -> ExternalSource | None:
    candidates = _get_search_paths("HERMES_HOME", "hermes", ".hermes", explicit_home)
    root = _find_first_dir(candidates)
    if not root:
        return None

    source = ExternalSource(competitor="hermes", root=str(root))

    for filename, kind in _HERMES_FILES.items():
        path = root / filename
        if path.is_file():
            source.files.append(
                DiscoveredFile(path=str(path), kind=kind, size_bytes=path.stat().st_size)
            )
            if kind == "env":
                source.has_api_keys = _detect_api_keys_in_env(path)

    memories_dir = root / "memories"
    if memories_dir.is_dir():
        for filename, kind in _HERMES_MEMORY_FILES.items():
            path = memories_dir / filename
            if path.is_file():
                source.files.append(
                    DiscoveredFile(path=str(path), kind=kind, size_bytes=path.stat().st_size)
                )
                if kind == "memory":
                    source.memory_count_estimate = _count_md_bullets(path)

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        source.skill_count = sum(1 for entry in skills_dir.iterdir() if entry.is_dir() and (entry / "SKILL.md").is_file())

    source.confidence = _hermes_confidence(source)
    return source if source.confidence != "low" else None


def discover_claude(explicit_home: Path | None) -> ExternalSource | None:
    candidates = _get_search_paths("CLAUDE_HOME", "Claude", ".claude", explicit_home)
    root = _find_first_dir(candidates)
    if not root:
        return None

    source = ExternalSource(competitor="claude", root=str(root))

    for filename, kind in _CLAUDE_HOME_FILES.items():
        path = root / filename
        if path.is_file():
            source.files.append(
                DiscoveredFile(path=str(path), kind=kind, size_bytes=path.stat().st_size)
            )
            if kind == "memory":
                source.memory_count_estimate = _count_md_bullets(path)

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        source.skill_count = sum(1 for _ in skills_dir.iterdir() if _.is_dir())

    commands_dir = root / "commands"
    if commands_dir.is_dir():
        source.skill_count += sum(1 for _ in commands_dir.iterdir() if _.is_file())

    source.confidence = _claude_confidence(source)
    return source if source.confidence != "low" else None


def discover_openclaw(explicit_home: Path | None) -> ExternalSource | None:
    candidates = _get_search_paths("OPENCLAW_HOME", "openclaw", ".openclaw", explicit_home)
    root = _find_first_dir(candidates)
    if not root:
        return None

    source = ExternalSource(competitor="openclaw", root=str(root))

    for candidate in ("memory.json", "sessions.json", "config.json"):
        path = root / candidate
        if path.is_file():
            source.files.append(
                DiscoveredFile(path=str(path), kind=candidate.replace(".json", ""), size_bytes=path.stat().st_size)
            )

    for workspace_dir in _openclaw_workspace_dirs(root):
        for md_name, kind in (("SOUL.md", "soul"), ("MEMORY.md", "memory"), ("USER.md", "user")):
            md_path = workspace_dir / md_name
            if md_path.is_file():
                source.files.append(
                    DiscoveredFile(path=str(md_path), kind=f"workspace_{kind}", size_bytes=md_path.stat().st_size)
                )
                if kind == "memory":
                    source.memory_count_estimate += _count_md_bullets(md_path)

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        source.skill_count = sum(1 for _ in skills_dir.iterdir())

    source.confidence = "high" if len(source.files) >= 2 else "medium" if source.files else "low"
    return source if source.confidence != "low" else None


def discover_codex(explicit_home: Path | None) -> ExternalSource | None:
    candidates = _get_search_paths("CODEX_HOME", "codex", ".codex", explicit_home)
    root = _find_first_dir(candidates)
    if not root:
        return None

    source = ExternalSource(competitor="codex", root=str(root))

    for candidate in ("instructions.md", "config.json", "settings.json"):
        path = root / candidate
        if path.is_file():
            source.files.append(
                DiscoveredFile(path=str(path), kind=candidate.split(".")[0], size_bytes=path.stat().st_size)
            )

    source.confidence = "high" if len(source.files) >= 2 else "medium" if source.files else "low"
    return source if source.confidence != "low" else None


def _find_first_dir(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _hermes_confidence(source: ExternalSource) -> ConfidenceLevel:
    has_memory = any(f.kind in ("memory", "user") for f in source.files)
    has_config = any(f.kind == "config" for f in source.files)
    has_soul = any(f.kind == "soul" for f in source.files)
    if has_memory and (has_config or has_soul):
        return "high"
    if has_memory or has_config or has_soul:
        return "medium"
    return "low"


def _claude_confidence(source: ExternalSource) -> ConfidenceLevel:
    has_memory = any(f.kind == "memory" for f in source.files)
    has_settings = any(f.kind == "settings" for f in source.files)
    if has_memory and has_settings:
        return "high"
    if has_memory or has_settings or source.skill_count > 0:
        return "medium"
    return "low"


def _openclaw_workspace_dirs(root: Path) -> list[Path]:
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
