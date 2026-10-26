"""Workspace root path resolution for server runtime.

[INPUT]
myrm_agent_harness.core.context_vars::workspace_root_var (POS: root bound to the active run)

[OUTPUT]
get_workspace_root: 解析 MYRM 工作区根目录 Path

[POS]
平台层工作区路径解析，供 core/services/api 共用，避免 api.dependencies 被下层 import。
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.core.context_vars import workspace_root_var


def get_workspace_root() -> Path:
    """Return the root bound to the active run, or the process working directory outside a run.

    Code that serves a chat or an artifact outside a run must resolve the chat's root with
    ``app.services.chat.effective_workspace.resolve_chat_workspace_root`` instead.
    """
    return Path(workspace_root_var.get() or Path.cwd())
