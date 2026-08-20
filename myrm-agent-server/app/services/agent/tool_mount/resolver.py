"""Agent meta-tool mount SSOT — General / Fast / Cron narrow + PTC rules.

[INPUT]
- profile_resolver.BuiltinToolFlags (POS: entitlement flags from enabled_builtin_tools)
- surfaces.ExecutionSurface (POS: product entry surface)

[OUTPUT]
- resolve_agent_mount: surface + profile flags → meta mount flags (FileAccessMode on WEB_FAST)
- apply_ptc_meta_mount: MCP PTC dependency injection at factory time

[POS]
Server product-layer SSOT for when file/shell meta tools mount. Harness get_meta_tools
assembles tools; this module decides FileAccessMode / shell per entry.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode

from app.services.agent.tool_mount.surfaces import ExecutionSurface

if TYPE_CHECKING:
    from app.services.agent.profile.profile_resolver import BuiltinToolFlags

logger = logging.getLogger(__name__)


def resolve_agent_mount(
    surface: ExecutionSurface,
    profile_flags: BuiltinToolFlags,
    *,
    cron_job_tools_allowed: tuple[str, ...] | None = None,
) -> BuiltinToolFlags:
    """Apply entry-surface meta mount policy on top of profile entitlement flags.

    - ``WEB_FAST``: no write/shell meta tools; UECD read-only ``file_read_tool`` only.
    - General surfaces: force file + shell meta tools (agent baseline).
    - ``CRON`` with ``cron_job_tools_allowed``: honor intersected allow-list only.
    """

    if surface == ExecutionSurface.WEB_FAST:
        return _with_meta_mount(
            profile_flags,
            file_access_mode=FileAccessMode.SPILL_AND_UPLOADS,
            enable_shell_tools=False,
        )

    if surface == ExecutionSurface.CRON and cron_job_tools_allowed is not None:
        return profile_flags

    return _with_meta_mount(
        profile_flags,
        file_access_mode=FileAccessMode.FULL,
        enable_shell_tools=True,
    )


def apply_ptc_meta_mount(
    file_access_mode: FileAccessMode,
    enable_shell_tools: bool,
    *,
    has_mcp: bool,
) -> tuple[FileAccessMode, bool]:
    """PTC dependency injection at factory time.

    MCP/PTC skills require file + shell. Never override an explicit shell-off
    mount (Fast track or Cron ``tools_allowed`` without ``code_execute``).
    """
    if not has_mcp or not enable_shell_tools:
        return file_access_mode, enable_shell_tools

    if file_access_mode == FileAccessMode.FULL and enable_shell_tools:
        return file_access_mode, enable_shell_tools

    logger.info("PTC auto-inject: forcing file_access_mode=FULL, shell_tools=True (MCP skills present)")
    return FileAccessMode.FULL, True


def _with_meta_mount(
    flags: BuiltinToolFlags,
    *,
    file_access_mode: FileAccessMode | None = None,
    enable_shell_tools: bool | None = None,
) -> BuiltinToolFlags:
    from app.services.agent.profile.profile_resolver import BuiltinToolFlags

    resolved_file_access = file_access_mode if file_access_mode is not None else flags["file_access_mode"]
    resolved_shell = enable_shell_tools if enable_shell_tools is not None else flags["enable_shell_tools"]
    return BuiltinToolFlags(
        enable_browser=flags["enable_browser"],
        enable_computer_use=flags["enable_computer_use"],
        file_access_mode=resolved_file_access,
        enable_shell_tools=resolved_shell,
        enable_wiki=flags["enable_wiki"],
        enable_kanban=flags["enable_kanban"],
        enable_cron_eager=flags["enable_cron_eager"],
        enable_answer_tool=flags["enable_answer_tool"],
        enable_render_ui=flags["enable_render_ui"],
        enable_planning=flags["enable_planning"],
        enable_structured_clarify=flags["enable_structured_clarify"],
        enable_external_cli=flags["enable_external_cli"],
        enable_skill_market=flags["enable_skill_market"],
        enable_skill_manage=flags["enable_skill_manage"],
    )
