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


def discover_competitors(home_dir: str | None = None) -> DiscoveryResult:
    """Scan the home directory for known competitor data directories."""

    home = Path(home_dir) if home_dir else Path.home()
    result = DiscoveryResult(scan_path=str(home))

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

    return result


def _discover_hermes(home: Path) -> CompetitorSource | None:
    root = home / ".hermes"
    if not root.is_dir():
        return None

    source = CompetitorSource(competitor="hermes", root=str(root))

    for filename, kind in _HERMES_FILES.items():
        path = root / filename
        if path.is_file():
            source.files.append(DiscoveredFile(
                path=str(path), kind=kind, size_bytes=path.stat().st_size,
            ))
            if kind == "env":
                source.has_api_keys = _detect_api_keys_in_env(path)

    memories_dir = root / "memories"
    if memories_dir.is_dir():
        for filename, kind in _HERMES_MEMORY_FILES.items():
            path = memories_dir / filename
            if path.is_file():
                source.files.append(DiscoveredFile(
                    path=str(path), kind=kind, size_bytes=path.stat().st_size,
                ))
                if kind == "memory":
                    source.memory_count_estimate = _count_md_bullets(path)

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        source.skill_count = sum(
            1 for entry in skills_dir.iterdir()
            if entry.is_dir() and (entry / "SKILL.md").is_file()
        )

    source.confidence = _hermes_confidence(source)
    return source if source.confidence != "low" else None


def _discover_claude(home: Path) -> CompetitorSource | None:
    root = home / ".claude"
    if not root.is_dir():
        return None

    source = CompetitorSource(competitor="claude", root=str(root))

    for filename, kind in _CLAUDE_HOME_FILES.items():
        path = root / filename
        if path.is_file():
            source.files.append(DiscoveredFile(
                path=str(path), kind=kind, size_bytes=path.stat().st_size,
            ))
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


def _discover_openclaw(home: Path) -> CompetitorSource | None:
    root = home / ".openclaw"
    if not root.is_dir():
        return None

    source = CompetitorSource(competitor="openclaw", root=str(root))

    for candidate in ("memory.json", "sessions.json", "config.json"):
        path = root / candidate
        if path.is_file():
            source.files.append(DiscoveredFile(
                path=str(path), kind=candidate.replace(".json", ""),
                size_bytes=path.stat().st_size,
            ))

    for workspace_dir in _discover_openclaw_workspace_dirs(root):
        for md_name, kind in (("SOUL.md", "soul"), ("MEMORY.md", "memory"), ("USER.md", "user")):
            md_path = workspace_dir / md_name
            if md_path.is_file():
                source.files.append(DiscoveredFile(
                    path=str(md_path), kind=f"workspace_{kind}",
                    size_bytes=md_path.stat().st_size,
                ))
                if kind == "memory":
                    source.memory_count_estimate += _count_md_bullets(md_path)

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        source.skill_count = sum(1 for _ in skills_dir.iterdir())

    source.confidence = "high" if len(source.files) >= 2 else "medium" if source.files else "low"
    return source if source.confidence != "low" else None


def _discover_cursor(home: Path) -> CompetitorSource | None:
    root = home / ".cursor"
    if not root.is_dir():
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
        source.files.append(DiscoveredFile(
            path=str(settings_path), kind="settings", size_bytes=settings_path.stat().st_size,
        ))

    source.confidence = "high" if source.skill_count >= 3 else "medium" if source.files else "low"
    return source if source.confidence != "low" else None


def _discover_codex(home: Path) -> CompetitorSource | None:
    root = home / ".codex"
    if not root.is_dir():
        return None

    source = CompetitorSource(competitor="codex", root=str(root))

    for candidate in ("instructions.md", "config.json", "settings.json"):
        path = root / candidate
        if path.is_file():
            source.files.append(DiscoveredFile(
                path=str(path), kind=candidate.split(".")[0],
                size_bytes=path.stat().st_size,
            ))

    source.confidence = "high" if len(source.files) >= 2 else "medium" if source.files else "low"
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
