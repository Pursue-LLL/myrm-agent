"""AI Agents 共享中间件 (Agent Middlewares)

为 GeneralAgent 提供可复用的 LangGraph Agent 中间件。

命名说明: 使用 agent_middlewares 而非 middlewares，避免与 FastAPI HTTP 中间件混淆。

[INPUT]
- myrm_agent_harness.agent.middlewares.memory_context::ephemeral_delta_middleware, memory_context_middleware, proactive_pack_middleware, two_layer_context_middleware (POS: 框架层记忆注入与 Human 尾部注入中间件)
- 本目录::project_roadmap_middleware, user_instructions_middleware, widget_capability_middleware (POS: 业务层提示词注入中间件)

[OUTPUT]
- 上述全部中间件与 PROACTIVE_PACK_CONTEXT_KEY（知识包在运行上下文里的键）：供 GeneralAgent 工厂装配与回合 setup 使用

[POS]
GeneralAgent 中间件的统一出口，把框架层与业务层中间件聚合到 `app.ai_agents.agent_middlewares` 一个命名空间。
"""

from myrm_agent_harness.agent.middlewares.memory_context.ephemeral_delta_middleware import (
    ephemeral_delta_middleware,
)
from myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware import (
    memory_context_middleware,
)
from myrm_agent_harness.agent.middlewares.memory_context.proactive_pack_middleware import (
    PROACTIVE_PACK_CONTEXT_KEY,
    proactive_pack_middleware,
)
from myrm_agent_harness.agent.middlewares.memory_context.two_layer_context_middleware import (
    two_layer_context_middleware,
)

from .project_roadmap_middleware import project_roadmap_middleware
from .user_instructions_middleware import user_instructions_middleware
from .widget_capability_middleware import widget_capability_middleware

__all__ = [
    "PROACTIVE_PACK_CONTEXT_KEY",
    "ephemeral_delta_middleware",
    "memory_context_middleware",
    "proactive_pack_middleware",
    "two_layer_context_middleware",
    "project_roadmap_middleware",
    "user_instructions_middleware",
    "widget_capability_middleware",
]
