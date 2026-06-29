"""AI Agents 共享中间件 (Agent Middlewares)

为 GeneralAgent 提供可复用的 LangGraph Agent 中间件。

命名说明: 使用 agent_middlewares 而非 middlewares，避免与 FastAPI HTTP 中间件混淆。
"""

from myrm_agent_harness.agent.middlewares.auto_session_recall_middleware import (
    auto_session_recall_middleware,
)
from myrm_agent_harness.agent.middlewares.memory_context_middleware import (
    memory_context_middleware,
)

from .user_instructions_middleware import user_instructions_middleware
from .widget_capability_middleware import widget_capability_middleware

__all__ = [
    "auto_session_recall_middleware",
    "memory_context_middleware",
    "user_instructions_middleware",
    "widget_capability_middleware",
]
