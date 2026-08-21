"""Voice Agent Bridge — server-side Agent execution within voice sessions.

Eliminates the frontend roundtrip by invoking the Agent directly from the
voice WebSocket when STT produces final text. Agent streamed output is
sentence-split and piped to TTS in real-time.

[INPUT]
- app.services.agent.streaming::ai_agent_service_stream (POS: Agent SSE streaming)
- app.services.agent.profile.profile_resolver::get_agent_profile_resolver (POS: Agent profile resolver)
- app.core.channel_bridge.config_loader::load_user_configs (POS: user config loader)
- app.core.channel_bridge.config_parsers (POS: config extraction utilities)
- app.core.channel_bridge.model_resolver (POS: model config resolution)
- app.channels.voice.tts::synthesize_stream (POS: streaming TTS)
- app.services.agent.resolve_enable_web_fetch::resolve_enable_web_fetch (POS: net_fetch capability gate)
- app.api.voice.voice_memory_context::voice_memory_context_from (POS: voice memory ACL SSOT)
- myrm_agent_harness.utils.runtime.cancellation::CancellationToken (POS: cancellation primitive)

[OUTPUT]
- VoiceAgentBridge: server-side Agent execution bridge for voice sessions

[POS]
Agent execution bridge for voice sessions. Handles parameter assembly,
streaming Agent execution, sentence-split TTS pipeline, turn management,
and working-response feedback within a single WebSocket session.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.runtime.cancellation import (
    CancellationToken,
    CancelReason,
)

if TYPE_CHECKING:
    from fastapi import WebSocket

    from app.ai_agents.agents import GeneralAgentParams
    from app.channels.types import VoiceConfig

logger = logging.getLogger(__name__)

_SENTENCE_END = re.compile(r"[.!?。！？\n]")
_MAX_TRANSCRIPT_HISTORY = 12
_VOICE_SUPERVISOR_TIMEOUT_S = 15.0
_VOICE_SYSTEM_SUFFIX = (
    "\n\n[Voice Mode] "
    "You are in a live voice conversation. Keep responses concise, "
    "conversational, and natural. Do NOT use markdown formatting, "
    "bullet points, headers, or code blocks — the user will hear "
    "your reply spoken aloud. Summarize tool results in plain spoken language."
)
_WORKING_HINT_ZH = "正在处理中，请稍等"
_WORKING_HINT_EN = "Let me look into that"
_FALLBACK_ZH = "抱歉，处理时出了点问题，请再试一次"
_FALLBACK_EN = "Sorry, something went wrong. Please try again"
_APPROVAL_HINT_ZH = "这个操作需要您在屏幕上确认"
_APPROVAL_HINT_EN = "This action requires your confirmation on screen"
_HANDOFF_HINT_ZH = "这个任务需要较长时间，已转入后台继续处理，完成后会主动提醒您"
_HANDOFF_HINT_EN = "This task requires more time and has been moved to the background. I will notify you when it finishes"

_SPEECH_INTERRUPTED_NOTE = (
    "[Note: the user interrupted your previous spoken reply before it finished. "
    "Do not repeat what you already said; continue naturally or address their new input.]"
)
_INTERRUPT_TTL_S = 120.0


@dataclass(slots=True)
class _TranscriptEntry:
    role: str
    text: str


@dataclass
class VoiceAgentBridge:
    """Server-side Agent execution bridge for voice sessions."""

    _ws: WebSocket
    _voice_config: VoiceConfig
    _agent_id: str | None
    _chat_id: str | None
    _ws_send_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _closed: bool = False

    _cancel_token: CancellationToken | None = field(default=None, repr=False)
    _current_turn: str | None = field(default=None, repr=False)
    _transcript: list[_TranscriptEntry] = field(default_factory=list, repr=False)
    _tts_cancel_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _speech_interrupted_at: float | None = field(default=None, repr=False)

    async def handle_stt_final(self, text: str) -> None:
        """Process finalized STT text: cancel prior turn, invoke Agent, TTS."""
        t_start = time.monotonic()
        self._cancel_current_turn()

        turn_id = f"turn-{uuid.uuid4().hex[:8]}"
        self._current_turn = turn_id
        cancel_token = CancellationToken()
        self._cancel_token = cancel_token
        self._tts_cancel_event.clear()

        interrupted_prefix = self._take_speech_interrupted()
        effective_query = f"{interrupted_prefix}{text}" if interrupted_prefix else text

        self._transcript.append(_TranscriptEntry(role="user", text=text))
        if len(self._transcript) > _MAX_TRANSCRIPT_HISTORY:
            self._transcript = self._transcript[-_MAX_TRANSCRIPT_HISTORY:]

        await self._send_json({"type": "agent_thinking", "turn_id": turn_id})
        await self._send_json({"type": "stt_final", "text": text})

        t_params: float | None = None
        outcome = "ok"

        try:
            params = await self._build_agent_params(effective_query)
            t_params = time.monotonic()
            if params is None:
                outcome = "params_failed"
                await self._speak_fallback()
                return

            is_fast = self._is_fast_lane_query(effective_query, params)

            if not is_fast:
                await self._tts_working_hint()

            if is_fast:
                full_text, has_approval = await self._consume_fast_lane_stream(
                    params,
                    cancel_token,
                    turn_id,
                )
            else:
                full_text, has_approval = await self._consume_agent_stream_supervised(
                    params,
                    cancel_token,
                    turn_id,
                    effective_query,
                )

            if self._current_turn != turn_id:
                outcome = "superseded"
                return

            if full_text:
                self._transcript.append(_TranscriptEntry(role="assistant", text=full_text))
            elif has_approval:
                outcome = "approval_pending"
            else:
                await self._speak_fallback()

        except asyncio.CancelledError:
            outcome = "cancelled"
        except Exception:
            outcome = "error"
            logger.exception("Voice agent bridge error (turn=%s)", turn_id)
            if self._current_turn == turn_id:
                await self._speak_fallback()
        finally:
            t_end = time.monotonic()
            if self._current_turn == turn_id:
                await self._send_json({"type": "agent_done", "turn_id": turn_id})
                self._current_turn = None
                self._cancel_token = None

            _log_turn_latency(
                turn_id,
                outcome,
                t_start,
                t_params,
                t_end,
            )

    def cancel_tts(self) -> None:
        """Signal TTS cancellation (barge-in) and mark interrupted latch."""
        self._tts_cancel_event.set()
        self._speech_interrupted_at = time.monotonic()

    def _take_speech_interrupted(self) -> str:
        """Consume the interrupted latch if within TTL; return note prefix or empty."""
        at = self._speech_interrupted_at
        self._speech_interrupted_at = None
        if at is not None and (time.monotonic() - at) < _INTERRUPT_TTL_S:
            return _SPEECH_INTERRUPTED_NOTE + "\n"
        return ""

    def _cancel_current_turn(self) -> None:
        """Cancel any in-progress Agent execution."""
        if self._cancel_token:
            self._cancel_token.cancel(CancelReason.USER_CANCELLED)
        self._tts_cancel_event.set()
        self._current_turn = None
        self._cancel_token = None

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
        agent_task = asyncio.create_task(
            self._consume_agent_stream(params, cancel_token, turn_id)
        )

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

    # ── Agent parameter assembly ──────────────────────────────────────

    async def _build_agent_params(self, query: str) -> GeneralAgentParams | None:
        _ensure_model_rebuild()
        from app.ai_agents.agents import GeneralAgentParams
        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.config_parsers import (
            extract_fallback_model_configs,
            extract_lite_model_config,
            extract_mcp_configs,
            extract_retrieval_models,
            extract_user_instructions,
            merge_org_mcp_configs,
            resolve_vision_fallback_chain_for_agent,
            verify_search_service_available,
        )
        from app.core.channel_bridge.model_resolver import (
            enrich_model_capabilities,
            enrich_model_context_window,
            resolve_model_config,
        )
        from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

        try:
            configs = await load_user_configs()
        except Exception:
            logger.warning("Voice bridge: failed to load user configs")
            return None

        resolver = get_agent_profile_resolver()
        agent_id = self._agent_id or "builtin-general"
        profile = await resolver.resolve(agent_id)

        if profile and profile.model:
            agent_model_cfg = resolve_model_config(configs.providers_dict, model_override=profile.model)
            agent_model_cfg = enrich_model_capabilities(agent_model_cfg, configs.providers_dict)
            agent_model_cfg = enrich_model_context_window(agent_model_cfg, configs.providers_dict)
        else:
            agent_model_cfg = enrich_model_capabilities(configs.model_cfg, configs.providers_dict)
            agent_model_cfg = enrich_model_context_window(agent_model_cfg, configs.providers_dict)

        fallback_model_cfg, fallback_lite_model_cfg = extract_fallback_model_configs(configs.providers_dict)
        vision_fallback_model_cfg, vision_fallback_model_cfgs = resolve_vision_fallback_chain_for_agent(
            configs.providers_dict,
            main_model_cfg=(agent_model_cfg if agent_model_cfg.supports_vision else None),
        )
        lite_model_cfg = extract_lite_model_config(configs.providers_dict)
        embedding_cfg, reranker_cfg = extract_retrieval_models(configs.retrieval_dict)
        mcp_configs = merge_org_mcp_configs(
            extract_mcp_configs(configs.mcp_dict),
            configs.org_mcp_dict,
        )

        if mcp_configs and profile:
            from app.services.agent.params.mcp_selection import (
                apply_agent_mcp_selection,
            )

            mcp_configs = apply_agent_mcp_selection(
                mcp_configs,
                mcp_ids=profile.mcp_ids or None,
                mcp_tool_selections=profile.mcp_tool_selections or None,
            )

        search_available = await verify_search_service_available(configs.search_cfg)

        user_instructions = extract_user_instructions(configs.personal_settings_dict)

        if profile:
            if profile.system_prompt:
                user_instructions = (
                    f"{user_instructions}\n\n{profile.system_prompt}" if user_instructions else profile.system_prompt
                )
            from app.services.agent.params.profile_output_suffixes import (
                apply_profile_output_suffixes,
            )

            user_instructions = apply_profile_output_suffixes(
                user_instructions,
                personality_style=profile.personality_style,
                engine_params=profile.engine_params,
                agent_id=agent_id,
            )

        voice_instructions = (user_instructions or "") + _VOICE_SYSTEM_SUFFIX

        transcript_ctx = ""
        if self._transcript:
            recent = self._transcript[-_MAX_TRANSCRIPT_HISTORY:]
            lines = [f"{'User' if e.role == 'user' else 'Assistant'}: {e.text}" for e in recent]
            transcript_ctx = "\n\n[Recent voice transcript for context]\n" + "\n".join(lines)

        chat_id = self._chat_id or f"voice-{uuid.uuid4().hex[:12]}"
        message_id = f"vmsg-{uuid.uuid4().hex[:12]}"

        memory_settings = configs.personal_settings_dict or {}

        from app.api.voice.voice_memory_context import voice_memory_context_from
        from app.core.agent.tool_description_locale import resolve_agent_params_locale
        from app.services.agent.profile.profile_resolver import (
            DEFAULT_ENABLED_BUILTIN_TOOLS,
            resolve_builtin_tool_flags,
        )
        from app.services.agent.resolve_enable_web_fetch import resolve_enable_web_fetch
        from app.services.agent.tool_mount import ExecutionSurface, resolve_agent_mount

        agent_security_raw = (
            {str(k): v for k, v in profile.security_overrides.items()} if profile and profile.security_overrides else None
        )

        skill_ids = list(profile.skill_ids) if profile else []
        subagent_ids = list(profile.subagent_ids) if profile and profile.subagent_ids else None
        enabled_builtin_tools = list(profile.enabled_builtin_tools) if profile else list(DEFAULT_ENABLED_BUILTIN_TOOLS)
        memory_context = voice_memory_context_from(memory_settings, enabled_builtin_tools)

        return GeneralAgentParams(
            query=query + transcript_ctx,
            model_cfg=agent_model_cfg,
            fallback_model_cfg=fallback_model_cfg,
            lite_model_cfg=lite_model_cfg,
            fallback_lite_model_cfg=fallback_lite_model_cfg,
            vision_fallback_model_cfg=vision_fallback_model_cfg,
            vision_fallback_model_cfgs=vision_fallback_model_cfgs or None,
            search_service_cfg=configs.search_cfg,
            mcp_cfg=mcp_configs or None,
            user_instructions=voice_instructions,
            chat_id=chat_id,
            message_id=message_id,
            agent_id=agent_id,
            embedding_config=embedding_cfg,
            reranker_config=reranker_cfg,
            enable_memory=memory_context.enable_memory,
            enable_web_search=search_available,
            enable_web_fetch=resolve_enable_web_fetch(agent_security_raw),
            **resolve_agent_mount(
                ExecutionSurface.VOICE,
                resolve_builtin_tool_flags(enabled_builtin_tools),
            ),
            fetch_raw_webpage=bool(memory_settings.get("fetchRawWebpage")),
            enable_memory_auto_extraction=bool(memory_settings.get("enableMemoryAutoExtraction", True)),
            enable_conversation_search=memory_context.enable_conversation_search,
            agent_skill_ids=skill_ids,
            subagent_ids=subagent_ids,
            agent_security_raw=agent_security_raw,
            channel_name="voice_bridge",
            locale=resolve_agent_params_locale(
                personal_settings=memory_settings,
                channel="voice_bridge",
            ),
            providers_dict=configs.providers_dict,
        )

    # ── Agent stream consumption ──────────────────────────────────────

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
                tool_name = event.get("data", {}).get("name", "") if isinstance(event.get("data"), dict) else ""
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

    # ── Approval handling ─────────────────────────────────────────────

    async def _handle_approval_required(
        self,
        event: dict[str, object],
        turn_id: str,
    ) -> None:
        """Notify user via TTS and forward approval data through WebSocket.

        Handles both ``approval_required`` (generic interrupt) and
        ``tool_approval_request`` (structured HITL) events. The original
        event type is preserved so the frontend can dispatch accordingly.
        """
        event_type = event.get("type", "approval_required")
        approval_data = event.get("data", {})

        lang = (self._voice_config.stt_language or "").lower()
        hint = _APPROVAL_HINT_ZH if "zh" in lang or "cn" in lang else _APPROVAL_HINT_EN
        await self._stream_tts_segment(hint, turn_id)

        ws_payload: dict[str, object] = {
            "type": str(event_type),
            "turn_id": turn_id,
        }
        if isinstance(approval_data, dict):
            ws_payload["data"] = approval_data
        if "messageId" in event:
            ws_payload["messageId"] = event["messageId"]
        await self._send_json(ws_payload)

        logger.info(
            "Voice approval forwarded: turn=%s event_type=%s",
            turn_id,
            event_type,
        )

    # ── TTS helpers ───────────────────────────────────────────────────

    async def _stream_tts_segment(self, text: str, turn_id: str) -> None:
        """Stream a single TTS segment to the client."""
        if self._tts_cancel_event.is_set() or self._current_turn != turn_id:
            return

        from app.channels.voice.tts import synthesize_stream

        try:
            from fastapi import WebSocketDisconnect

            await self._send_json({"type": "tts_start"})
            async for chunk in synthesize_stream(text, self._voice_config):
                if self._tts_cancel_event.is_set() or self._current_turn != turn_id:
                    break
                try:
                    async with self._ws_send_lock:
                        await self._ws.send_bytes(chunk)
                except (WebSocketDisconnect, RuntimeError):
                    self._closed = True
                    break
            await self._send_json({"type": "tts_end"})
        except Exception:
            logger.warning("Voice bridge TTS segment error", exc_info=True)

    async def _tts_working_hint(self) -> None:
        """Speak a brief working hint while Agent processes."""
        lang = (self._voice_config.stt_language or "").lower()
        hint = _WORKING_HINT_ZH if "zh" in lang or "cn" in lang else _WORKING_HINT_EN
        await self._stream_tts_segment(hint, self._current_turn or "")

    async def _speak_fallback(self) -> None:
        """Speak a fallback message when Agent fails."""
        lang = (self._voice_config.stt_language or "").lower()
        msg = _FALLBACK_ZH if "zh" in lang or "cn" in lang else _FALLBACK_EN
        await self._stream_tts_segment(msg, self._current_turn or "")
        await self._send_json({"type": "agent_error", "message": "Agent execution failed"})

    # ── WebSocket helpers ─────────────────────────────────────────────

    async def _send_json(self, data: dict[str, object]) -> None:
        if self._closed:
            return
        try:
            async with self._ws_send_lock:
                await self._ws.send_text(json.dumps(data, ensure_ascii=False))
        except Exception:
            self._closed = True


_model_rebuilt = False


def _ensure_model_rebuild() -> None:
    """One-time Pydantic model rebuild for forward-ref resolution."""
    global _model_rebuilt  # noqa: PLW0603
    if _model_rebuilt:
        return
    from myrm_agent_harness.toolkits.memory.config import (
        EmbeddingConfig,
        RerankerConfig,
    )

    from app.ai_agents.agents import GeneralAgentParams

    GeneralAgentParams.model_rebuild(
        _types_namespace={
            "EmbeddingConfig": EmbeddingConfig,
            "RerankerConfig": RerankerConfig,
        }
    )
    _model_rebuilt = True


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


def _log_turn_latency(
    turn_id: str,
    outcome: str,
    t_start: float,
    t_params: float | None,
    t_end: float,
) -> None:
    """Log per-turn latency breakdown for production observability."""
    total_ms = int((t_end - t_start) * 1000)
    params_ms = int((t_params - t_start) * 1000) if t_params else None
    agent_tts_ms = int((t_end - t_params) * 1000) if t_params else None

    parts = [f"turn={turn_id}", f"outcome={outcome}", f"total={total_ms}ms"]
    if params_ms is not None:
        parts.append(f"params_assembly={params_ms}ms")
    if agent_tts_ms is not None:
        parts.append(f"agent_tts={agent_tts_ms}ms")

    logger.info("Voice turn latency: %s", " ".join(parts))
