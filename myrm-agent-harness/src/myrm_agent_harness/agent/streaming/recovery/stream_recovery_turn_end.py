"""Streaming turn-end recovery: what runs after the model finished a turn that did not end well.

[INPUT]
- agent.streaming.recovery.stream_recovery_truncation (POS: reply-shape helpers and the re-run input shared with the truncation recoveries)
- agent.config.llm_safety::normalize_messages (POS: re-pairs tool calls with their results for a direct LLM call)
- utils.chat_utils::extract_answer_text (POS: answer extraction that falls back for reasoning models with empty content)

[OUTPUT]
- StreamTurnEndRecoveryMixin: iteration-limit handling with a grace-call summary, and empty-response recovery.

[POS]
Mixed into StreamRecoveryMixin. These handlers act on the messages a finished turn collected, not on an error it raised.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.agent.errors.fault_side import FaultSide
from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import StreamTruncationRecoveryMixin
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.utils.chat_utils import extract_answer_text
from myrm_agent_harness.utils.logger_utils import get_agent_logger

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

    from myrm_agent_harness.agent.streaming.stream_compactor import StreamCompactor
    from myrm_agent_harness.agent.streaming.stream_executor import StreamContext

logger = get_agent_logger(__name__)


class StreamTurnEndRecoveryMixin(StreamTruncationRecoveryMixin):
    """Turn-end recovery handlers, used by StreamExecutor via StreamRecoveryMixin.

    Accesses StreamExecutor attributes via self: _ctx, _compactor, _emit_recovery_event.
    """

    _ctx: StreamContext
    _compactor: StreamCompactor

    if TYPE_CHECKING:

        async def _emit_recovery_event(self, step_key: str, **extra: object) -> None: ...

    async def _handle_iteration_limit(
        self,
        exc: Exception,
        collected_messages: list[BaseMessage],
    ) -> bool:
        """Detect GraphRecursionError, generate a grace-call summary, and emit events.

        When the LangGraph recursion limit is reached:
        1. Emit ITERATION_LIMIT_REACHED event (frontend shows a warning badge).
        2. Perform a **grace call**: one extra toolless LLM invocation that produces
           a summary from the conversation so far, ensuring the user never sees a
           blank response.
        3. Return True so the caller can decide whether to break (normal mode) or
           fall through to goal-continuation (goal mode).
        """
        from langgraph.errors import GraphRecursionError

        if not isinstance(exc, GraphRecursionError):
            return False

        ctx = self._ctx
        recursion_limit = ctx.run_config.get("recursion_limit", "?")
        logger.warning(
            " Iteration limit reached (%s). Completed %d nodes before limit. Detail: %s",
            recursion_limit,
            ctx.stats.node_execution_count,
            exc,
        )

        await self._compactor.put(
            {
                "type": AgentEventType.ITERATION_LIMIT_REACHED.value,
                "data": {
                    "limit": recursion_limit,
                    "nodes_completed": ctx.stats.node_execution_count,
                    # Recursion limit is an engine pipeline guard, not a model or
                    # tool failure — attribute to HARNESS_PIPELINE.
                    "fault_side": FaultSide.HARNESS_PIPELINE.value,
                },
                "messageId": ctx.message_id,
            }
        )

        await self._grace_call_summary(collected_messages)
        return True

    _GRACE_FALLBACK_EN = (
        "I reached the iteration limit before completing the task. "
        "Please try again with a more specific request, or I can "
        "continue from where I left off."
    )
    _GRACE_FALLBACK_ZH = "本轮执行已达到迭代上限，任务尚未完成。你可以尝试更具体的指令，或者让我从上次中断的地方继续。"

    def _grace_fallback_text(self) -> str:
        locale = self._ctx.merged_context.get("locale", "en") if self._ctx.merged_context else "en"
        return self._GRACE_FALLBACK_ZH if locale.startswith("zh") else self._GRACE_FALLBACK_EN

    async def _grace_call_summary(
        self,
        collected_messages: list[BaseMessage],
    ) -> None:
        """Perform a single toolless LLM call to summarise progress so far.

        The summary is emitted as a normal ``MESSAGE`` event so the frontend
        renders it automatically — no frontend changes required.
        """

        from myrm_agent_harness.agent.config.llm_safety import normalize_messages

        llm = self._ctx.llm
        if llm is None:
            await self._emit_message_pair(self._grace_fallback_text())
            return

        grace_prompt = HumanMessage(
            content=(
                "[SYSTEM] You have reached the maximum iteration limit for this turn. "
                "Based on the work you have done so far, provide a concise summary of "
                "your findings and any remaining tasks. Do NOT call any tools. "
                "If prior tool messages already contain successful MCP, web search, or "
                "browser results, summarize that data faithfully — do not claim tools "
                "were not called. "
                "Respond in the same language as the conversation."
            ),
        )
        repaired_messages = normalize_messages(collected_messages)
        tail = repaired_messages[-20:]
        while tail and getattr(tail[0], "type", None) == "tool":
            tail = tail[1:]
        summary_messages = [*tail, grace_prompt]

        try:
            response: AIMessage = await llm.ainvoke(summary_messages)
            # 兼容 reasoning 模型 content 空回退（Qwen3/DeepSeek-R1 等）
            summary_text = extract_answer_text(response).strip()
        except Exception:
            logger.warning("Grace call LLM invocation failed; using fallback message")
            summary_text = ""

        await self._emit_message_pair(summary_text.strip() if summary_text else self._grace_fallback_text())

    async def _emit_message_pair(self, text: str) -> None:
        """Emit a MESSAGE + MESSAGE_END event pair."""
        mid = self._ctx.message_id
        await self._compactor.put({"type": AgentEventType.MESSAGE.value, "data": text, "messageId": mid})
        await self._compactor.put({"type": AgentEventType.MESSAGE_END.value, "data": "", "messageId": mid})

    async def _handle_empty_response(
        self,
        collected_messages: list[BaseMessage],
        retries: int = 0,
    ) -> bool:
        """Detect empty LLM response and inject a prompt to recover.

        The reply judged is the run's latest one, which ``collected_messages`` does not hold when it is empty.
        Returns True when a continuation prompt was injected (caller should ``continue``
        the outer loop to re-run astream). Returns False otherwise.
        """
        last_ai_msg = self._latest_reply
        if last_ai_msg is None:
            return False

        has_tool_calls = self._has_tool_calls(last_ai_msg)
        # Tag-wrapped reasoning (MiniMax inlines ``<think>`` into ``content``) is not
        # user-visible content, so it must not exempt the turn from recovery.
        has_tagged_reasoning = self._has_inline_reasoning(last_ai_msg)
        has_content = False if has_tagged_reasoning else self._has_non_reasoning_content(last_ai_msg)

        # Tool calls (executable or withheld as unsafe) or user-visible content: not an empty response.
        # Note: We do NOT exempt reasoning-only responses (e.g. <thinking> blocks without actual output).
        # A reasoning-only response is still an empty response from the user's perspective and must be retried.
        if has_tool_calls or has_content:
            return False

        # A reply the output limit cut inside its reasoning belongs to the truncation recovery, which has
        # already raised the budget as far as it goes: asking again at the base budget would only cut again.
        if self._cut_by_output_limit() and (has_tagged_reasoning or self._has_reasoning_content(last_ai_msg)):
            return False

        if has_tagged_reasoning:
            logger.warning(" Response contained only tag-wrapped reasoning — no visible output")

        max_empty_retries = 2
        if retries >= max_empty_retries:
            logger.error(
                " Empty response recovery exhausted after %d retries. Raising error.",
                retries,
            )
            from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError
            from myrm_agent_harness.toolkits.llms.errors.error_types import (
                FailoverReason,
            )

            raise MyrmLLMError(
                error_code=FailoverReason.FORMAT_ERROR,
                default_msg="LLM returned an empty response repeatedly.",
            )

        self._redrive_with_hint(
            collected_messages,
            "[System: Your response was completely empty (no text and no tool calls). "
            "Please provide your answer or call a tool to proceed with the task.]",
        )

        logger.warning(
            "↻ Empty response detected. Injecting recovery prompt (%d/%d)...",
            retries + 1,
            max_empty_retries,
        )

        await self._emit_recovery_event("empty_response_recovery", restart=True)
        return True
