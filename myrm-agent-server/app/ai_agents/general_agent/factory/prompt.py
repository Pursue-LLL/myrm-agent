"""[INPUT]
- app.ai_agents.general_agent.agent::GeneralAgent (POS: 通用 Agent 核心实现。管理 Agent 生命周期（初始化、流式执行、资源释放），)
- app.ai_agents.general_agent.mount_resolver::ResolvedMountPlan (POS: Pure resolver layer between channel ingress and GeneralAgent factory wiring.)
- app.ai_agents.prompts.general_agent_prompt::coerce_prompt_mode / get_core_system_prompt / SEARCH_DEEP_SUFFIX / SEARCH_DEEP_SUFFIX_ZH (POS: GeneralAgent 核心系统提示词。支持四档 Prompt Mode（full/lean/naked/search）与中英双语（默认英文），)
- app.ai_agents.general_agent.kanban_tool_mode::resolve_kanban_tool_mode (POS: GeneralAgent factory 的 Kanban 工具 bind 解析辅助模块；TaskRunner 强制 worker，chat 默认 orchestrator。)
- myrm_agent_harness.utils.locale::is_chinese (POS: Shared locale utilities consumed by channel i18n, error diagnostics, and)
- myrm_agent_harness.toolkits.kanban::get_worker_lifecycle_guidance (POS: Kanban toolkit entry point. Aggregates dispatcher, protocols, built-in)
- app.ai_agents.prompts.shared_rules::DESKTOP_CONTROL_RULES (POS: 跨 Agent 共享规则常量。供多个 Agent 提示词复用的通用规则片段，除桌面控制外均支持中英双语，提供任务完整性、桌面控制等核心护栏；用户指令的优先级只由 user_instructions 消息头声明。桌面控制规则是底层工具调用协议，只有英文版，由 factory 注入。)
- app.services.agent.outbound_notify.types::CHANNEL_NOTIFY_SYSTEM_APPENDIX (POS: Data types for agent-initiated outbound channel notifications.)

[OUTPUT]
- build_system_prompt: build_system_prompt

[POS]
装配第五阶段；按模式、桌面挂载与会话根目录拼接最终提示词。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai_agents.general_agent.agent import GeneralAgent
    from app.ai_agents.general_agent.mount_resolver import ResolvedMountPlan


def build_system_prompt(
    agent_wrapper: "GeneralAgent",
    *,
    mount_plan: "ResolvedMountPlan",
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

    if mount_plan.mount_computer_use:
        from app.ai_agents.prompts.shared_rules import DESKTOP_CONTROL_RULES

        system_prompt += DESKTOP_CONTROL_RULES

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
