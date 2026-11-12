"""[INPUT]
- app.ai_agents.general_agent.factory.builder::build_general_agent (POS: GeneralAgent 装配层。负责把业务配置、工具、存储、中间件和 LLM 组装为最终的可执行 Agent； 尊重用户在 WebUI 选择的主模型，failover 由 harness `stream_recovery` 在 API 报错时触发。)
- app.ai_agents.general_agent.factory.support::_build_session_cleanup_callback / _build_skill_review_callback / _resolve_kanban_default_board_id / _setup_kanban_tools / _should_enable_cron_tools / _should_enable_subagent_tools / _should_setup_computer_use_tools / _try_inject_mcp_oauth (POS: 与装配主流程分离的工具/Kanban/回调构造；只被 factory 包内部调用。)

[OUTPUT]
- build_general_agent
- _build_session_cleanup_callback
- _build_skill_review_callback
- _resolve_kanban_default_board_id
- _setup_kanban_tools
- _should_enable_cron_tools
- _should_enable_subagent_tools
- _should_setup_computer_use_tools
- _try_inject_mcp_oauth

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
