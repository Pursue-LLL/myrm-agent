"""External AI assistant data auto-discovery service.

[INPUT]
Local filesystem scan of well-known external assistant data directories.

[OUTPUT]
DiscoveryResult: list of detected data sources with confidence scoring.

[POS]
Local/Tauri-only service that scans the user's home directory for external
AI assistant data (Hermes, Claude Code, OpenClaw, Codex — four sources only).
SaaS sandboxes cannot access user filesystems.
Per-source probe logic lives in source_probes.py.
New migration sources are intentionally out of scope; see _ARCH.md policy.
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
class ExternalSource:
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

    sources: list[ExternalSource] = field(default_factory=list)
    scan_path: str = ""


_MEMORY_BULLET_PATTERN = re.compile(r"^[-*]\s+.+$", re.MULTILINE)

_ENV_API_KEY_PATTERN = re.compile(
    r"^(OPENAI_API_KEY|ANTHROPIC_API_KEY|OPENROUTER_API_KEY|GOOGLE_API_KEY|"
    r"GEMINI_API_KEY|GROQ_API_KEY|XAI_API_KEY|MISTRAL_API_KEY|DEEPSEEK_API_KEY)\s*=",
    re.MULTILINE,
)


def _get_search_paths(env_var: str, app_name: str, default_dot_dir: str, explicit_home: Path | None) -> list[Path]:
    paths: list[Path] = []

    if explicit_home is not None:
        paths.append(explicit_home / default_dot_dir)
        return _dedupe_paths(paths)

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

    return _dedupe_paths(paths)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


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


def discover_external_sources(home_dir: str | None = None) -> DiscoveryResult:
    """Scan the filesystem for known competitor data directories."""

    from .source_probes import (
        discover_claude,
        discover_codex,
        discover_hermes,
        discover_openclaw,
    )

    home = Path(home_dir) if home_dir else None
    scan_path = str(home) if home else str(Path.home())
    result = DiscoveryResult(scan_path=scan_path)

    probes = [
        discover_hermes,
        discover_claude,
        discover_openclaw,
        discover_codex,
    ]

    for probe in probes:
        source = probe(home)
        if source:
            result.sources.append(source)

    return result
