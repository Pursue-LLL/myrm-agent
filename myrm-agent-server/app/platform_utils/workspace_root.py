"""Workspace root path resolution for server runtime.

[INPUT]
app.config.settings::settings (POS: 统一配置中心)

[OUTPUT]
get_workspace_root: 解析 MYRM 工作区根目录 Path

[POS]
平台层工作区路径解析，供 core/services/api 共用，避免 api.dependencies 被下层 import。
"""

from __future__ import annotations

from pathlib import Path


def get_workspace_root() -> Path:
    """Return the workspace root directory from settings, or cwd as fallback."""
    from app.config.settings import settings

    if hasattr(settings, "workspace_root") and settings.workspace_root:
        return Path(settings.workspace_root)
    return Path.cwd()
