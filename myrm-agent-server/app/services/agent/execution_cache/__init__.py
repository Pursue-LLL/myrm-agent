"""Chat-scoped SkillAgent execution cache public exports.

[INPUT]
- execution_cache.registry::get_execution_cache (POS: chat 级 BuiltExecutionUnit 池)
- execution_cache.session_lifecycle::finalize_agent_session (POS: pooled/ephemeral 收尾)

[OUTPUT]
- ChatAgentExecutionCache, ExecutionMode, fingerprint helpers, unit apply/capture

[POS]
execution_cache 包入口。WebUI/Channel 复用 BuiltExecutionUnit；Cron/Eval 走 ephemeral。
"""

from app.services.agent.execution_cache.fingerprint import (
    build_execution_scope_key,
    compute_execution_fingerprint,
)
from app.services.agent.execution_cache.registry import (
    ChatAgentExecutionCache,
    close_execution_cache_for_chat,
    close_execution_cache_for_chat_all_agents,
    get_execution_cache,
)
from app.services.agent.execution_cache.session_lifecycle import (
    finalize_agent_session,
    resolve_execution_mode,
)
from app.services.agent.execution_cache.types import BuiltExecutionUnit, ExecutionMode
from app.services.agent.execution_cache.unit_ops import (
    apply_built_unit,
    capture_built_unit,
    detach_wrapper_refs,
)

__all__ = [
    "BuiltExecutionUnit",
    "ChatAgentExecutionCache",
    "ExecutionMode",
    "apply_built_unit",
    "build_execution_scope_key",
    "capture_built_unit",
    "close_execution_cache_for_chat",
    "close_execution_cache_for_chat_all_agents",
    "compute_execution_fingerprint",
    "detach_wrapper_refs",
    "finalize_agent_session",
    "get_execution_cache",
    "resolve_execution_mode",
]
