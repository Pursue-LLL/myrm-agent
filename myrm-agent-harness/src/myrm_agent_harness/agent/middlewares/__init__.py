"""Agent middleware system.

[OUTPUT]
- create_context_pipeline_middleware(): 上下文管道中间件工厂函数
- debug_logger_middleware: 调试日志中间件
- tool_interceptor_middleware: 工具拦截中间件
- ToolConflictGateMiddleware: 工具冲突闸门中间件类
- PlanConfirmMiddleware: Plan-phase HITL 中间件类
- reset_plan_confirm_state(): 重置 plan confirm 状态
- ValidationResult: 验证结果数据类（security 模块的再导出）
- validate_tool_result(): 工具结果验证函数（security 模块的再导出）

[POS]
Agent middleware system exports. Provides the complete middleware stack (context management, debug logging, tool interception).

"""

from myrm_agent_harness.agent.middlewares._session_context import (
    get_delegation_token,
)
from myrm_agent_harness.agent.middlewares.advisor_risk_trigger_router import (
    AdvisorRiskTriggerRouter,
    RiskTriggerDecision,
    RiskTriggerReason,
    is_unrecoverable_fatal_error,
)
from myrm_agent_harness.agent.middlewares.approval import (
    ApprovalRateLimiter,
    get_approval_rate_limiter,
)
from myrm_agent_harness.agent.middlewares.completion import (
    CompletionGuard,
    reset_completion_guard,
)
from myrm_agent_harness.agent.middlewares.concurrency.tool_conflict_gate import (
    ToolConflictGateMiddleware,
)
from myrm_agent_harness.agent.middlewares.context_pipeline.context_pipeline_middleware import (
    create_context_pipeline_middleware,
)
from myrm_agent_harness.agent.middlewares.debug_logger_middleware import (
    debug_logger_middleware,
)
from myrm_agent_harness.agent.middlewares.guardrails import (
    GuardrailMiddleware,
    SkillBoundaryProvider,
)
from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
    create_moa_advisor_middleware,
)
from myrm_agent_harness.agent.middlewares.plan_confirm_middleware import (
    PlanConfirmMiddleware,
    reset_plan_confirm_state,
)
from myrm_agent_harness.agent.middlewares.progress_middleware import progress_middleware
from myrm_agent_harness.agent.middlewares.rate_limit import RateLimitMiddleware
from myrm_agent_harness.agent.middlewares.replan_middleware import (
    ReplanMiddleware,
    get_max_consecutive_replan_errors,
    get_replan_error_summary,
    reset_replan_attempts,
)
from myrm_agent_harness.agent.middlewares.subagent_limit_middleware import (
    subagent_limit_middleware,
)
from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import (
    notify_loop_guard_compaction,
    reset_loop_guard,
    tool_interceptor_middleware,
)
from myrm_agent_harness.agent.security.detection.tool_result_validator import (
    ValidationResult,
    validate_tool_result,
)

__all__ = [
    "AdvisorRiskTriggerRouter",
    "ApprovalRateLimiter",
    "CompletionGuard",
    "GuardrailMiddleware",
    "PlanConfirmMiddleware",
    "RateLimitMiddleware",
    "ReplanMiddleware",
    "RiskTriggerDecision",
    "RiskTriggerReason",
    "SkillBoundaryProvider",
    "ValidationResult",
    "create_context_pipeline_middleware",
    "create_moa_advisor_middleware",
    "ToolConflictGateMiddleware",
    "debug_logger_middleware",
    "get_approval_rate_limiter",
    "get_delegation_token",
    "get_max_consecutive_replan_errors",
    "get_replan_error_summary",
    "is_unrecoverable_fatal_error",
    "notify_loop_guard_compaction",
    "progress_middleware",
    "reset_completion_guard",
    "reset_loop_guard",
    "reset_plan_confirm_state",
    "reset_replan_attempts",
    "subagent_limit_middleware",
    "tool_interceptor_middleware",
    "validate_tool_result",
]
