"""Shared local filesystem reveal helpers for product REST endpoints.

[INPUT]
- platform / subprocess / os / shutil (stdlib)

[OUTPUT]
- reveal_path_in_file_manager: Reveal path in Finder/Explorer
- open_with_default_app: Open file with OS default handler
- open_vault_in_obsidian_app: Launch Obsidian on vault folder (Local/Tauri)
- is_obsidian_direct_launch_available: Whether direct Obsidian launch is supported

[POS]
Cross-endpoint filesystem UX helpers for local/Tauri deployments.
Used by files local_actions and wiki vault reveal/open routes.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException

_OBSIDIAN_MACOS_APP_CANDIDATES: tuple[Path, ...] = (
    Path("/Applications/Obsidian.app"),
    Path.home() / "Applications/Obsidian.app",
)


def _obsidian_windows_executable_candidates() -> tuple[Path, ...]:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return ()
    base = Path(local_app_data)
    return (
        base / "Programs" / "Obsidian" / "Obsidian.exe",
        base / "Obsidian" / "Obsidian.exe",
    )


def _resolve_obsidian_executable() -> Path | None:
    """Return an Obsidian launcher path when installed on the current platform."""
    system = platform.system()
    if system == "Darwin":
        for candidate in _OBSIDIAN_MACOS_APP_CANDIDATES:
            if candidate.is_dir():
                return candidate
        return None
    if system == "Windows":
        for candidate in _obsidian_windows_executable_candidates():
            if candidate.is_file():
                return candidate
        return None

    obsidian_bin = shutil.which("obsidian")
    if obsidian_bin:
        return Path(obsidian_bin)
    return None


def reveal_path_in_file_manager(path: Path) -> None:
    """Reveal a file or open a directory in the system file manager."""
    system = platform.system()
    target = path.resolve()
    try:
        if target.is_dir():
            if system == "Darwin":
                subprocess.Popen(["open", str(target)])
            elif system == "Windows":
                subprocess.Popen(["explorer.exe", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
            return

        if system == "Darwin":
            subprocess.Popen(["open", "-R", str(target)])
        elif system == "Windows":
            subprocess.Popen(["explorer.exe", f"/select,{target}"])
        else:
            subprocess.Popen(["xdg-open", str(target.parent)])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"File manager command not found on {system}") from exc


def open_with_default_app(path: Path) -> None:
    """Open a file with the system's default application."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", str(path)])
        elif system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Open command not found on {system}") from exc


def open_vault_in_obsidian_app(vault_path: Path) -> bool:
    """Try to launch Obsidian with the vault folder. Returns True when a launcher ran."""
    resolved = vault_path.resolve()
    if not resolved.is_dir():
        return False

    system = platform.system()
    try:
        if system == "Darwin":
            if _resolve_obsidian_executable() is None:
                return False
            subprocess.Popen(["open", "-a", "Obsidian", str(resolved)])
            return True

        executable = _resolve_obsidian_executable()
        if executable is None:
            return False
        subprocess.Popen([str(executable), str(resolved)])
        return True
    except (FileNotFoundError, OSError):
        return False


def is_obsidian_app_installed() -> bool:
    """Return True when Obsidian is installed for the current platform."""
    return _resolve_obsidian_executable() is not None


def is_obsidian_direct_launch_available() -> bool:
    """Return True when local deployment can launch Obsidian with the vault folder."""
    from app.config.deploy_mode import is_local_mode

    return is_local_mode() and is_obsidian_app_installed()
