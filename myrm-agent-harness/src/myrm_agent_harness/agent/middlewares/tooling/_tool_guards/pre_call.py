"""[INPUT]
- .shared::PreCallResult / _emit_loop_guard_event (POS: 共用事件与阶段间状态)
- agent.middlewares.tooling._circuit_breaker::check_circuit_breaker (POS: 硬熔断器)
- agent.middlewares.tooling._tool_helpers (POS: 无状态助手)
- agent.security.guards.estop::check_estop (POS: 全局急停)
- agent.security.guards.loop_guard::CallRecord / LoopAction / LoopGuard (POS: 会话级循环检测)
- agent.security.guards.tool_turn_budget_guard (POS: 每回合高成本工具预算)
- utils.runtime.steering (POS: steering token)
- utils.token_economics.tracker::get_token_tracker (POS: token 追踪器)
- agent.security.audit::record_decision (POS: 安全审计)

[OUTPUT]
- run_pre_call_guards: 依次执行全部调用前守卫

[POS]
`_tool_guards/` 的调用前阶段；阻断时返回错误 ToolMessage，放行时返回 PreCallResult。
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import ToolCallRequest
from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.errors.tool_error_category import ToolErrorCategory
from myrm_agent_harness.agent.middlewares.tooling._circuit_breaker import check_circuit_breaker
from myrm_agent_harness.agent.middlewares.tooling._model_round import model_round_id
from myrm_agent_harness.agent.middlewares.tooling._tool_helpers import (
    check_tool_params_pii,
    check_trust_attenuation,
    make_error_msg,
)
from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.guards.estop import EStopLevel, check_estop
from myrm_agent_harness.agent.security.guards.loop_guard import LoopAction
from myrm_agent_harness.agent.security.guards.tool_turn_budget_guard import (
    TurnBudgetAction,
    get_tool_turn_budget_guard,
    resolve_turn_budget_units,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.runtime.steering import (
    STEERING_SKIP_MESSAGE,
    get_steering_token,
)
from myrm_agent_harness.utils.token_economics.tracker import get_token_tracker

from .shared import PreCallResult, _emit_loop_guard_event

logger = get_agent_logger(__name__)


async def run_pre_call_guards(
    request: ToolCallRequest,
    tool_name: str,
    tool_call_id: str,
    tool_args: dict[str, object],
    get_loop_guard_fn: Any = None,
) -> ToolMessage | PreCallResult:
    """Execute all pre-call guards. Returns ToolMessage if blocked, PreCallResult to proceed."""
    from myrm_agent_harness.agent.hooks.executor import fire_hook
    from myrm_agent_harness.agent.hooks.types import HookEvent
    from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
        set_current_message_id,
    )
    from myrm_agent_harness.agent.middlewares._session_context import (
        get_active_message_id,
    )

    active_message_id = get_active_message_id()
    if active_message_id:
        set_current_message_id(active_message_id)

    if get_loop_guard_fn is None:
        from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import (
            get_loop_guard as get_loop_guard_fn,
        )

    pre_hook_result = await fire_hook(
        HookEvent.PRE_TOOL_USE,
        {"tool_name": tool_name, "tool_input": tool_args, "tool_call_id": tool_call_id},
    )
    if pre_hook_result.blocked:
        record_decision(tool_name, "HOOK_BLOCKED", pre_hook_result.reason, tool_call_id=tool_call_id)
        return make_error_msg(
            tool_name,
            tool_call_id,
            f"Blocked by hook: {pre_hook_result.reason}",
            error_category=ToolErrorCategory.HOOK_BLOCKED,
        )
    if pre_hook_result.updated_input is not None:
        tool_args.clear()
        tool_args.update(pre_hook_result.updated_input)
        request.tool_call["args"] = tool_args

    blocked = check_circuit_breaker(tool_name, tool_call_id)
    if blocked:
        return blocked

    estop_state = check_estop()
    if estop_state is not None:
        record_decision(
            tool_name,
            "ESTOP_BLOCKED",
            f"E-Stop active: {estop_state.level} — {estop_state.reason}",
            tool_call_id=tool_call_id,
        )
        msg = f"E-Stop active ({estop_state.level}): all tool execution is suspended. Reason: {estop_state.reason}"
        if estop_state.level == EStopLevel.KILL_ALL:
            msg = f"EMERGENCY: {msg}"
        return make_error_msg(tool_name, tool_call_id, msg, error_category=ToolErrorCategory.ESTOP)

    loop_guard = get_loop_guard_fn()
    tracker = get_token_tracker()
    if tracker and tracker.usage.last_call:
        loop_guard.feed_output_tokens(
            tracker.call_count,
            tracker.usage.last_call.completion_tokens,
            has_tool_call=True,
        )

    try:
        loop_verdict = loop_guard.pre_check(tool_name, tool_args, round_id=model_round_id(request.state, tool_call_id))
    except Exception as pre_check_exc:
        from myrm_agent_harness.agent.errors.agent_errors import (
            RunawayCircuitBreakException,
            ToolStuckException,
        )

        if isinstance(pre_check_exc, RunawayCircuitBreakException):
            logger.error(
                "RunawayCircuitBreakException triggered in unattended mode [%s]: %s",
                tool_name,
                pre_check_exc,
            )
            # Do NOT swallow with interrupt or ToolMessage: escalate directly out of LangGraph
            # to let Server stop runaway loops and prevent retries.
            raise pre_check_exc

        if isinstance(pre_check_exc, ToolStuckException):
            from langgraph.types import interrupt

            logger.warning("ToolStuckException → GraphInterrupt [%s]: %s", tool_name, str(pre_check_exc)[:200])
            interrupt(pre_check_exc.interrupt_payload(tool_name, tool_call_id))
            return make_error_msg(
                tool_name,
                tool_call_id,
                f"Error: {pre_check_exc}",
                error_category=ToolErrorCategory.LOOP_GUARD,
                loop_kind="tool_stuck",
            )
        raise pre_check_exc

    # The record ``pre_check`` just opened is this call's own. Calls run concurrently, so it is taken here, before
    # any await lets another call open a record of its own.
    call_record = loop_guard.latest_record()

    metrics = loop_guard.get_metrics()
    if metrics.total_calls % 100 == 0 and metrics.total_calls > 0:
        logger.info(
            "Loop guard: %d calls, detection_rate=%.1f%%, avg_streak=%.1f, "
            "param_change=%.1f%%, effective_follow=%.1f%%",
            metrics.total_calls,
            metrics.detection_rate * 100,
            metrics.avg_streak,
            metrics.param_change_rate * 100,
            metrics.effective_follow_rate * 100,
        )

    if loop_verdict.action == LoopAction.BREAK:
        raw_loop_kind = getattr(loop_verdict, "loop_kind", None)
        loop_kind = raw_loop_kind if isinstance(raw_loop_kind, str) else "loop_break"

        if loop_kind == "sandbox_boundary":
            record_decision(tool_name, "SANDBOX_BOUNDARY_ESCALATE", loop_verdict.reason, tool_call_id=tool_call_id)
            logger.warning("Sandbox boundary escalation: %s -- %s", tool_name, loop_verdict.reason)
            await _emit_loop_guard_event("sandbox_boundary", tool_name, loop_kind, "error")
            return make_error_msg(
                tool_name,
                tool_call_id,
                f"Error: {loop_verdict.reason}\n\nYour goal will be paused for human review.",
                error_category=ToolErrorCategory.SANDBOX_BOUNDARY,
                loop_kind=loop_kind,
            )

        record_decision(tool_name, "LOOP_BREAK", loop_verdict.reason, tool_call_id=tool_call_id)
        logger.warning("Loop break: %s -- %s", tool_name, loop_verdict.reason)
        await _emit_loop_guard_event("loop_guard_break", tool_name, loop_kind, "error")
        return make_error_msg(
            tool_name,
            tool_call_id,
            f"Error: {loop_verdict.reason}\n\nHint: {loop_verdict.backoff_hint}",
            error_category=ToolErrorCategory.LOOP_GUARD,
            loop_kind=loop_kind,
        )
    if loop_verdict.action == LoopAction.WARN:
        record_decision(tool_name, "LOOP_WARN", loop_verdict.reason, tool_call_id=tool_call_id)
        logger.warning("Loop warning: %s -- %s", tool_name, loop_verdict.reason)
        await _emit_loop_guard_event("loop_guard_warn", tool_name, loop_verdict.loop_kind, "warning")

    turn_budget_guard = get_tool_turn_budget_guard()
    turn_budget_units = resolve_turn_budget_units(tool_name, tool_args)
    turn_budget_verdict = turn_budget_guard.check(
        tool_name,
        message_id=active_message_id,
        units=turn_budget_units,
    )
    if turn_budget_verdict.action == TurnBudgetAction.BREAK:
        record_decision(tool_name, "TURN_BUDGET_BREAK", turn_budget_verdict.reason, tool_call_id=tool_call_id)
        logger.warning("Turn budget break: %s -- %s", tool_name, turn_budget_verdict.reason)
        unit_label = "search queries" if tool_name == "web_search_tool" else "calls"
        return make_error_msg(
            tool_name,
            tool_call_id,
            f"Error: {turn_budget_verdict.reason}\n\n"
            f"Tool: {turn_budget_verdict.tool_count}/{turn_budget_verdict.tool_limit} "
            f"{unit_label}, "
            f"{turn_budget_verdict.tool_remaining} remaining this turn.",
            error_category=ToolErrorCategory.TURN_BUDGET_GUARD,
        )

    steering_token = get_steering_token()
    if steering_token and steering_token.is_active:
        logger.warning("Steering skip: %s", tool_name)
        return make_error_msg(
            tool_name,
            tool_call_id,
            STEERING_SKIP_MESSAGE,
            error_category=ToolErrorCategory.STEERING,
        )

    if request.tool is None:
        error_content = (
            f"Error: '{tool_name}' is not a valid tool. Please retry.\n\n"
            "Hint: Do not confuse tools with skills. "
            "Tools are for LLM to call directly. "
            "Skills (ending with _skill) are operation manuals for certain workflows "
            "and cannot be called directly by LLM. "
            "You must first use skill_select_tool to select a skill, then learn from its documentation!"
        )
        logger.warning("Invalid tool call: %s", tool_name)
        return make_error_msg(
            tool_name,
            tool_call_id,
            error_content,
            error_category=ToolErrorCategory.INVALID_TOOL,
        )

    attenuation_msg = check_trust_attenuation(tool_name)
    if attenuation_msg:
        return make_error_msg(
            tool_name,
            tool_call_id,
            attenuation_msg,
            error_category=ToolErrorCategory.TRUST_ATTENUATION,
        )

    pii_block_msg = check_tool_params_pii(tool_name, tool_args)
    if pii_block_msg:
        return make_error_msg(
            tool_name,
            tool_call_id,
            pii_block_msg,
            error_category=ToolErrorCategory.PII_GUARD,
        )

    turn_budget_guard.record(
        tool_name,
        message_id=active_message_id,
        units=turn_budget_units,
    )

    return PreCallResult(
        loop_guard,
        loop_verdict,
        steering_token,
        call_record,
    )
