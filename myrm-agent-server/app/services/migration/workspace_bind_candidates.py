"""Discover filesystem paths suitable for post-migration project workspace bind.

[INPUT]
- Competitor discovery payload or loaded adapter payload with ``_discovery_root``
- OpenClaw workspace directory layout under competitor home

[OUTPUT]
- WorkspaceBindCandidate list for migration wizard handoff (pre-fill Mount UI)

[POS]
Server business layer only. Does not register Harness tools or alter agent prompts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_MAX_MD_SCAN = 2000


@dataclass(frozen=True, slots=True)
class WorkspaceBindCandidate:
    path: str
    label: str
    has_obsidian_config: bool
    markdown_file_count: int


def discover_workspace_bind_candidates(
    loaded_payload: dict[str, object],
) -> list[WorkspaceBindCandidate]:
    """Return validated workspace bind suggestions for a competitor import payload."""
    competitor = str(loaded_payload.get("_source", "")).strip().lower()
    root_raw = loaded_payload.get("_discovery_root")
    if not root_raw or not isinstance(root_raw, str):
        return []

    root = Path(root_raw).expanduser()
    if not root.is_dir():
        return []

    if competitor == "openclaw":
        return _candidates_from_openclaw_root(root)

    if competitor == "codex":
        return _candidates_from_codex_payload(loaded_payload)

    return []


def candidates_to_metadata(
    candidates: list[WorkspaceBindCandidate],
) -> list[dict[str, object]]:
    return [
        {
            "path": item.path,
            "label": item.label,
            "has_obsidian_config": item.has_obsidian_config,
            "markdown_file_count": item.markdown_file_count,
        }
        for item in candidates
    ]


def candidates_from_metadata(raw: object) -> list[WorkspaceBindCandidate]:
    if not isinstance(raw, list):
        return []
    parsed: list[WorkspaceBindCandidate] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        label = str(item.get("label", path)).strip() or path
        has_obsidian = item.get("has_obsidian_config") is True
        md_count_raw = item.get("markdown_file_count", 0)
        md_count = int(md_count_raw) if isinstance(md_count_raw, (int, float)) else 0
        parsed.append(
            WorkspaceBindCandidate(
                path=path,
                label=label,
                has_obsidian_config=has_obsidian,
                markdown_file_count=max(0, md_count),
            )
        )
    return parsed


def _candidates_from_codex_payload(
    loaded_payload: dict[str, object],
) -> list[WorkspaceBindCandidate]:
    from app.services.project.workspace_path_resolve import (
        WorkspacePathValidationError,
        normalize_project_workspace_path,
    )

    raw_hints = loaded_payload.get("obsidian_vault_hints")
    hint_paths: list[str] = []
    if isinstance(raw_hints, list):
        hint_paths = [
            str(item).strip()
            for item in raw_hints
            if isinstance(item, str) and str(item).strip()
        ]

    seen: set[str] = set()
    candidates: list[WorkspaceBindCandidate] = []
    for raw_path in hint_paths:
        try:
            normalized = normalize_project_workspace_path(
                str(Path(raw_path).expanduser())
            )
        except WorkspacePathValidationError:
            continue
        if not normalized or normalized in seen:
            continue
        directory = Path(normalized)
        if not directory.is_dir():
            continue
        seen.add(normalized)
        fingerprint = _fingerprint_directory(directory)
        candidates.append(
            WorkspaceBindCandidate(
                path=normalized,
                label=_codex_vault_label(normalized),
                has_obsidian_config=fingerprint.has_obsidian_config,
                markdown_file_count=fingerprint.markdown_file_count,
            )
        )
    return candidates


def _codex_vault_label(normalized_path: str) -> str:
    lowered = normalized_path.lower()
    if "openhuman" in lowered:
        return "OpenHuman memory vault"
    return "Codex Obsidian vault"


def _candidates_from_openclaw_root(root: Path) -> list[WorkspaceBindCandidate]:
    from app.services.project.workspace_path_resolve import (
        WorkspacePathValidationError,
        normalize_project_workspace_path,
    )

    seen: set[str] = set()
    candidates: list[WorkspaceBindCandidate] = []

    for workspace_dir in _discover_openclaw_workspace_dirs(root):
        try:
            normalized = normalize_project_workspace_path(str(workspace_dir))
        except WorkspacePathValidationError:
            continue
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        fingerprint = _fingerprint_directory(Path(normalized))
        candidates.append(
            WorkspaceBindCandidate(
                path=normalized,
                label="OpenClaw workspace",
                has_obsidian_config=fingerprint.has_obsidian_config,
                markdown_file_count=fingerprint.markdown_file_count,
            )
        )

    return candidates


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


@dataclass(frozen=True, slots=True)
class _DirectoryFingerprint:
    has_obsidian_config: bool
    markdown_file_count: int


def _fingerprint_directory(directory: Path) -> _DirectoryFingerprint:
    has_obsidian = (directory / ".obsidian").is_dir()
    md_count = 0
    try:
        for _dirpath, dirnames, filenames in os.walk(directory):
            dirnames[:] = [name for name in dirnames if not name.startswith(".")]
            for filename in filenames:
                if filename.lower().endswith(".md"):
                    md_count += 1
                    if md_count >= _MAX_MD_SCAN:
                        return _DirectoryFingerprint(
                            has_obsidian_config=has_obsidian,
                            markdown_file_count=md_count,
                        )
    except OSError:
        return _DirectoryFingerprint(
            has_obsidian_config=has_obsidian, markdown_file_count=md_count
        )
    return _DirectoryFingerprint(
        has_obsidian_config=has_obsidian, markdown_file_count=md_count
    )
