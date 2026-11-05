"""[INPUT]
- .common (POS: shared types and constants)

[OUTPUT]
- TurnMixin

[POS]
Voice bridge mixin: one voice turn: STT finalization, cancellation, approvals and websocket sends.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason

if TYPE_CHECKING:
    pass

from .common import (
    _APPROVAL_HINT_EN,
    _APPROVAL_HINT_ZH,
    _MAX_TRANSCRIPT_HISTORY,
    _TOOL_STUCK_HINT_EN,
    _TOOL_STUCK_HINT_ZH,
    _TranscriptEntry,
    logger,
)


class TurnMixin:
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

    def _cancel_current_turn(self) -> None:
        """Cancel any in-progress Agent execution."""
        if self._cancel_token:
            self._cancel_token.cancel(CancelReason.USER_CANCELLED)
        self._tts_cancel_event.set()
        self._current_turn = None
        self._cancel_token = None

    async def _handle_approval_required(
        self,
        event: dict[str, object],
        turn_id: str,
    ) -> None:
        """Notify user via TTS and forward approval data through WebSocket.

        Handles both ``approval_required`` (generic interrupt) and
        ``tool_approval_request`` (structured HITL) events. The original
        event type is preserved so the frontend can dispatch accordingly.
        A loop guard pause arrives as ``approval_required`` but waits on no answer, so it is
        spoken as a stop rather than as a request to confirm on screen.
        """
        from app.services.agent.approval_payload import is_tool_stuck_pause

        event_type = event.get("type", "approval_required")
        approval_data = event.get("data", {})

        lang = (self._voice_config.stt_language or "").lower()
        speaks_chinese = "zh" in lang or "cn" in lang
        if is_tool_stuck_pause(approval_data):
            # Parallel tool calls can stop together; the stop is said once per turn.
            if self._stop_spoken_turn != turn_id:
                self._stop_spoken_turn = turn_id
                await self._stream_tts_segment(_TOOL_STUCK_HINT_ZH if speaks_chinese else _TOOL_STUCK_HINT_EN, turn_id)
        else:
            await self._stream_tts_segment(_APPROVAL_HINT_ZH if speaks_chinese else _APPROVAL_HINT_EN, turn_id)

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

    async def _send_json(self, data: dict[str, object]) -> None:
        if self._closed:
            return
        try:
            async with self._ws_send_lock:
                await self._ws.send_text(json.dumps(data, ensure_ascii=False))
        except Exception:
            self._closed = True


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
