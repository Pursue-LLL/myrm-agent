"""GeneralAgent 装配包门面。

[OUTPUT]
build_general_agent 及内部测试使用的工具/Kanban/回调构造函数。

[POS]
`app.ai_agents.general_agent.factory` 的唯一入口；实现位于 builder/support 等子模块。
"""

from app.ai_agents.general_agent.factory.builder import build_general_agent
from app.ai_agents.general_agent.factory.support import (
    _build_session_cleanup_callback,
    _build_skill_review_callback,
    _resolve_kanban_default_board_id,
    _setup_kanban_tools,
    _should_enable_cron_tools,
    _should_enable_subagent_tools,
    _should_setup_computer_use_tools,
    _try_inject_mcp_oauth,
)

__all__ = [
    "_build_session_cleanup_callback",
    "_build_skill_review_callback",
    "_resolve_kanban_default_board_id",
    "_setup_kanban_tools",
    "_should_enable_cron_tools",
    "_should_enable_subagent_tools",
    "_should_setup_computer_use_tools",
    "_try_inject_mcp_oauth",
    "build_general_agent",
]
