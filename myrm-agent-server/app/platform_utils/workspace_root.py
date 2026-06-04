"""Workspace root path resolution for server runtime."""

from __future__ import annotations

from pathlib import Path


def get_workspace_root() -> Path:
    """Return the workspace root directory from settings, or cwd as fallback."""
    from app.config.settings import settings

    if hasattr(settings, "workspace_root") and settings.workspace_root:
        return Path(settings.workspace_root)
    return Path.cwd()
