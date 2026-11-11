"""Agent-loop MoA advisor overlay middleware.

Runs lightweight reference-model fan-out before each acting-model call (per
fanout policy), emits SSE progress events, and shows the advisors' perspectives
to the acting model without persisting them to checkpoint history.

The advice of a round is written once into the run's notice ledger, behind the
message that was last at that moment, and every later request of the run carries
it there unchanged. A reasoning block the provider signed is valid only under the
prompt it was written in, so a request that showed the advice followed by one
that did not (or showed it elsewhere) would be refused.

[INPUT]
- toolkits.llms.consensus.advisor_fanout::AdvisorFanoutRunner
- toolkits.llms.consensus.advisor_prompts::build_advisor_injection_block
- agent.middlewares._run_notices::NoticeLedger, last_stored_message, run_scope (POS: Request-local notices that keep their place and their text for the whole run.)
- utils.runtime.progress_sink::get_tool_progress_sink

[OUTPUT]
- create_moa_advisor_middleware(): factory returning wrap_model_call middleware

[POS]
Advisor injection for agent tool loops. Mount after context_pipeline
(server factory) so compression runs before fan-out. Skips unattended runs,
budget pressure (emits moa_overlay_skipped when fan-out would run), and when
overlay is disabled. Every round of a run keeps its advice, so under
``per_iteration`` the notes of a long run add up.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import TYPE_CHECKING

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse, wrap_model_call

from myrm_agent_harness.agent.middlewares._run_notices import NoticeLedger, last_stored_message, run_scope
from myrm_agent_harness.agent.middlewares.advisor_risk_trigger_router import (
    AdvisorRiskTriggerRouter,
)
from myrm_agent_harness.toolkits.llms.consensus.advisor_fanout import (
    AdvisorFanoutRunner,
    apply_privacy_to_ref,
    inject_privacy_mode,
    should_run_fanout,
    sse_privacy_mode,
)
from myrm_agent_harness.toolkits.llms.consensus.advisor_prompts import (
    build_advisor_injection_block,
)
from myrm_agent_harness.toolkits.llms.consensus.moa_overlay_types import (
    MoAOverlayConfig,
    PrivacyFilterMode,
)
from myrm_agent_harness.toolkits.llms.consensus.types import (
    PrivacyRedactor,
    ReferenceResponse,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

MOA_OVERLAY_SKIP_BUDGET_PRESSURE = "budget_pressure"
MOA_OVERLAY_SKIP_INSUFFICIENT_REFS = "insufficient_refs"
MOA_OVERLAY_SKIP_RISK_TIMEOUT = "risk_trigger_timeout"

_ADVICE_LEDGER_KEY = "moa_advisor_notice_ledger"

_moa_budget_skip_notified_var: ContextVar[bool] = ContextVar("moa_budget_skip_notified", default=False)


def _budget_pressure_active() -> bool:
    try:
        from myrm_agent_harness.utils.token_economics.tracker import get_token_tracker

        tracker = get_token_tracker()
        if tracker is None:
            return False
        status = getattr(tracker, "last_budget_status", "ok")
        return status not in ("ok", "")
    except Exception:
        return False


async def _emit_ref_done(ref_model: str, *, success: bool, elapsed: float, content: str | None) -> None:
    from myrm_agent_harness.utils.runtime.progress_sink import get_tool_progress_sink

    sink = get_tool_progress_sink()
    if sink is None:
        return
    await sink.emit(
        {
            "type": "status",
            "step_key": "moa_ref_done",
            "data": {
                "model": ref_model,
                "success": success,
                "elapsed": elapsed,
                "content": content,
            },
        }
    )


async def _emit_overlay_active(reference_models: list[str], trigger_reason: str | None = None) -> None:
    from myrm_agent_harness.utils.runtime.progress_sink import get_tool_progress_sink

    sink = get_tool_progress_sink()
    if sink is None:
        return
    payload: dict[str, object] = {"reference_models": reference_models}
    if trigger_reason:
        payload["trigger_reason"] = trigger_reason
    await sink.emit(
        {
            "type": "status",
            "step_key": "moa_overlay_active",
            "data": payload,
        }
    )


async def _emit_overlay_skipped(reason: str) -> None:
    from myrm_agent_harness.utils.runtime.progress_sink import get_tool_progress_sink

    sink = get_tool_progress_sink()
    if sink is None:
        return
    await sink.emit(
        {
            "type": "status",
            "step_key": "moa_overlay_skipped",
            "status": "warning",
            "data": {"reason": reason},
        }
    )


def _model_name(llm: BaseChatModel) -> str:
    for attr in ("model_name", "model", "name"):
        val = getattr(llm, attr, None)
        if val and isinstance(val, str):
            return val
    return type(llm).__name__


def create_moa_advisor_middleware(
    reference_llms: list[BaseChatModel],
    *,
    config: MoAOverlayConfig | None = None,
    unattended: bool = False,
    privacy_redactor: PrivacyRedactor | None = None,
    risk_router: AdvisorRiskTriggerRouter | None = None,
) -> AgentMiddleware:
    """Build MoA advisor overlay middleware bound to pre-resolved reference LLMs."""
    overlay_cfg = config or MoAOverlayConfig()
    runner = AdvisorFanoutRunner(reference_llms, overlay_cfg)
    privacy_mode: PrivacyFilterMode = overlay_cfg.privacy_filter
    router = (
        risk_router
        if risk_router is not None
        else (AdvisorRiskTriggerRouter(overlay_cfg) if overlay_cfg.fanout == "risk_triggered" else None)
    )

    @wrap_model_call(name="moa_advisor_middleware")
    async def _middleware(
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        if unattended:
            return await handler(request)

        messages = list(request.messages)
        ledger = NoticeLedger.of(run_scope(request), _ADVICE_LEDGER_KEY)

        async def forward() -> ModelResponse:
            # Advice of the run's earlier rounds stands behind its message on every request, this one included.
            return await handler(request.override(messages=ledger.placed_in(messages)))

        next_iteration = runner.iteration + 1
        trigger_reason: str | None = None

        if overlay_cfg.fanout == "risk_triggered":
            decision = router.evaluate_trigger(messages, current_turn=next_iteration) if router else None
            fanout_this_call = bool(decision and decision.should_trigger)
            if fanout_this_call and decision and decision.reason:
                trigger_reason = decision.reason.value
        else:
            fanout_this_call = should_run_fanout(
                messages=messages,
                fanout=overlay_cfg.fanout,
                every_n=overlay_cfg.every_n,
                iteration=next_iteration,
            )

        if overlay_cfg.fanout == "risk_triggered" and not fanout_this_call:
            return await forward()

        if _budget_pressure_active():
            if fanout_this_call and not _moa_budget_skip_notified_var.get():
                await _emit_overlay_skipped(MOA_OVERLAY_SKIP_BUDGET_PRESSURE)
                _moa_budget_skip_notified_var.set(True)
            logger.debug("MoA overlay skipped: budget pressure active")
            return await forward()

        if fanout_this_call:
            ref_names = [_model_name(llm) for llm in reference_llms]
            await _emit_overlay_active(ref_names, trigger_reason=trigger_reason)

        async def _on_ref_done(ref: ReferenceResponse) -> None:
            sse_ref = apply_privacy_to_ref(ref, sse_privacy_mode(privacy_mode), privacy_redactor)
            await _emit_ref_done(
                sse_ref.model,
                success=sse_ref.success,
                elapsed=sse_ref.elapsed_seconds,
                content=sse_ref.content if sse_ref.success else None,
            )

        try:
            timeout_limit = (
                overlay_cfg.risk_trigger_timeout
                if overlay_cfg.fanout == "risk_triggered"
                else overlay_cfg.timeout_total
            )
            if overlay_cfg.fanout == "risk_triggered":
                fanout = runner.run(messages, on_ref_done=_on_ref_done, force_run=fanout_this_call)
            else:
                fanout = runner.run(messages, on_ref_done=_on_ref_done)
            ref_responses = await asyncio.wait_for(fanout, timeout=timeout_limit)
        except TimeoutError:
            logger.warning(
                "MoA overlay: hard timeout reached (%.1fs) during fan-out; silent fallback to acting model",
                timeout_limit,
            )
            if fanout_this_call:
                await _emit_overlay_skipped(MOA_OVERLAY_SKIP_RISK_TIMEOUT)
            return await forward()

        if not ref_responses:
            return await forward()

        if router is not None and fanout_this_call:
            router.record_trigger(next_iteration)

        successful = [r for r in ref_responses if r.success and r.content.strip()]
        if len(successful) < overlay_cfg.min_successful:
            if fanout_this_call:
                await _emit_overlay_skipped(MOA_OVERLAY_SKIP_INSUFFICIENT_REFS)
            logger.info(
                "MoA overlay: insufficient refs (%d/%d), skipping injection",
                len(successful),
                overlay_cfg.min_successful,
            )
            return await forward()

        inject_refs = [apply_privacy_to_ref(r, inject_privacy_mode(privacy_mode), privacy_redactor) for r in successful]
        injection = build_advisor_injection_block(inject_refs)
        if injection:
            ledger.record(last_stored_message(messages), injection)
        return await forward()

    return _middleware


__all__ = [
    "MOA_OVERLAY_SKIP_BUDGET_PRESSURE",
    "MOA_OVERLAY_SKIP_INSUFFICIENT_REFS",
    "MOA_OVERLAY_SKIP_RISK_TIMEOUT",
    "create_moa_advisor_middleware",
]
