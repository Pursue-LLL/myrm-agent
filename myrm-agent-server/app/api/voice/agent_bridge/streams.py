"""[INPUT]
- .common (POS: shared types and constants)

[OUTPUT]
- StreamMixin

[POS]
Voice bridge mixin: fast-lane and agent-stream consumption for a voice turn.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason

if TYPE_CHECKING:
    from app.ai_agents.agents import GeneralAgentParams

from .common import (
    _HANDOFF_HINT_EN,
    _HANDOFF_HINT_ZH,
    _SENTENCE_END,
    _VOICE_SUPERVISOR_TIMEOUT_S,
    logger,
)


class StreamMixin:
    def _is_fast_lane_query(self, query: str, params: GeneralAgentParams) -> bool:
        """Classify if the query can take the Fast Lane.

        SIMPLE queries (greetings, quick acknowledgments, simple factuals) with no
        active skills, custom subagents, or forced search take the fast lane.
        """
        if params.agent_skill_ids or params.subagent_ids:
            return False

        from myrm_agent_harness.toolkits.llms.routing.complexity_router import (
            DEFAULT_REASONING_KEYWORDS,
            DEFAULT_SIMPLE_INDICATORS,
            DEFAULT_STANDARD_KEYWORDS,
            RoutingTier,
            _rule_based_classify,
        )

        tier = _rule_based_classify(
            query,
            has_image=False,
            standard_keywords=DEFAULT_STANDARD_KEYWORDS,
            reasoning_keywords=DEFAULT_REASONING_KEYWORDS,
            simple_indicators=DEFAULT_SIMPLE_INDICATORS,
        )
        return tier == RoutingTier.SIMPLE

    async def _consume_fast_lane_stream(
        self,
        params: GeneralAgentParams,
        cancel_token: CancellationToken,
        turn_id: str,
    ) -> tuple[str, bool]:
        """Execute fast lane stream for simple greetings/factuals without heavy AgentFactory."""
        from app.services.agent.stream_session.stream_lane_factory import (
            create_fast_lane_stream,
        )

        full_text_parts: list[str] = []
        pending_text = ""

        try:
            async for event in create_fast_lane_stream(params, cancel_token):
                if self._current_turn != turn_id or self._closed:
                    break

                event_type = event.get("type", "")
                if event_type == "message":
                    chunk = str(event.get("data", ""))
                    if chunk:
                        pending_text += chunk
                        full_text_parts.append(chunk)

                        segments, remaining = _extract_speakable_segments(pending_text)
                        pending_text = remaining
                        for seg in segments:
                            await self._stream_tts_segment(seg, turn_id)
                            await self._send_json(
                                {
                                    "type": "agent_response",
                                    "text": seg,
                                    "turn_id": turn_id,
                                    "done": False,
                                }
                            )

            if pending_text.strip() and self._current_turn == turn_id:
                await self._stream_tts_segment(pending_text.strip(), turn_id)
                await self._send_json(
                    {
                        "type": "agent_response",
                        "text": pending_text.strip(),
                        "turn_id": turn_id,
                        "done": True,
                    }
                )

        except Exception:
            logger.exception("Voice bridge fast lane error (turn=%s)", turn_id)
            # Fallback self-healing: if fast lane fails unexpectedly, try falling back to full stream
            if not full_text_parts and self._current_turn == turn_id:
                logger.info("Fast lane produced no output, falling back to full agent stream (turn=%s)", turn_id)
                return await self._consume_agent_stream(params, cancel_token, turn_id)

        return "".join(full_text_parts), False

    async def _consume_agent_stream_supervised(
        self,
        params: GeneralAgentParams,
        cancel_token: CancellationToken,
        turn_id: str,
        effective_query: str,
    ) -> tuple[str, bool]:
        """Supervised full agent execution: hands off to background if duration exceeds 15s."""
        agent_task = asyncio.create_task(self._consume_agent_stream(params, cancel_token, turn_id))

        try:
            done, pending = await asyncio.wait(
                {agent_task},
                timeout=_VOICE_SUPERVISOR_TIMEOUT_S,
            )

            if agent_task in done:
                return await agent_task

            # Timeout occurred (> 15s). Hand off to background task handler.
            logger.info("Voice turn %s exceeded %.1fs, delegating to background", turn_id, _VOICE_SUPERVISOR_TIMEOUT_S)
            cancel_token.cancel(CancelReason.USER_CANCELLED)
            await self._handoff_to_background(effective_query, turn_id)
            return "", False

        except asyncio.CancelledError:
            if not agent_task.done():
                agent_task.cancel()
            raise

    async def _consume_agent_stream(
        self,
        params: GeneralAgentParams,
        cancel_token: CancellationToken,
        turn_id: str,
    ) -> tuple[str, bool]:
        """Consume agent stream, sentence-split TTS, return (full_text, has_approval)."""
        from app.services.agent.runtime_context import (
            build_agent_runtime_context,
            resolve_stream_execution_mode,
        )
        from app.services.agent.streaming import ai_agent_service_stream

        extra_context = await build_agent_runtime_context(execution_mode=resolve_stream_execution_mode())

        full_text_parts: list[str] = []
        pending_text = ""
        has_approval = False

        async for event in ai_agent_service_stream(
            params,
            cancel_token=cancel_token,
            extra_context=extra_context,
        ):
            if self._current_turn != turn_id or self._closed:
                break

            event_type = event.get("type", "")

            if event_type == "message":
                chunk = str(event.get("data", ""))
                if chunk:
                    pending_text += chunk
                    full_text_parts.append(chunk)

                    segments, remaining = _extract_speakable_segments(pending_text)
                    pending_text = remaining
                    for seg in segments:
                        await self._stream_tts_segment(seg, turn_id)
                        await self._send_json(
                            {
                                "type": "agent_response",
                                "text": seg,
                                "turn_id": turn_id,
                                "done": False,
                            }
                        )

            elif event_type == "tool_use":
                tool_data = event.get("data")
                tool_name = tool_data.get("name", "") if isinstance(tool_data, dict) else ""
                await self._send_json(
                    {
                        "type": "agent_tool_use",
                        "tool_name": tool_name,
                        "turn_id": turn_id,
                    }
                )

            elif event_type in ("approval_required", "tool_approval_request"):
                has_approval = True
                await self._handle_approval_required(event, turn_id)

        if pending_text.strip() and self._current_turn == turn_id:
            await self._stream_tts_segment(pending_text.strip(), turn_id)
            await self._send_json(
                {
                    "type": "agent_response",
                    "text": pending_text.strip(),
                    "turn_id": turn_id,
                    "done": True,
                }
            )

        return "".join(full_text_parts), has_approval

    async def _handoff_to_background(self, prompt: str, turn_id: str) -> None:
        """Inform user of handoff via TTS and spawn persistent Kanban background task."""
        from app.channels.types import InboundMessage
        from app.core.channel_bridge.persistent_background import BACKGROUND_SOURCE_VOICE
        from app.core.channel_bridge.setup import get_background_task_handler

        lang = (self._voice_config.stt_language or "").lower()
        hint = _HANDOFF_HINT_ZH if "zh" in lang or "cn" in lang else _HANDOFF_HINT_EN
        await self._stream_tts_segment(hint, turn_id)
        await self._send_json(
            {
                "type": "agent_response",
                "text": hint,
                "turn_id": turn_id,
                "done": True,
                "handoff_background": True,
            }
        )

        handler = get_background_task_handler()
        if handler:
            chat_id = self._chat_id or "voice_bridge"
            msg = InboundMessage(
                channel="voice_bridge",
                sender_id=chat_id,
                chat_id=chat_id,
                content=prompt,
                user_id="local-user",
            )
            try:
                task_id = await handler.spawn_background(
                    msg,
                    prompt,
                    background_source=BACKGROUND_SOURCE_VOICE,
                    agent_id=self._agent_id,
                )
                logger.info("Voice turn %s successfully handed off to background task %s", turn_id, task_id)
            except Exception:
                logger.exception("Failed to spawn background task for voice turn %s", turn_id)
        else:
            logger.warning("Background task handler not available for voice handoff (turn=%s)", turn_id)


def _extract_speakable_segments(text: str) -> tuple[list[str], str]:
    """Split text at sentence boundaries; return (segments, remaining)."""
    segments: list[str] = []
    remaining = text

    while remaining:
        match = _SENTENCE_END.search(remaining)
        if match is None:
            break
        segment = remaining[: match.end()].strip()
        if segment:
            segments.append(segment)
        remaining = remaining[match.end() :]

    return segments, remaining
