"""Obsidian vault path discovery for competitor migration payloads.

[INPUT]
- Codex/Claude settings dicts or filesystem roots

[OUTPUT]
- Normalized existing directory paths suitable for workspace bind + wiki import handoff

[POS]
Server migration layer only. Shared by load_codex and workspace_bind_candidates.
"""

from __future__ import annotations

import os
from pathlib import Path

_OBSIDIAN_SETTING_KEY_HINTS = (
    "obsidian_vault",
    "obsidianVault",
    "obsidian_path",
    "obsidianPath",
    "vault_path",
    "vaultPath",
    "vault",
    "workspace",
    "workspace_path",
    "workspacePath",
)

_OPENHUMAN_MEMORY_VAULT = Path("~/OpenHuman/memory")
_CC_CURSOR_SHARED_VAULT_NAMES = (
    Path("~/Obsidian"),
    Path("~/Documents/Obsidian"),
    Path("~/Documents/Obsidian Vault"),
)


def codex_well_known_obsidian_vault_paths() -> list[str]:
    """Preset vault locations referenced by Codex+Obsidian / OpenHuman migration guides."""
    presets = [_OPENHUMAN_MEMORY_VAULT, *_CC_CURSOR_SHARED_VAULT_NAMES]
    return _existing_directory_paths(presets)


def extract_obsidian_vault_paths_from_settings(
    settings: dict[str, object],
) -> list[str]:
    """Parse competitor settings JSON for Obsidian vault directory hints."""
    found: list[str] = []
    _walk_settings_for_vault_paths(settings, found, depth=0)
    return _dedupe_existing_directories(found)


def collect_codex_obsidian_vault_hints(
    settings: dict[str, object] | None,
    *,
    discovery_root: Path | None = None,
) -> list[str]:
    """Merge settings-derived and well-known Codex+Obsidian vault paths."""
    candidates: list[str] = []
    if isinstance(settings, dict) and settings:
        candidates.extend(extract_obsidian_vault_paths_from_settings(settings))
    candidates.extend(codex_well_known_obsidian_vault_paths())
    if discovery_root is not None:
        candidates.extend(_scan_nearby_obsidian_vaults(discovery_root))
    return _dedupe_existing_directories(candidates)


def _walk_settings_for_vault_paths(value: object, found: list[str], *, depth: int) -> None:
    if depth > 4:
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key).strip().lower()
            if isinstance(nested, str):
                if _looks_like_obsidian_setting_key(key_text):
                    found.append(nested.strip())
                elif _path_has_obsidian_config(nested):
                    found.append(_obsidian_vault_from_nested_path(nested))
            else:
                _walk_settings_for_vault_paths(nested, found, depth=depth + 1)
        return
    if isinstance(value, list):
        for item in value:
            _walk_settings_for_vault_paths(item, found, depth=depth + 1)


def _looks_like_obsidian_setting_key(key_text: str) -> bool:
    if "obsidian" in key_text:
        return True
    return any(token in key_text for token in _OBSIDIAN_SETTING_KEY_HINTS)


def _path_has_obsidian_config(raw_path: str) -> bool:
    text = raw_path.strip()
    if not text or text.startswith("http"):
        return False
    expanded = Path(text).expanduser()
    if (expanded / ".obsidian").is_dir():
        return True
    parent = expanded.parent
    return parent.name == ".obsidian" and parent.parent.is_dir()


def _obsidian_vault_from_nested_path(raw_path: str) -> str:
    expanded = Path(raw_path.strip()).expanduser()
    if expanded.name == ".obsidian" and expanded.parent.is_dir():
        return str(expanded.parent)
    return str(expanded)


def _scan_nearby_obsidian_vaults(root: Path) -> list[str]:
    paths: list[str] = []
    for candidate in (root, root.parent, Path.home()):
        if not candidate.is_dir():
            continue
        try:
            for entry in candidate.iterdir():
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                if (entry / ".obsidian").is_dir():
                    paths.append(str(entry))
        except OSError:
            continue
    return paths


def _existing_directory_paths(raw_paths: list[Path | str]) -> list[str]:
    existing: list[str] = []
    for raw in raw_paths:
        path = Path(str(raw)).expanduser()
        if path.is_dir():
            existing.append(str(path))
    return existing


def _dedupe_existing_directories(raw_paths: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in raw_paths:
        text = raw.strip()
        if not text:
            continue
        expanded = str(Path(text).expanduser())
        if not os.path.isdir(expanded) or expanded in seen:
            continue
        seen.add(expanded)
        ordered.append(expanded)
    return ordered
