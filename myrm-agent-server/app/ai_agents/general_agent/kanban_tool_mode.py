"""[INPUT]
- myrm_agent_harness.toolkits.kanban.kanban_agent_tools::KanbanToolMode (POS: harness Kanban 工具模式枚举)
- GeneralAgent.kanban_tool_mode / kanban_current_task_id (POS: 业务层 Kanban 绑定参数)

[OUTPUT]
- resolve_kanban_tool_mode(): 解析 LLM 侧应 bind 的 Kanban 工具集模式

[POS]
GeneralAgent factory 的 Kanban 工具 bind 解析辅助模块；TaskRunner 强制 worker，chat 默认 orchestrator。
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.kanban import KanbanToolMode

_KANBAN_TOOL_MODES: frozenset[KanbanToolMode] = frozenset({"worker", "orchestrator", "full"})


def resolve_kanban_tool_mode(
    *,
    kanban_tool_mode: str | None,
    kanban_current_task_id: str | None,
) -> KanbanToolMode:
    """Resolve harness KanbanToolMode for LLM tool binding.

    Task-bound runs (Kanban TaskRunner) always use worker tools. Chat agents with
    kanban enabled default to orchestrator (8 tools). Full (16) remains opt-in.
    """
    if kanban_current_task_id:
        return "worker"
    mode = (kanban_tool_mode or "orchestrator").strip()
    if mode not in _KANBAN_TOOL_MODES:
        return "orchestrator"
    return mode
