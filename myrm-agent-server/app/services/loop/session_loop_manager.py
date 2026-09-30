"""Session Loop Manager — lifecycle orchestration for in-session recurring loops.

[INPUT]
- /loop command string or REST start/stop invocations
- Chat ID and active database session

[OUTPUT]
- SessionLoopStartResult and broadcasted SessionLoopStatusDTO
- Background scheduling tasks updating Chat.extra_data["active_loop"]

[POS]
Server service layer. Bridges harness stateless algorithms with persistent Chat state,
enforcing 5 deterministic stop gates and prompt cache preservation.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from myrm_agent_harness.runtime.loop import (
    AdaptiveBackoffCalculator,
    LoopConfig,
    LoopMode,
    LoopState,
    LoopStatus,
    LoopStopReason,
    build_wakeup_prompt,
    is_loop_complete_response,
    parse_loop_args,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session
from app.database.models import Chat
from app.services.loop.session_loop_types import (
    SessionLoopStartResult,
    SessionLoopStatusDTO,
)
from app.services.loop.session_turn_arbiter import SessionTurnArbiter

logger = logging.getLogger(__name__)

StatusListener = Callable[[SessionLoopStatusDTO], Awaitable[None]]


class SessionLoopManager:
    """Manages session-scoped loop tasks, state persistence, and backoff pacing."""

    _instance: SessionLoopManager | None = None

    def __init__(self) -> None:
        self._active_loops: dict[str, LoopState] = {}
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._listeners: set[StatusListener] = set()
        self._backoff_calc = AdaptiveBackoffCalculator()
        self._arbiter = SessionTurnArbiter.get_instance()
        # Mockable turnaround hook for tests and custom turn execution
        self.turn_executor: Callable[[str, str], Awaitable[str]] | None = None

    @classmethod
    def get_instance(cls) -> SessionLoopManager:
        """Access singleton manager instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add_listener(self, listener: StatusListener) -> None:
        """Register status update listener (e.g. for SSE forwarding)."""
        self._listeners.add(listener)

    def remove_listener(self, listener: StatusListener) -> None:
        """Unregister status update listener."""
        self._listeners.discard(listener)

    async def _notify_listeners(self, status: SessionLoopStatusDTO) -> None:
        """Broadcast status change to registered listeners."""
        for listener in list(self._listeners):
            try:
                await listener(status)
            except Exception as exc:
                logger.debug("Failed notifying loop status listener: %s", exc)

    async def start_loop(
        self,
        chat_id: str,
        command_text: str,
        *,
        db: AsyncSession | None = None,
    ) -> SessionLoopStartResult:
        """Start or replace an active loop for the given chat session."""
        config: LoopConfig = parse_loop_args(command_text)
        if not config.is_valid:
            return SessionLoopStartResult(success=False, error=config.error or "Invalid loop command")

        # Stop existing task if active
        await self.stop_loop(chat_id, reason=LoopStopReason.USER_PREEMPTED, db=db)

        now = time.time()
        initial_delay = float(config.interval_seconds or self._backoff_calc.floor_seconds)
        state = LoopState(
            session_id=chat_id,
            prompt=config.prompt,
            status=LoopStatus.ACTIVE,
            mode=config.mode,
            interval_seconds=initial_delay,
            current_delay=initial_delay,
            times=config.times,
            until=config.until,
            created_at=now,
            last_fired_at=0.0,
            next_due_at=now,  # First tick fires immediately
        )

        self._active_loops[chat_id] = state
        await self._persist_state(chat_id, state, db=db)

        # Spawn background scheduler worker
        task = asyncio.create_task(self._run_loop_worker(chat_id))
        self._active_tasks[chat_id] = task

        status_dto = SessionLoopStatusDTO.from_loop_state(state, now)
        await self._notify_listeners(status_dto)
        logger.info("SessionLoopManager: started %s loop for chat %s", state.cadence_label(), chat_id)
        return SessionLoopStartResult(success=True, status=status_dto)

    async def stop_loop(
        self,
        chat_id: str,
        *,
        reason: LoopStopReason = LoopStopReason.USER_STOPPED,
        db: AsyncSession | None = None,
    ) -> bool:
        """Stop active loop for chat and persist termination reason."""
        task = self._active_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        state = self._active_loops.get(chat_id)
        if state is None:
            state = await self._hydrate_state(chat_id, db=db)

        if state is None or state.status != LoopStatus.ACTIVE:
            return False

        state.status = LoopStatus.STOPPED if reason == LoopStopReason.USER_STOPPED else LoopStatus.COMPLETED
        state.last_stop_reason = reason
        self._active_loops[chat_id] = state
        self._arbiter.clean_chat(chat_id)

        await self._persist_state(chat_id, state, db=db)
        status_dto = SessionLoopStatusDTO.from_loop_state(state, time.time())
        await self._notify_listeners(status_dto)
        logger.info("SessionLoopManager: stopped loop for chat %s (reason: %s)", chat_id, reason.value)
        return True

    async def get_status(
        self,
        chat_id: str,
        *,
        db: AsyncSession | None = None,
    ) -> SessionLoopStatusDTO | None:
        """Fetch current status DTO from memory or DB."""
        state = self._active_loops.get(chat_id)
        if state is None:
            state = await self._hydrate_state(chat_id, db=db)
            if state is not None:
                self._active_loops[chat_id] = state

        if state is None:
            return None
        return SessionLoopStatusDTO.from_loop_state(state, time.time())

    async def _run_loop_worker(self, chat_id: str) -> None:
        """Background worker executing cadence ticks and evaluating stop conditions."""
        try:
            while True:
                state = self._active_loops.get(chat_id)
                if state is None or state.status != LoopStatus.ACTIVE:
                    break

                now = time.time()
                wait_time = max(0.05, state.next_due_at - now)
                await asyncio.sleep(wait_time)

                # Concurrency arbitration: defer if user recently typed
                if self._arbiter.should_defer_loop_wakeup(chat_id):
                    state.next_due_at = time.time() + 5.0
                    continue

                state.awaiting_response = True
                state.ticks_fired += 1
                state.last_fired_at = time.time()

                # Build wakeup prompt and execute turn
                prompt = build_wakeup_prompt(
                    tick=state.ticks_fired,
                    prompt=state.prompt,
                    until=state.until,
                    cadence_label=state.cadence_label(),
                )

                response_text = ""
                if self.turn_executor is not None:
                    response_text = await self.turn_executor(chat_id, prompt)

                state.awaiting_response = False

                # Stop gate 1: Model complete marker
                if is_loop_complete_response(response_text):
                    state.status = LoopStatus.COMPLETED
                    state.last_stop_reason = LoopStopReason.MODEL_SIGNAL
                    await self._persist_state(chat_id, state)
                    await self._notify_listeners(SessionLoopStatusDTO.from_loop_state(state, time.time()))
                    break

                # Stop gate 2: User run cap (--times N)
                if state.times > 0 and state.ticks_fired >= state.times:
                    state.status = LoopStatus.COMPLETED
                    state.last_stop_reason = LoopStopReason.TIMES_EXHAUSTED
                    await self._persist_state(chat_id, state)
                    await self._notify_listeners(SessionLoopStatusDTO.from_loop_state(state, time.time()))
                    break

                # Stop gate 3: Max ticks backstop budget
                if state.max_ticks > 0 and state.ticks_fired >= state.max_ticks:
                    state.status = LoopStatus.PAUSED
                    state.last_stop_reason = LoopStopReason.MAX_TICKS_REACHED
                    state.paused_reason = f"Reached maximum backstop limit of {state.max_ticks} ticks"
                    await self._persist_state(chat_id, state)
                    await self._notify_listeners(SessionLoopStatusDTO.from_loop_state(state, time.time()))
                    break

                # Calculate next cadence delay via adaptive backoff
                if state.mode == LoopMode.SELF_PACED:
                    decision = self._backoff_calc.evaluate(
                        response_text,
                        previous_digest=state.last_response_digest,
                        current_delay=state.current_delay,
                        consecutive_unchanged=state.consecutive_unchanged,
                    )
                    state.current_delay = decision.next_delay
                    state.consecutive_unchanged = decision.consecutive_unchanged
                    state.last_response_digest = decision.current_digest
                    next_delay = decision.next_delay
                else:
                    next_delay = state.interval_seconds

                state.next_due_at = time.time() + next_delay
                await self._persist_state(chat_id, state)
                await self._notify_listeners(SessionLoopStatusDTO.from_loop_state(state, time.time()))

        except asyncio.CancelledError:
            logger.debug("Loop worker cancelled for chat %s", chat_id)
        except Exception as exc:
            logger.exception("Unexpected error in loop worker for chat %s: %s", chat_id, exc)
            if chat_id in self._active_loops:
                self._active_loops[chat_id].status = LoopStatus.STOPPED
                self._active_loops[chat_id].last_stop_reason = LoopStopReason.ERROR

    async def _persist_state(self, chat_id: str, state: LoopState, *, db: AsyncSession | None = None) -> None:
        """Persist loop state dictionary inside Chat.extra_data['active_loop']."""
        async def _do_persist(session: AsyncSession) -> None:
            stmt = select(Chat).where(Chat.id == chat_id)
            result = await session.execute(stmt)
            chat = result.scalar_one_or_none()
            if chat is not None:
                # Chat model extra data fallback
                current_notes = getattr(chat, "extra_data", None)
                extra: dict[str, Any] = dict(current_notes) if isinstance(current_notes, dict) else {}
                extra["active_loop"] = state.to_dict()
                if hasattr(chat, "extra_data"):
                    chat.extra_data = extra
                await session.commit()

        if db is not None:
            await _do_persist(db)
        else:
            async with get_session() as session:
                await _do_persist(session)

    async def _hydrate_state(self, chat_id: str, *, db: AsyncSession | None = None) -> LoopState | None:
        """Hydrate LoopState from Chat.extra_data['active_loop'] if present."""
        async def _do_hydrate(session: AsyncSession) -> LoopState | None:
            stmt = select(Chat).where(Chat.id == chat_id)
            result = await session.execute(stmt)
            chat = result.scalar_one_or_none()
            if chat is not None:
                current_extra = getattr(chat, "extra_data", None)
                if isinstance(current_extra, dict):
                    raw_loop = current_extra.get("active_loop")
                    if isinstance(raw_loop, dict):
                        return LoopState.from_dict(raw_loop)
            return None

        if db is not None:
            return await _do_hydrate(db)
        async with get_session() as session:
            return await _do_hydrate(session)
