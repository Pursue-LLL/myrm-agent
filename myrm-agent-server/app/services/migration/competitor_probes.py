"""Per-competitor filesystem probe implementations.

[INPUT]
Path candidates from _get_search_paths utility.

[OUTPUT]
CompetitorSource | None for each competitor.

[POS]
Extracted from competitor_discovery.py to keep per-file line budget under 400.
Each function scans for a specific competitor's data directories and returns
structured results with confidence scoring.
"""

from __future__ import annotations

from pathlib import Path

from .competitor_discovery import (
    CompetitorSource,
    ConfidenceLevel,
    DiscoveredFile,
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


def discover_hermes(explicit_home: Path | None) -> CompetitorSource | None:
    candidates = _get_search_paths("HERMES_HOME", "hermes", ".hermes", explicit_home)
    root = _find_first_dir(candidates)
    if not root:
        return None

    source = CompetitorSource(competitor="hermes", root=str(root))

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


def discover_claude(explicit_home: Path | None) -> CompetitorSource | None:
    candidates = _get_search_paths("CLAUDE_HOME", "Claude", ".claude", explicit_home)
    root = _find_first_dir(candidates)
    if not root:
        return None

    source = CompetitorSource(competitor="claude", root=str(root))

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


def discover_openclaw(explicit_home: Path | None) -> CompetitorSource | None:
    candidates = _get_search_paths("OPENCLAW_HOME", "openclaw", ".openclaw", explicit_home)
    root = _find_first_dir(candidates)
    if not root:
        return None

    source = CompetitorSource(competitor="openclaw", root=str(root))

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


def discover_cursor(explicit_home: Path | None) -> CompetitorSource | None:
    candidates = _get_search_paths("CURSOR_HOME", "Cursor", ".cursor", explicit_home)
    root = _find_first_dir(candidates)
    if not root:
        return None

    source = CompetitorSource(competitor="cursor", root=str(root))

    rules_dir = root / "rules"
    if rules_dir.is_dir():
        rule_files = [f for f in rules_dir.iterdir() if f.suffix in (".md", ".mdc")]
        for f in rule_files:
            source.files.append(DiscoveredFile(path=str(f), kind="rule", size_bytes=f.stat().st_size))
        source.skill_count = len(rule_files)

    settings_path = root / "settings.json"
    if settings_path.is_file():
        source.files.append(
            DiscoveredFile(path=str(settings_path), kind="settings", size_bytes=settings_path.stat().st_size)
        )

    source.confidence = "high" if source.skill_count >= 3 else "medium" if source.files else "low"
    return source if source.confidence != "low" else None


def discover_codex(explicit_home: Path | None) -> CompetitorSource | None:
    candidates = _get_search_paths("CODEX_HOME", "codex", ".codex", explicit_home)
    root = _find_first_dir(candidates)
    if not root:
        return None

    source = CompetitorSource(competitor="codex", root=str(root))

    for candidate in ("instructions.md", "config.json", "settings.json"):
        path = root / candidate
        if path.is_file():
            source.files.append(
                DiscoveredFile(path=str(path), kind=candidate.split(".")[0], size_bytes=path.stat().st_size)
            )

    source.confidence = "high" if len(source.files) >= 2 else "medium" if source.files else "low"
    return source if source.confidence != "low" else None


def discover_windsurf(explicit_home: Path | None) -> CompetitorSource | None:
    """Detect Windsurf global rules at ~/.codeium/windsurf/memories/."""

    candidates = _get_search_paths("WINDSURF_HOME", "Windsurf", ".codeium", explicit_home)
    root = None
    for candidate in candidates:
        windsurf_dir = candidate / "windsurf" if candidate.name != "windsurf" else candidate
        if windsurf_dir.is_dir():
            root = windsurf_dir
            break
    if not root:
        return None

    source = CompetitorSource(competitor="windsurf", root=str(root))

    memories_dir = root / "memories"
    if memories_dir.is_dir():
        global_rules = memories_dir / "global_rules.md"
        if global_rules.is_file():
            source.files.append(
                DiscoveredFile(path=str(global_rules), kind="global_rule", size_bytes=global_rules.stat().st_size)
            )
            source.memory_count_estimate = _count_md_bullets(global_rules)

    rules_dir = root / "rules"
    if rules_dir.is_dir():
        rule_files = [f for f in rules_dir.iterdir() if f.suffix == ".md" and f.is_file()]
        for f in rule_files:
            source.files.append(DiscoveredFile(path=str(f), kind="rule", size_bytes=f.stat().st_size))
        source.skill_count += len(rule_files)

    source.confidence = "high" if source.skill_count >= 2 or source.memory_count_estimate > 0 else "medium" if source.files else "low"
    return source if source.confidence != "low" else None


def discover_trae(explicit_home: Path | None) -> CompetitorSource | None:
    """Detect Trae global rules at ~/.trae/rules/ and ~/.trae-cn/rules/."""

    trae_editions = [
        ("TRAE_HOME", "Trae", ".trae"),
        ("TRAE_CN_HOME", "Trae", ".trae-cn"),
    ]
    root = None
    for env_var, app_name, dot_dir in trae_editions:
        candidates = _get_search_paths(env_var, app_name, dot_dir, explicit_home)
        for candidate in candidates:
            if candidate.is_dir():
                root = candidate
                break
        if root:
            break
    if not root:
        return None

    source = CompetitorSource(competitor="trae", root=str(root))

    rules_dir = root / "rules"
    if rules_dir.is_dir():
        rule_files = [f for f in rules_dir.iterdir() if f.suffix == ".md" and f.is_file()]
        for f in rule_files:
            source.files.append(DiscoveredFile(path=str(f), kind="rule", size_bytes=f.stat().st_size))
        source.skill_count += len(rule_files)

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        source.skill_count += sum(1 for entry in skills_dir.iterdir() if entry.is_dir())

    source.confidence = "high" if source.skill_count >= 2 else "medium" if source.files or source.skill_count > 0 else "low"
    return source if source.confidence != "low" else None


def discover_qwenpaw(explicit_home: Path | None) -> CompetitorSource | None:
    """Detect QwenPaw/CoPaw data at ~/.qwenpaw or legacy ~/.copaw."""

    candidates: list[Path] = []
    if explicit_home is not None:
        candidates.append(explicit_home / ".qwenpaw")
        candidates.append(explicit_home / ".copaw")
    else:
        candidates.append(Path.home() / ".qwenpaw")
        candidates.append(Path.home() / ".copaw")

    root = _find_first_dir(candidates)
    if not root:
        return None

    source = CompetitorSource(competitor="qwenpaw", root=str(root))

    memory_dir = root / "memory"
    if memory_dir.is_dir():
        for entry in memory_dir.iterdir():
            if entry.is_file() and entry.suffix in (".json", ".md", ".txt"):
                source.files.append(
                    DiscoveredFile(path=str(entry), kind="memory", size_bytes=entry.stat().st_size)
                )
                source.memory_count_estimate += 1

    secret_dir = root / ".secret"
    if not secret_dir.is_dir():
        secret_dir = Path(str(root) + ".secret")
    if secret_dir.is_dir():
        env_file = secret_dir / ".env"
        if env_file.is_file():
            source.files.append(
                DiscoveredFile(path=str(env_file), kind="env", size_bytes=env_file.stat().st_size)
            )
            source.has_api_keys = _detect_api_keys_in_env(env_file)

    plugins_dir = root / "plugins"
    if plugins_dir.is_dir():
        source.skill_count += sum(1 for entry in plugins_dir.iterdir() if entry.is_dir())

    for workspace_dir in _qwenpaw_workspace_dirs(root):
        agent_json = workspace_dir / "agent.json"
        if agent_json.is_file():
            source.files.append(
                DiscoveredFile(path=str(agent_json), kind="agent_config", size_bytes=agent_json.stat().st_size)
            )
        for prompt_file in ("AGENTS.md", "SOUL.md", "PROFILE.md"):
            prompt_path = workspace_dir / prompt_file
            if prompt_path.is_file():
                source.files.append(
                    DiscoveredFile(path=str(prompt_path), kind="prompt", size_bytes=prompt_path.stat().st_size)
                )

    source.confidence = _qwenpaw_confidence(source)
    return source if source.confidence != "low" else None


# --- Private helpers ---


def _find_first_dir(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _hermes_confidence(source: CompetitorSource) -> ConfidenceLevel:
    has_memory = any(f.kind in ("memory", "user") for f in source.files)
    has_config = any(f.kind == "config" for f in source.files)
    has_soul = any(f.kind == "soul" for f in source.files)
    if has_memory and (has_config or has_soul):
        return "high"
    if has_memory or has_config or has_soul:
        return "medium"
    return "low"


def _claude_confidence(source: CompetitorSource) -> ConfidenceLevel:
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


def _qwenpaw_confidence(source: CompetitorSource) -> ConfidenceLevel:
    has_agent_config = any(f.kind == "agent_config" for f in source.files)
    has_memory = any(f.kind == "memory" for f in source.files)
    has_prompt = any(f.kind == "prompt" for f in source.files)
    if has_agent_config and (has_memory or has_prompt):
        return "high"
    if has_agent_config or has_memory or has_prompt or source.skill_count > 0:
        return "medium"
    return "low"


def _qwenpaw_workspace_dirs(root: Path) -> list[Path]:
    """Discover QwenPaw workspace directories containing agent.json."""

    dirs: list[Path] = []
    try:
        for entry in root.iterdir():
            if entry.is_dir() and (entry / "agent.json").is_file():
                dirs.append(entry)
    except OSError:
        pass
    return dirs
