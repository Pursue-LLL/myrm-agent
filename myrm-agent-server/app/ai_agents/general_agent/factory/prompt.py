"""GeneralAgent 的系统提示词组装。

[POS]
装配第五阶段；按模式、桌面/CLI 挂载与会话根目录拼接最终提示词。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor

    from app.ai_agents.general_agent.agent import GeneralAgent
    from app.ai_agents.general_agent.mount_resolver import ResolvedMountPlan

logger = logging.getLogger(__name__)


def build_system_prompt(
    agent_wrapper: "GeneralAgent",
    *,
    mount_plan: "ResolvedMountPlan",
    executor: "CodeExecutor | None",
    channel_notify_tool_loaded: bool,
    prompt_locale: str | None,
) -> str:
    from app.ai_agents.prompts.general_agent_prompt import coerce_prompt_mode, get_core_system_prompt

    system_prompt = get_core_system_prompt(
        mode=coerce_prompt_mode(agent_wrapper.prompt_mode),
        enable_answer_tool=agent_wrapper.enable_answer_tool,
        locale=prompt_locale,
    )

    if agent_wrapper.prompt_mode == "search" and getattr(agent_wrapper, "search_depth", "normal") == "deep":
        from myrm_agent_harness.utils.locale import is_chinese

        from app.ai_agents.prompts.general_agent_prompt import (
            SEARCH_DEEP_SUFFIX,
            SEARCH_DEEP_SUFFIX_ZH,
        )

        system_prompt += SEARCH_DEEP_SUFFIX_ZH if is_chinese(prompt_locale) else SEARCH_DEEP_SUFFIX

    if getattr(agent_wrapper, "unattended_mode", False):
        system_prompt += (
            "\n\n[Unattended Mode] You are running without human supervision. "
            "Do not ask the user for clarification or approval. "
            "Make reasonable decisions independently and proceed to completion."
        )

    from app.ai_agents.general_agent.kanban_tool_mode import resolve_kanban_tool_mode

    if (
        resolve_kanban_tool_mode(
            kanban_tool_mode=getattr(agent_wrapper, "kanban_tool_mode", None),
            kanban_current_task_id=getattr(agent_wrapper, "kanban_current_task_id", None),
        )
        == "worker"
    ):
        from myrm_agent_harness.toolkits.kanban import get_worker_lifecycle_guidance

        system_prompt += get_worker_lifecycle_guidance(
            zombie_timeout_seconds=getattr(agent_wrapper, "kanban_zombie_timeout_seconds", 120),
            max_runtime_seconds=getattr(agent_wrapper, "kanban_max_runtime_seconds", None),
        )

    if mount_plan.mount_desktop_prompt:
        from app.ai_agents.prompts.shared_rules import DESKTOP_CONTROL_RULES

        system_prompt += DESKTOP_CONTROL_RULES

    if executor is not None and mount_plan.mount_cli_context:
        try:
            from myrm_agent_harness.toolkits.code_execution.tool_discovery import (
                get_cli_tools_context,
            )

            cli_ctx = get_cli_tools_context()
            if cli_ctx:
                system_prompt += cli_ctx
        except Exception as e:
            logger.warning("CLI tool discovery failed (degraded): %s", e)

    if channel_notify_tool_loaded:
        from app.services.agent.outbound_notify.types import (
            CHANNEL_NOTIFY_SYSTEM_APPENDIX,
        )

        system_prompt += CHANNEL_NOTIFY_SYSTEM_APPENDIX

    session_roots_raw = getattr(agent_wrapper, "session_access_roots", None)
    if session_roots_raw and isinstance(session_roots_raw, (list, tuple)):
        roots_lines = [
            f"- {str(r.get('path'))} ({'read-write' if r.get('writable', True) else 'read-only'})"
            for r in sorted(
                session_roots_raw,
                key=lambda x: str(x.get("path", "")) if isinstance(x, dict) else "",
            )
            if isinstance(r, dict) and r.get("path")
        ]
        if roots_lines:
            system_prompt += (
                "\n\n[Mounted Workspace Directories]\n"
                "The following local directories are granted for this session:\n"
                + "\n".join(roots_lines)
                + "\nYou can read, search, and operate on files within these directories directly using tools."
            )

    return system_prompt
