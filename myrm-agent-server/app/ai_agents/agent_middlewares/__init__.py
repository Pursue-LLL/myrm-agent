"""AI Agents 共享中间件 (Agent Middlewares)

为 GeneralAgent 提供可复用的 LangGraph Agent 中间件。

命名说明: 使用 agent_middlewares 而非 middlewares，避免与 FastAPI HTTP 中间件混淆。
"""

from myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware import (
    memory_context_middleware,
)

from .project_roadmap_middleware import project_roadmap_middleware
from .project_scoped_context_middleware import project_scoped_workspace_middleware
from .user_instructions_middleware import user_instructions_middleware
from .widget_capability_middleware import widget_capability_middleware

__all__ = [
    "memory_context_middleware",
    "project_roadmap_middleware",
    "project_scoped_workspace_middleware",
    "user_instructions_middleware",
    "widget_capability_middleware",
]
