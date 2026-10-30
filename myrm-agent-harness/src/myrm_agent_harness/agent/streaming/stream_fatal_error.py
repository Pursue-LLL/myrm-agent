"""流式执行引擎 — 致命错误上报 Mixin

[INPUT]
- agent.errors.fault_side::classify_fault_side (POS: Deterministic fault-side attribution; pure functions, no I/O.)
- agent.streaming.recovery.context_pressure_gate::CONTEXT_OVERFLOW_TERMINAL_CODE (POS: Deterministic send-gate owned by the streaming recovery layer.)
- agent.streaming.stream_compactor::StreamCompactor (POS: Coalescing queue writer for high-frequency stream events.)
- toolkits.llms.errors::MyrmLLMError, classify_error, classify_failover_reason (POS: LLM error classification and standardized exceptions for failover decisions.)
- toolkits.llms.errors.provider_window::extract_provider_window (POS: Facade for the provider-window subpackage.)

[OUTPUT]
- StreamFatalErrorMixin: `_emit_fatal_error` builds the diagnosed error event, persists it to the event journal and raises MyrmLLMError.

[POS]
Fatal-error reporting for StreamExecutor: one place that turns an exception of the run into the GUI error event and the typed exception.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.agent.errors.fault_side import classify_fault_side
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.toolkits.llms.errors import (
    MyrmLLMError,
    classify_failover_reason,
)
from myrm_agent_harness.toolkits.llms.errors.classifier import classify_error
from myrm_agent_harness.toolkits.llms.errors.provider_window import extract_provider_window
from myrm_agent_harness.utils.logger_utils import get_agent_logger

from .recovery.context_pressure_gate import CONTEXT_OVERFLOW_TERMINAL_CODE

if TYPE_CHECKING:
    from .stream_compactor import StreamCompactor
    from .stream_executor import StreamContext

logger = get_agent_logger(__name__)


class StreamFatalErrorMixin:
    """Fatal-error reporting. StreamExecutor uses it through multiple inheritance.

    Reads from the executor: _ctx, _compactor.
    """

    _ctx: StreamContext
    _compactor: StreamCompactor

    async def _emit_fatal_error(self, exc: Exception) -> None:
        """Build standardized error event with diagnostics and raise MyrmLLMError."""
        ctx = self._ctx
        error_msg = str(exc)
        error_type = type(exc).__name__
        failover_reason = classify_failover_reason(exc)
        error_kind = classify_error(exc)
        ctx.stats.error_message = f"{error_type}: {error_msg}"
        logger.error(
            " Agent execution error [%s]: %s: %s",
            failover_reason.value,
            error_type,
            error_msg[:300],
            exc_info=True,
        )

        error_event: dict[str, object] = {
            "type": AgentEventType.ERROR.value,
            "error": error_msg,
            "error_type": error_type,
            "error_kind": error_kind.value,
            "failover_reason": failover_reason.value,
            "messageId": ctx.message_id,
        }

        # Deterministic fault-side attribution (pure rules, no LLM) — lets the
        # GUI tell users who owns the failure instead of guessing.
        error_event["fault_side"] = classify_fault_side(error_kind=error_kind.value).value

        if ctx.stats.compression_exhausted:
            error_event["compression_exhausted"] = True
            error_event["terminal_code"] = CONTEXT_OVERFLOW_TERMINAL_CODE

        window_hint = extract_provider_window(exc)
        if window_hint is not None:
            error_event["cooldown_remaining_ms"] = int(window_hint.wait_s * 1000)

        try:
            from myrm_agent_harness.agent.errors.diagnostics import (
                ErrorContext,
                LLMErrorDiagnostic,
            )

            model_name = "unknown"
            base_url = None
            is_custom_endpoint = False

            if ctx.llm_info:
                model_name = ctx.llm_info.get("model_name") or "unknown"
                base_url = ctx.llm_info.get("base_url")
                is_custom_endpoint = base_url is not None

            context = ErrorContext(
                model_name=model_name,
                is_custom_endpoint=is_custom_endpoint,
                base_url=base_url,
            )

            locale = ctx.merged_context.get("locale", "en") if ctx.merged_context else "en"
            cooldown_remaining_ms = error_event.get("cooldown_remaining_ms")
            cooldown_remaining_ms = cooldown_remaining_ms if isinstance(cooldown_remaining_ms, int) else None

            diagnostic = LLMErrorDiagnostic.diagnose(
                exc, context, locale=locale, cooldown_remaining_ms=cooldown_remaining_ms
            )

            error_event["diagnostic_result"] = {
                "error_type": diagnostic.error_type,
                "user_message": diagnostic.user_message,
                "resolution_steps": diagnostic.resolution_steps,
                "locale": diagnostic.locale,
            }

            # Refine attribution with the diagnostic error_type as a fallback:
            # error_kind may be UNKNOWN while the diagnostic pinpoints the cause
            # (e.g. api_key/connection). The unified classifier prefers
            # error_kind and falls back to error_type.
            error_event["fault_side"] = classify_fault_side(
                error_kind=error_kind.value,
                error_type=diagnostic.error_type,
            ).value

            recovery_actions = LLMErrorDiagnostic.get_recovery_actions(diagnostic.error_type, locale=diagnostic.locale)
            if recovery_actions:
                error_event["recovery_actions"] = recovery_actions
        except Exception as diag_err:
            logger.error("Diagnostic generation failed: %s", diag_err)

        await self._compactor.put(error_event)

        # Persist the fatal error to the event journal so post-mortem trace
        # reconstruction (trace_builder) sees LLM fatal errors, not just tool
        # failures. Mirrors StreamDispatcherMixin._emit_event's logging path:
        # type/messageId are transport-only fields, stripped before persistence.
        # Best-effort: logging must never mask the original fatal error.
        if ctx.event_logger is not None:
            try:
                persisted = dict(error_event)
                persisted.pop("type", None)
                persisted.pop("messageId", None)
                await ctx.event_logger.log(AgentEventType.ERROR.value, persisted)
            except Exception as log_err:
                logger.error("Failed to persist fatal error event: %s", log_err)

        diagnostic_payload = error_event.get("diagnostic_result")
        raise MyrmLLMError(
            error_code=failover_reason,
            default_msg=error_msg,
            context=(
                {"cooldown_remaining_ms": error_event.get("cooldown_remaining_ms")}
                if "cooldown_remaining_ms" in error_event
                else None
            ),
            original_exc=exc,
            diagnostic_result=(diagnostic_payload if isinstance(diagnostic_payload, dict) else None),
        ) from exc
