"""Per-source filesystem probe implementations.

[INPUT]
source_discovery::_get_search_paths (POS: 外部助手数据目录路径解析)

[OUTPUT]
ExternalSource | None for hermes, claude, openclaw, codex, pi, plur.

[POS]
Local/Tauri filesystem probes for the supported migration sources. Claude Code
auto-memory directories and Codex memory files are probed alongside their
instruction/config lanes; PLUR reads the official ``~/.plur`` engram store.
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

_CLAUDE_AUTO_MEMORY_MAX_FILES = 2000
_CLAUDE_AUTO_MEMORY_MAX_PROJECT_DIRS = 5000
_PLUR_ENGRAM_MAX_COUNT = 5000
_PLUR_ENGRAM_MAX_SCAN_LINES = 200_000

_HERMES_FILES = {
    "config.yaml": "config",
    "SOUL.md": "soul",
    "AGENTS.md": "agents",
    ".env": "env",
    "auth.json": "auth",
}
_HERMES_MEMORY_FILES = {
    "MEMORY.md": "memory",
    "USER.md": "user",
}

_CLAUDE_HOME_FILES = {
    "CLAUDE.md": "claude_md",
    "CLAUDE.local.md": "claude_local_md",
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
            source.files.append(DiscoveredFile(path=str(path), kind=kind, size_bytes=path.stat().st_size))
            if kind == "env":
                source.has_api_keys = _detect_api_keys_in_env(path) or source.has_api_keys
            elif kind == "auth":
                source.has_api_keys = True

    memories_dir = root / "memories"
    if memories_dir.is_dir():
        for filename, kind in _HERMES_MEMORY_FILES.items():
            path = memories_dir / filename
            if path.is_file():
                source.files.append(DiscoveredFile(path=str(path), kind=kind, size_bytes=path.stat().st_size))
                if kind == "memory":
                    source.memory_count_estimate = _count_md_bullets(path)

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        source.skill_count = sum(1 for entry in skills_dir.iterdir() if entry.is_dir() and (entry / "SKILL.md").is_file())

    from ..hermes.hermes_cron_converter import discover_hermes_cron_job_files

    for cron_path, _profile in discover_hermes_cron_job_files(root):
        source.files.append(DiscoveredFile(path=str(cron_path), kind="cron_jobs", size_bytes=cron_path.stat().st_size))

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
            source.files.append(DiscoveredFile(path=str(path), kind=kind, size_bytes=path.stat().st_size))
            if kind == "claude_md":
                source.memory_count_estimate = _count_md_bullets(path)

    memory_files = collect_claude_auto_memory_files(root)
    for memory_file in memory_files:
        try:
            size = memory_file.stat().st_size
        except OSError:
            size = 0
        source.files.append(DiscoveredFile(path=str(memory_file), kind="claude_memory", size_bytes=size))
    if memory_files:
        source.memory_count_estimate += len(memory_files)

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        source.skill_count = sum(1 for _ in skills_dir.iterdir() if _.is_dir())

    commands_dir = root / "commands"
    if commands_dir.is_dir():
        source.skill_count += sum(1 for _ in commands_dir.iterdir() if _.is_file())

    source.confidence = _claude_confidence(source)
    return source if source.confidence != "low" else None


def collect_claude_auto_memory_files(root: Path) -> list[Path]:
    """Collect Claude Code auto-memory markdown files under the store root.

    Memory lives in ``projects/<project>/memory/*.md``; a user-configured
    ``autoMemoryDirectory`` (absolute or ``~/``-relative) is honored on top.
    Both scans are bounded so a pathological store cannot stall discovery, and
    the loader reuses this collector so probe and load stay in lockstep.
    """

    memory_dirs: list[Path] = []
    projects_dir = root / "projects"
    if projects_dir.is_dir():
        scanned = 0
        try:
            for project_dir in projects_dir.iterdir():
                scanned += 1
                if scanned > _CLAUDE_AUTO_MEMORY_MAX_PROJECT_DIRS:
                    break
                if not project_dir.is_dir():
                    continue
                candidate = project_dir / "memory"
                if candidate.is_dir():
                    memory_dirs.append(candidate)
        except OSError:
            pass

    settings_path = root / "settings.json"
    if settings_path.is_file():
        from .._loader_utils import read_json

        settings = read_json(settings_path)
        if isinstance(settings, dict):
            configured = settings.get("autoMemoryDirectory")
            if isinstance(configured, str) and configured.strip():
                configured_dir = _resolve_memory_directory(configured)
                if configured_dir is not None and configured_dir.is_dir() and configured_dir not in memory_dirs:
                    memory_dirs.append(configured_dir)

    files: list[Path] = []
    for memory_dir in memory_dirs:
        try:
            entries = sorted(memory_dir.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_file() and entry.suffix.lower() == ".md":
                files.append(entry)
                if len(files) >= _CLAUDE_AUTO_MEMORY_MAX_FILES:
                    return files
    return files


def _resolve_memory_directory(raw_path: str) -> Path | None:
    """Resolve an absolute or ``~/``-relative auto-memory directory."""

    candidate = Path(raw_path.strip()).expanduser()
    return candidate if candidate.is_absolute() else None


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


_CODEX_MEMORY_FILES = (
    ("memories/MEMORY.md", "codex_memory"),
    ("memories/memory_summary.md", "codex_memory"),
)


def discover_codex(explicit_home: Path | None) -> ExternalSource | None:
    candidates = _get_search_paths("CODEX_HOME", "codex", ".codex", explicit_home)
    root = _find_first_dir(candidates)
    if not root:
        return None

    source = ExternalSource(competitor="codex", root=str(root))

    for candidate in ("instructions.md", "config.json", "settings.json"):
        path = root / candidate
        if path.is_file():
            source.files.append(DiscoveredFile(path=str(path), kind=candidate.split(".")[0], size_bytes=path.stat().st_size))

    for relative, kind in _CODEX_MEMORY_FILES:
        path = root / relative
        if path.is_file():
            source.files.append(DiscoveredFile(path=str(path), kind=kind, size_bytes=path.stat().st_size))
            source.memory_count_estimate += _count_md_bullets(path) or 1

    source.confidence = "high" if len(source.files) >= 2 else "medium" if source.files else "low"
    return source if source.confidence != "low" else None


def discover_plur(explicit_home: Path | None) -> ExternalSource | None:
    candidates = _get_search_paths("PLUR_PATH", "Plur", ".plur", explicit_home)
    root = _find_first_dir(candidates)
    if not root:
        return None

    source = ExternalSource(competitor="plur", root=str(root))

    engrams_path = root / "engrams.yaml"
    if not engrams_path.is_file():
        return None

    source.files.append(
        DiscoveredFile(path=str(engrams_path), kind="engrams", size_bytes=engrams_path.stat().st_size),
    )
    source.memory_count_estimate = count_plur_engrams(engrams_path)
    source.confidence = "high"
    return source


def count_plur_engrams(path: Path, *, max_count: int = _PLUR_ENGRAM_MAX_COUNT) -> int:
    """Count engram entries in a PLUR store file with a bounded line scan."""

    count = 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for scanned, line in enumerate(handle):
                if scanned > _PLUR_ENGRAM_MAX_SCAN_LINES:
                    break
                stripped = line.lstrip()
                if stripped.startswith("- id:") or stripped.startswith("- id :"):
                    count += 1
                    if count >= max_count:
                        break
    except OSError:
        return 0
    return count


def discover_pi(explicit_home: Path | None) -> ExternalSource | None:
    home = explicit_home or Path.home()
    agent_dir = home / ".pi" / "agent"
    if not agent_dir.is_dir():
        return None

    source = ExternalSource(competitor="pi", root=str(agent_dir))

    for filename, kind in (("AGENTS.md", "agents"), ("settings.json", "settings")):
        path = agent_dir / filename
        if path.is_file():
            source.files.append(DiscoveredFile(path=str(path), kind=kind, size_bytes=path.stat().st_size))

    auth_path = agent_dir / "auth.json"
    if auth_path.is_file():
        source.files.append(DiscoveredFile(path=str(auth_path), kind="auth", size_bytes=auth_path.stat().st_size))
        source.has_api_keys = True

    sessions_dir = agent_dir / "sessions"
    if sessions_dir.is_dir():
        session_count = sum(1 for f in sessions_dir.iterdir() if f.suffix == ".jsonl")
        if session_count > 0:
            source.memory_count_estimate = session_count

    skills_dir = agent_dir / "skills"
    if skills_dir.is_dir():
        source.skill_count = sum(1 for entry in skills_dir.iterdir() if entry.is_dir() and (entry / "SKILL.md").is_file())

    source.confidence = _pi_confidence(source)
    return source if source.confidence != "low" else None


def _pi_confidence(source: ExternalSource) -> ConfidenceLevel:
    has_agents = any(f.kind == "agents" for f in source.files)
    has_settings = any(f.kind == "settings" for f in source.files)
    has_sessions = source.memory_count_estimate > 0
    if has_agents and (has_settings or has_sessions):
        return "high"
    if has_agents or has_settings or has_sessions:
        return "medium"
    return "low"


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
    has_memory = any(f.kind in ("claude_md", "claude_memory") for f in source.files)
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
