"""[INPUT]
- .shared::_emit_loop_guard_event (POS: 共用事件)
- agent.middlewares.tooling._tool_helpers (POS: 无状态助手)
- agent.security.guards.context_budget (POS: 会话级上下文预算)
- agent.security.guards.loop_guard (POS: 会话级循环检测)
- semantic_failure_sniffer (POS: 语义失败嗅探)
- agent.security.audit::record_decision (POS: 安全审计)

[OUTPUT]
- run_post_call_guards: 预算截断、投毒检测、污点、hook 校验与循环记录

[POS]
`_tool_guards/` 的调用后阶段；只改工具结果，不阻止调用。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.middlewares.tooling._tool_helpers import (
    apply_validation_result,
    build_hook_failure_result,
    check_tool_result_pii,
    emit_archive_restore_block_status,
    emit_hook_failure_event,
    extract_text_content,
    run_content_validation,
)
from myrm_agent_harness.agent.middlewares.tooling.semantic_failure_sniffer import (
    elevate_semantic_failure_observation,
    sniff_semantic_failure,
)
from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.guards.context_budget import (
    BudgetAction,
    get_context_budget_guard,
)
from myrm_agent_harness.agent.security.guards.loop_guard import CallRecord, LoopAction, LoopGuard
from myrm_agent_harness.utils.logger_utils import get_agent_logger

from .shared import _emit_loop_guard_event

logger = get_agent_logger(__name__)

async def run_post_call_guards(
    result: ToolMessage | Any,
    tool_name: str,
    tool_call_id: str,
    tool_args: dict[str, object],
    loop_guard: LoopGuard,
    loop_verdict: Any,
    steering_token: Any,
    call_record: CallRecord | None = None,
) -> ToolMessage | Any:
    """Execute all post-call guards on a ToolMessage. Returns (possibly modified) result.

    ``call_record`` is the loop-guard record the pre-call phase opened for this call; the result and the
    verification category are written to it, not to whichever record is latest by now. Without one the result
    goes to the latest record and no verification category is recorded.
    """
    from myrm_agent_harness.agent.hooks.executor import fire_hook
    from myrm_agent_harness.agent.hooks.types import HookEvent
    from myrm_agent_harness.agent.streaming.types import AgentEventType

    if steering_token and steering_token.has_pending:
        steering_token.activate()

    if not isinstance(result, ToolMessage):
        return result

    result_text = extract_text_content(result.content)
    untruncated_text = result_text

    if not result_text.strip():
        result_text = "(no output)"
        result = ToolMessage(
            content=result_text,
            name=tool_name,
            tool_call_id=result.tool_call_id,
            status=result.status,
            additional_kwargs=result.additional_kwargs,
        )

    await emit_archive_restore_block_status(result_text, tool_name)

    # Semantic Failure Sniffer: Catch HTTP 200 pseudo-success business errors
    if result.status != "error":
        sniff_res = sniff_semantic_failure(
            result_text,
            tool_name=tool_name,
            tool_args=dict(tool_args),
        )
        if sniff_res.is_failure:
            elevated_content = elevate_semantic_failure_observation(sniff_res, result_text)
            extra_kwargs = dict(result.additional_kwargs or {})
            extra_kwargs["error_category"] = sniff_res.failure_type.value
            extra_kwargs["semantic_failure_reason"] = sniff_res.reason
            if sniff_res.extracted_code is not None:
                extra_kwargs["extracted_code"] = sniff_res.extracted_code
            result = ToolMessage(
                content=elevated_content,
                name=tool_name,
                tool_call_id=result.tool_call_id,
                status="error",
                additional_kwargs=extra_kwargs,
            )
            result_text = elevated_content

    from myrm_agent_harness.agent.middlewares.tooling._mutation_verifier import (
        record_mutation_result,
    )

    record_mutation_result(
        tool_name=tool_name,
        tool_args=dict(tool_args),
        is_error=(result.status == "error"),
        error_content=result_text if result.status == "error" else None,
    )

    budget_guard = get_context_budget_guard()
    budget_verdict = budget_guard.check_and_truncate(result_text, tool_name)
    if budget_verdict.action == BudgetAction.PERSISTED:
        record_decision(tool_name, "CONTEXT_PERSISTED", budget_verdict.reason, tool_call_id=tool_call_id)
        logger.info(
            "Context budget persisted: %s -> %s",
            tool_name,
            budget_verdict.persisted_path,
        )
        if budget_verdict.evicted_ref:
            from myrm_agent_harness.agent.context_management.infra.evicted import (
                emit_evicted_ref,
            )

            await emit_evicted_ref(
                budget_verdict.evicted_ref,
                tool_name=tool_name,
                tool_call_id=result.tool_call_id,
                preview_stdout=(budget_verdict.content if isinstance(budget_verdict.content, str) else None),
                stored_chars=budget_verdict.stored_chars,
                total_lines=budget_verdict.total_lines,
                storage_truncated=budget_verdict.storage_truncated,
            )
        result = ToolMessage(
            content=budget_verdict.content,
            name=tool_name,
            tool_call_id=result.tool_call_id,
            status=result.status,
            additional_kwargs=result.additional_kwargs,
        )
        result_text = budget_verdict.content
    elif budget_verdict.action == BudgetAction.TRUNCATED:
        record_decision(tool_name, "CONTEXT_TRUNCATED", budget_verdict.reason, tool_call_id=tool_call_id)
        logger.warning("Context budget truncated: %s -- %s", tool_name, budget_verdict.reason)
        result = ToolMessage(
            content=budget_verdict.content,
            name=tool_name,
            tool_call_id=result.tool_call_id,
            status=result.status,
            additional_kwargs=result.additional_kwargs,
        )
        result_text = budget_verdict.content
    elif budget_verdict.action == BudgetAction.WARNING:
        logger.warning("Context budget warning: %s", budget_verdict.reason)

    validation = run_content_validation(result_text, tool_name)
    if validation is not None:
        logger.warning("Context poisoning [%s]: %s", tool_name, validation.reason)
        result = apply_validation_result(result, validation, tool_name)

    from myrm_agent_harness.agent.security.guards.taint_tracker import get_taint_tracker

    get_taint_tracker().record_tool_output(tool_name, tool_input=tool_args)

    result, result_text = check_tool_result_pii(result, result_text, tool_name)

    from myrm_agent_harness.agent.workspace_rules.tracker import (
        check_and_append_rules,
    )

    rules_append = check_and_append_rules(tool_name, tool_args, result_text)
    if rules_append and isinstance(result.content, str):
        result = ToolMessage(
            content=f"{result.content}\n{rules_append}",
            name=tool_name,
            tool_call_id=result.tool_call_id,
            status=result.status,
            additional_kwargs=result.additional_kwargs,
        )
        result_text = extract_text_content(result.content)

    try:
        post_verdict = loop_guard.record_result(
            tool_name, tool_args, result_text, record=call_record, errored=result.status == "error"
        )
    except Exception as post_check_exc:
        from myrm_agent_harness.agent.errors.agent_errors import (
            RunawayCircuitBreakException,
            ToolStuckException,
        )

        if isinstance(post_check_exc, RunawayCircuitBreakException):
            logger.error(
                "RunawayCircuitBreakException triggered in unattended mode (post-result) [%s]: %s",
                tool_name,
                post_check_exc,
            )
            raise post_check_exc
        if isinstance(post_check_exc, ToolStuckException):
            logger.warning(
                "ToolStuckException raised during record_result [%s]: %s",
                tool_name,
                str(post_check_exc)[:200],
            )
        raise post_check_exc

    if post_verdict.action == LoopAction.BREAK:
        post_loop_kind = getattr(post_verdict, "loop_kind", None)
        if post_loop_kind == "sandbox_boundary":
            record_decision(tool_name, "SANDBOX_BOUNDARY_ESCALATE", post_verdict.reason, tool_call_id=tool_call_id)
            logger.warning("Sandbox boundary (post-call): %s -- %s", tool_name, post_verdict.reason)
            await _emit_loop_guard_event("sandbox_boundary", tool_name, post_loop_kind, "error")
        else:
            record_decision(tool_name, "LOOP_BREAK", post_verdict.reason, tool_call_id=tool_call_id)
            logger.warning("Loop output break: %s -- %s", tool_name, post_verdict.reason)
            await _emit_loop_guard_event("loop_guard_break", tool_name, post_loop_kind, "error")
    elif post_verdict.action == LoopAction.WARN:
        record_decision(tool_name, "LOOP_WARN", post_verdict.reason, tool_call_id=tool_call_id)
        logger.warning("Loop output warning: %s -- %s", tool_name, post_verdict.reason)
        await _emit_loop_guard_event("loop_guard_warn", tool_name, post_verdict.loop_kind, "warning")

    if tool_name == "bash_code_execute_tool" and call_record is not None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.verification import tag_verification_call

        tag_verification_call(call_record, tool_args, untruncated_text)

    warnings: list[str] = []
    if loop_verdict.action == LoopAction.WARN or post_verdict.action == LoopAction.WARN:
        hint = loop_verdict.backoff_hint or post_verdict.backoff_hint
        if hint:
            warnings.append(f"Loop detected: {hint}")

    if warnings and isinstance(result.content, str):
        warning_text = "\n\n".join(warnings)
        result = ToolMessage(
            content=f"{result.content}\n\n{warning_text}",
            name=tool_name,
            tool_call_id=result.tool_call_id,
            status=result.status,
            additional_kwargs=result.additional_kwargs,
        )

    post_result_text = extract_text_content(result.content)
    post_hook_result = await fire_hook(
        HookEvent.POST_TOOL_USE,
        {
            "tool_name": tool_name,
            "tool_input": tool_args,
            "tool_output": post_result_text,
            "tool_call_id": tool_call_id,
        },
    )
    if post_hook_result.blocked or not post_hook_result.all_succeeded:
        result = build_hook_failure_result(result, post_hook_result, tool_name, tool_call_id, post_result_text)
        await emit_hook_failure_event(tool_name, post_hook_result, AgentEventType)

    return result
