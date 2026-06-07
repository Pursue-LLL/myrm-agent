"""Competitor data auto-discovery service.

[INPUT]
Local filesystem scan of well-known competitor data directories.

[OUTPUT]
DiscoveryResult: list of detected competitor data sources with confidence scoring.

[POS]
Local/Tauri-only service that scans the user's home directory for competitor
AI assistant data (Hermes, Claude Code, OpenClaw, Cursor, Codex). SaaS mode
cannot access user filesystems, so this service only runs in local deployments.
"""

from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ConfidenceLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class DiscoveredFile:
    """A single file or directory detected within a competitor's data."""

    path: str
    kind: str
    size_bytes: int = 0


@dataclass
class CompetitorSource:
    """A detected competitor data installation."""

    competitor: str
    root: str
    confidence: ConfidenceLevel = "low"
    files: list[DiscoveredFile] = field(default_factory=list)
    memory_count_estimate: int = 0
    skill_count: int = 0
    has_api_keys: bool = False


@dataclass
class DiscoveryResult:
    """Aggregated result of scanning for all competitor data."""

    sources: list[CompetitorSource] = field(default_factory=list)
    scan_path: str = ""


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

_MEMORY_BULLET_PATTERN = re.compile(r"^[-*]\s+.+$", re.MULTILINE)

_ENV_API_KEY_PATTERN = re.compile(
    r"^(OPENAI_API_KEY|ANTHROPIC_API_KEY|OPENROUTER_API_KEY|GOOGLE_API_KEY|"
    r"GEMINI_API_KEY|GROQ_API_KEY|XAI_API_KEY|MISTRAL_API_KEY|DEEPSEEK_API_KEY)\s*=",
    re.MULTILINE,
)


def _get_search_paths(env_var: str, app_name: str, default_dot_dir: str, explicit_home: Path | None) -> list[Path]:
    paths: list[Path] = []

    if explicit_home:
        paths.append(explicit_home / default_dot_dir)

    env_val = os.environ.get(env_var, "").strip()
    if env_val:
        paths.append(Path(env_val))

    system = platform.system()
    if system == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        if local_appdata:
            paths.append(Path(local_appdata) / app_name)
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            paths.append(Path(appdata) / app_name)
    elif system == "Darwin":
        paths.append(Path.home() / "Library" / "Application Support" / app_name)

    paths.append(Path.home() / default_dot_dir)

    seen = set()
    result = []
    for p in paths:
        try:
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                result.append(resolved)
        except OSError:
            if p not in seen:
                seen.add(p)
                result.append(p)
    return result


def discover_competitors(home_dir: str | None = None) -> DiscoveryResult:
    """Scan the filesystem for known competitor data directories."""

    home = Path(home_dir) if home_dir else None
    scan_path = str(home) if home else str(Path.home())
    result = DiscoveryResult(scan_path=scan_path)

    hermes = _discover_hermes(home)
    if hermes:
        result.sources.append(hermes)

    claude = _discover_claude(home)
    if claude:
        result.sources.append(claude)

    openclaw = _discover_openclaw(home)
    if openclaw:
        result.sources.append(openclaw)

    cursor = _discover_cursor(home)
    if cursor:
        result.sources.append(cursor)

    codex = _discover_codex(home)
    if codex:
        result.sources.append(codex)

    windsurf = _discover_windsurf(home)
    if windsurf:
        result.sources.append(windsurf)

    return result


def _discover_hermes(explicit_home: Path | None) -> CompetitorSource | None:
    candidates = _get_search_paths("HERMES_HOME", "hermes", ".hermes", explicit_home)
    root = None
    for candidate in candidates:
        if candidate.is_dir():
            root = candidate
            break
    if not root:
        return None

    source = CompetitorSource(competitor="hermes", root=str(root))

    for filename, kind in _HERMES_FILES.items():
        path = root / filename
        if path.is_file():
            source.files.append(
                DiscoveredFile(
                    path=str(path),
                    kind=kind,
                    size_bytes=path.stat().st_size,
                )
            )
            if kind == "env":
                source.has_api_keys = _detect_api_keys_in_env(path)

    memories_dir = root / "memories"
    if memories_dir.is_dir():
        for filename, kind in _HERMES_MEMORY_FILES.items():
            path = memories_dir / filename
            if path.is_file():
                source.files.append(
                    DiscoveredFile(
                        path=str(path),
                        kind=kind,
                        size_bytes=path.stat().st_size,
                    )
                )
                if kind == "memory":
                    source.memory_count_estimate = _count_md_bullets(path)

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        source.skill_count = sum(1 for entry in skills_dir.iterdir() if entry.is_dir() and (entry / "SKILL.md").is_file())

    source.confidence = _hermes_confidence(source)
    return source if source.confidence != "low" else None


def _discover_claude(explicit_home: Path | None) -> CompetitorSource | None:
    candidates = _get_search_paths("CLAUDE_HOME", "Claude", ".claude", explicit_home)
    root = None
    for candidate in candidates:
        if candidate.is_dir():
            root = candidate
            break
    if not root:
        return None

    source = CompetitorSource(competitor="claude", root=str(root))

    for filename, kind in _CLAUDE_HOME_FILES.items():
        path = root / filename
        if path.is_file():
            source.files.append(
                DiscoveredFile(
                    path=str(path),
                    kind=kind,
                    size_bytes=path.stat().st_size,
                )
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


def _discover_openclaw(explicit_home: Path | None) -> CompetitorSource | None:
    candidates = _get_search_paths("OPENCLAW_HOME", "openclaw", ".openclaw", explicit_home)
    root = None
    for candidate in candidates:
        if candidate.is_dir():
            root = candidate
            break
    if not root:
        return None

    source = CompetitorSource(competitor="openclaw", root=str(root))

    for candidate in ("memory.json", "sessions.json", "config.json"):
        path = root / candidate
        if path.is_file():
            source.files.append(
                DiscoveredFile(
                    path=str(path),
                    kind=candidate.replace(".json", ""),
                    size_bytes=path.stat().st_size,
                )
            )

    for workspace_dir in _discover_openclaw_workspace_dirs(root):
        for md_name, kind in (("SOUL.md", "soul"), ("MEMORY.md", "memory"), ("USER.md", "user")):
            md_path = workspace_dir / md_name
            if md_path.is_file():
                source.files.append(
                    DiscoveredFile(
                        path=str(md_path),
                        kind=f"workspace_{kind}",
                        size_bytes=md_path.stat().st_size,
                    )
                )
                if kind == "memory":
                    source.memory_count_estimate += _count_md_bullets(md_path)

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        source.skill_count = sum(1 for _ in skills_dir.iterdir())

    source.confidence = "high" if len(source.files) >= 2 else "medium" if source.files else "low"
    return source if source.confidence != "low" else None


def _discover_cursor(explicit_home: Path | None) -> CompetitorSource | None:
    candidates = _get_search_paths("CURSOR_HOME", "Cursor", ".cursor", explicit_home)
    root = None
    for candidate in candidates:
        if candidate.is_dir():
            root = candidate
            break
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
            DiscoveredFile(
                path=str(settings_path),
                kind="settings",
                size_bytes=settings_path.stat().st_size,
            )
        )

    source.confidence = "high" if source.skill_count >= 3 else "medium" if source.files else "low"
    return source if source.confidence != "low" else None


def _discover_codex(explicit_home: Path | None) -> CompetitorSource | None:
    candidates = _get_search_paths("CODEX_HOME", "codex", ".codex", explicit_home)
    root = None
    for candidate in candidates:
        if candidate.is_dir():
            root = candidate
            break
    if not root:
        return None

    source = CompetitorSource(competitor="codex", root=str(root))

    for candidate in ("instructions.md", "config.json", "settings.json"):
        path = root / candidate
        if path.is_file():
            source.files.append(
                DiscoveredFile(
                    path=str(path),
                    kind=candidate.split(".")[0],
                    size_bytes=path.stat().st_size,
                )
            )

    source.confidence = "high" if len(source.files) >= 2 else "medium" if source.files else "low"
    return source if source.confidence != "low" else None


def _discover_windsurf(explicit_home: Path | None) -> CompetitorSource | None:
    """Detect Windsurf/Devin Desktop data at ~/.codeium/windsurf/ or ~/.codeium/devin/."""

    home = explicit_home or Path.home()
    codeium_base = home / ".codeium"
    if not codeium_base.is_dir():
        return None

    root = None
    for subdir in ("windsurf", "devin"):
        candidate = codeium_base / subdir
        if candidate.is_dir():
            root = candidate
            break
    if not root:
        return None

    source = CompetitorSource(competitor="windsurf", root=str(root))

    memories_dir = root / "memories"
    if memories_dir.is_dir():
        global_rules = memories_dir / "global_rules.md"
        if global_rules.is_file():
            source.files.append(
                DiscoveredFile(path=str(global_rules), kind="global_rules", size_bytes=global_rules.stat().st_size)
            )

        for entry in memories_dir.iterdir():
            if entry.is_file() and entry.suffix == ".md" and entry.name != "global_rules.md":
                source.files.append(
                    DiscoveredFile(path=str(entry), kind="memory", size_bytes=entry.stat().st_size)
                )
                source.memory_count_estimate += _count_md_bullets(entry)

    source.confidence = "high" if source.memory_count_estimate > 0 or any(f.kind == "global_rules" for f in source.files) else "medium" if source.files else "low"
    return source if source.confidence != "low" else None


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


def _count_md_bullets(path: Path) -> int:
    """Estimate memory count from bullet points in a Markdown file."""

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        return len(_MEMORY_BULLET_PATTERN.findall(content))
    except OSError:
        return 0


def _detect_api_keys_in_env(path: Path) -> bool:
    """Check if .env file contains known API key variables."""

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        return bool(_ENV_API_KEY_PATTERN.search(content))
    except OSError:
        return False


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
