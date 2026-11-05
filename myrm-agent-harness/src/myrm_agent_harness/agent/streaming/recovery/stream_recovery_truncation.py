"""Streaming length truncation recovery mixin.

[INPUT]
- toolkits.llms.ephemeral_output_tokens (POS: ephemeral max-output-tokens ContextVar)
- agent.streaming.types::AgentEventType (POS: streaming event type constants)
- agent.errors.diagnostics::LLMErrorDiagnostic (POS: LLM truncation diagnostic builder)
- utils.token_economics.tracker::get_token_tracker (POS: token finish-reason tracker)
- toolkits.llms.adapters.tool_recovery::has_withheld_tool_calls, describe_withheld_tool_calls (POS: detects tool calls withheld as unsafe, and describes them for the log)
- agent.streaming.recovery.stream_recovery_budget::StreamOutputBudgetMixin (POS: output budget scaling of recovery retries)
- agent.streaming.recovery.stream_recovery_redrive::StreamRedriveMixin (POS: the re-run input shared by fresh and resumed turns)

[OUTPUT]
- StreamTruncationRecoveryMixin: handles length/max-token continuation, truncated or withheld tool-call retry, and truncation warnings.
- ephemeral_max_output_tokens: ContextVar for per-request output token override.
- get_ephemeral_max_output_tokens / set_ephemeral_max_output_tokens / reset_ephemeral_max_output_tokens: accessors.

[POS]
Streaming truncation recovery layer. Detects length-truncated responses, injects safe
continuation prompts with progressive output budget boosting, auto-retries truncated
or withheld (unsafe-argument) tool calls, and emits structured truncation warnings.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage

from myrm_agent_harness.agent.streaming.recovery.stream_recovery_budget import StreamOutputBudgetMixin
from myrm_agent_harness.agent.streaming.recovery.stream_recovery_redrive import StreamRedriveMixin
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.core.events import THINKING_TAG_NAMES
from myrm_agent_harness.toolkits.llms.adapters.tool_recovery import (
    describe_withheld_tool_calls,
    has_withheld_tool_calls,
)
from myrm_agent_harness.toolkits.llms.ephemeral_output_tokens import (
    MAX_EPHEMERAL_OUTPUT_TOKENS,
    ephemeral_max_output_tokens,
    get_ephemeral_max_output_tokens,
    reset_ephemeral_max_output_tokens,
    set_ephemeral_max_output_tokens,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

    from myrm_agent_harness.agent.streaming.stream_compactor import StreamCompactor
    from myrm_agent_harness.agent.streaming.stream_executor import StreamContext

logger = get_agent_logger(__name__)

_MAX_EPHEMERAL_OUTPUT_TOKENS = MAX_EPHEMERAL_OUTPUT_TOKENS


class StreamTruncationRecoveryMixin(StreamOutputBudgetMixin, StreamRedriveMixin):
    _ctx: StreamContext
    _compactor: StreamCompactor
    _latest_reply: AIMessage | None
    streaming_final_answer: bool
    _tool_truncation_retries: int
    _MAX_LENGTH_CONTINUE_RETRIES = 3
    _MAX_TOOL_TRUNCATION_RETRIES = 1

    async def _handle_length_truncation(
        self,
        collected_messages: list[BaseMessage],
        retries: int = 0,
    ) -> bool:
        """Detect length truncation and either auto-continue or emit warnings.

        What was truncated is the run's latest reply, which ``collected_messages`` may not hold (an empty
        reply is left out of it); ``collected_messages`` is what a retry carries.
        """
        last_ai_msg = self._latest_reply
        if last_ai_msg is None:
            return False

        # A tool call withheld as unsafe (arguments cut off or unparseable) ends the
        # turn as surely as a length cut, whatever finish_reason the provider reported.
        if not self._cut_by_output_limit() and not has_withheld_tool_calls(last_ai_msg.additional_kwargs):
            return False

        has_tool_calls = self._has_tool_calls(last_ai_msg)
        # Tag-wrapped reasoning must be classified before the plain-content probe:
        # providers that inline ``<think>`` into ``content`` (MiniMax) otherwise
        # look like they produced user-visible text.
        has_tagged_reasoning = self._has_inline_reasoning(last_ai_msg)
        has_content = False if has_tagged_reasoning else self._has_non_reasoning_content(last_ai_msg)
        has_reasoning = has_tagged_reasoning or self._has_reasoning_content(last_ai_msg)

        ctx = self._ctx
        locale = ctx.merged_context.get("locale", "en") if ctx.merged_context else "en"

        if has_content and not has_tool_calls:
            return await self._try_text_continuation(
                collected_messages,
                retries,
                locale,
            )

        if has_tool_calls:
            return await self._try_tool_call_retry(
                collected_messages,
                last_ai_msg,
                locale,
            )

        if has_reasoning and not has_content:
            return await self._try_thinking_budget_recovery(
                collected_messages,
                last_ai_msg,
                retries,
                locale,
            )

        return False

    async def _try_thinking_budget_recovery(
        self,
        collected_messages: list[BaseMessage],
        draft: BaseMessage,
        retries: int,
        locale: str,
    ) -> bool:
        """Recover a reasoning-only truncation by raising the budget and retrying.

        The thinking phase consumed the whole output budget, so the model never
        reached user-visible text. Re-running without more headroom would simply
        truncate again — the budget boost is what makes the retry productive.
        Prevention lives upstream: ``thinking_headroom`` floors a thinking model's
        ``max_tokens`` at creation time.
        """
        if retries >= self._MAX_LENGTH_CONTINUE_RETRIES:
            logger.warning(
                " Thinking-budget recovery exhausted after %d retries",
                retries,
            )
            reset_ephemeral_max_output_tokens()
            await self._emit_truncation_warning("thinking_budget_exhausted", locale)
            return False

        # The draft is not re-sent: the user never saw it (the scrubber routed it to REASONING).
        self._redrive_with_hint(
            (msg for msg in collected_messages if msg is not draft),
            "[System: Your previous response spent its entire output budget on "
            "internal reasoning and produced no user-visible answer. Respond "
            "directly now, with minimal reasoning.]",
        )

        self._boost_output_tokens(retries)

        logger.warning(
            "↻ Thinking-budget recovery (%d/%d)...",
            retries + 1,
            self._MAX_LENGTH_CONTINUE_RETRIES,
        )
        await self._emit_truncation_warning("thinking_budget_exhausted", locale)
        return True

    async def _try_text_continuation(
        self,
        collected_messages: list[BaseMessage],
        retries: int,
        locale: str,
    ) -> bool:
        """Inject a continuation prompt and signal the outer loop to retry astream."""
        if retries >= self._MAX_LENGTH_CONTINUE_RETRIES:
            logger.warning(
                " Text continuation exhausted after %d retries",
                retries,
            )
            reset_ephemeral_max_output_tokens()
            await self._emit_truncation_warning("text_continuation_exhausted", locale)
            return False

        self._redrive_with_hint(
            collected_messages,
            "[System: Your previous response was truncated by the output length limit. "
            "Continue exactly where you left off. Do not restart or repeat prior text. "
            "Finish the answer directly.]",
        )

        self._boost_output_tokens(retries)

        logger.warning(
            "↻ Text continuation (%d/%d)...",
            retries + 1,
            self._MAX_LENGTH_CONTINUE_RETRIES,
        )

        await self._emit_truncation_warning("text_continuation", locale)
        return True

    async def _try_tool_call_retry(
        self,
        collected_messages: list[BaseMessage],
        failed_reply: AIMessage,
        locale: str,
    ) -> bool:
        """Re-run the turn after its tool call failed, with a larger output budget.

        The failed reply carries nothing executable (its calls are cut off or withheld as unsafe), so it is
        not re-sent. Only retries once to avoid infinite loops.
        """
        for description in describe_withheld_tool_calls(failed_reply.additional_kwargs):
            logger.warning(" Withheld tool call: %s", description)
        kept = [msg for msg in collected_messages if msg is not failed_reply]

        tool_truncation_retries = self._tool_truncation_retries
        if tool_truncation_retries >= self._MAX_TOOL_TRUNCATION_RETRIES:
            logger.warning(
                " Tool-call truncation retry exhausted (%d/%d)",
                tool_truncation_retries,
                self._MAX_TOOL_TRUNCATION_RETRIES,
            )
            reset_ephemeral_max_output_tokens()
            await self._emit_truncation_warning("tool_call_truncated", locale)
            return False

        self._tool_truncation_retries = tool_truncation_retries + 1

        self._redrive_with_hint(
            kept,
            "[System: Your previous tool call was not executed because its arguments were "
            "incomplete or invalid (for example cut off by the output length limit). "
            "Please retry the operation. If the output is very large, consider splitting "
            "it into smaller parts.]",
        )

        self._boost_output_tokens(0)

        logger.warning(
            "↻ Tool-call truncation retry (%d/%d)...",
            tool_truncation_retries + 1,
            self._MAX_TOOL_TRUNCATION_RETRIES,
        )
        await self._emit_truncation_warning("tool_call_retry", locale, restart=True)
        return True

    async def _emit_truncation_warning(
        self,
        truncation_type: str,
        locale: str,
        restart: bool = False,
    ) -> None:
        """Emit a STATUS event with optional i18n diagnostic for truncation.

        ``restart=True`` marks recovery paths that discard the truncated output and
        re-run the turn from scratch (tool-call truncation retry), so the consumer
        drops any draft streamed before the truncation. Continuation and warning-only
        paths leave it False.
        """
        try:
            from myrm_agent_harness.agent.errors.diagnostics import LLMErrorDiagnostic

            diagnostic = LLMErrorDiagnostic.diagnose_truncation(truncation_type, locale)
            diagnostic_dict: dict[str, object] | None = {
                "error_type": diagnostic.error_type,
                "user_message": diagnostic.user_message,
                "resolution_steps": diagnostic.resolution_steps,
                "locale": diagnostic.locale,
            }
        except Exception as diag_err:
            logger.error("Truncation diagnostic failed: %s", diag_err)
            diagnostic_dict = None

        logger.warning(" Length truncation detected: %s", truncation_type)

        event: dict[str, object] = {
            "type": AgentEventType.STATUS.value,
            "step_key": truncation_type,
            "tool_name": None,
            "messageId": self._ctx.message_id,
        }
        if restart:
            event["restart"] = True
        if diagnostic_dict:
            event["diagnostic_result"] = diagnostic_dict

        await self._compactor.put(event)

    @staticmethod
    def _cut_by_output_limit() -> bool:
        """Whether the provider reported that the latest model call stopped at its output limit."""
        from myrm_agent_harness.utils.token_economics.tracker import get_token_tracker

        tracker = get_token_tracker()
        return tracker is not None and tracker.last_finish_reason in ("length", "max_tokens")

    @staticmethod
    def _has_tool_calls(msg: AIMessage) -> bool:
        """Whether the message carries executable tool calls or calls withheld as unsafe."""
        return bool(msg.tool_calls) or has_withheld_tool_calls(msg.additional_kwargs)

    @staticmethod
    def _has_non_reasoning_content(msg: object) -> bool:
        """Check if an AIMessage has actual user-visible content."""
        content = getattr(msg, "content", None)
        if not content:
            return False
        if isinstance(content, str):
            return bool(content.strip())
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") not in ("thinking", "redacted_thinking"):
                        return True
                elif isinstance(block, str) and block.strip():
                    return True
            return False
        return bool(content)

    @staticmethod
    def _has_reasoning_content(msg: object) -> bool:
        """Check if an AIMessage contains reasoning/thinking content."""
        kwargs: dict[str, object] = getattr(msg, "additional_kwargs", {}) or {}
        if kwargs.get("reasoning_content"):
            return True

        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    return True

        return False

    @staticmethod
    def _has_inline_reasoning(msg: object) -> bool:
        """Check if an AIMessage's text is nothing but tag-wrapped reasoning.

        Some providers return the thinking phase inside ``content`` wrapped in tags
        (MiniMax emits ``<think>…</think>``) instead of a separate reasoning field.
        The stream layer strips those tags before display, so such a message reaches
        the user as empty even though ``content`` is non-empty.

        Returns True only when tags are present, the text has no thinking left over,
        and the residual carries no user-visible answer — otherwise the message is a
        genuine (truncated) answer that belongs on the continuation path.
        """
        content = getattr(msg, "content", None)
        if not isinstance(content, str) or not content:
            return False

        stripped = content
        tagged = False
        for name in THINKING_TAG_NAMES:
            open_tag = f"<{name}>"
            close_tag = f"</{name}>"
            if open_tag not in stripped and close_tag not in stripped:
                continue
            tagged = True
            # Remove complete blocks, then any unclosed trailing block: an opening
            # tag with no close marks a response cut off mid-reasoning, so the
            # remainder is reasoning too and must not count as visible content.
            stripped = re.sub(
                rf"{re.escape(open_tag)}.*?{re.escape(close_tag)}",
                "",
                stripped,
                flags=re.DOTALL,
            )
            if open_tag in stripped:
                stripped = stripped.split(open_tag, 1)[0]
            stripped = stripped.replace(close_tag, "")

        return tagged and not stripped.strip()


__all__ = [
    "MAX_EPHEMERAL_OUTPUT_TOKENS",
    "_MAX_EPHEMERAL_OUTPUT_TOKENS",
    "StreamTruncationRecoveryMixin",
    "ephemeral_max_output_tokens",
    "get_ephemeral_max_output_tokens",
    "reset_ephemeral_max_output_tokens",
    "set_ephemeral_max_output_tokens",
]
