"""Router lifecycle mixin: the consume loop, the janitor, and the stuck-task watchdog.

[INPUT]
- channels.routing.pipeline.hosts::RouterLifecycleHost (POS: typing protocol for the host attributes this mixin reads)
- channels.routing.router_constants::_CLEANUP_TTL, _JANITOR_INTERVAL, _MAX_CONCURRENT_AGENTS, _STUCK_TASK_TIMEOUT (POS: concurrency, cleanup TTL and watchdog limits)
- channels.routing.router_models::_ActiveTask (POS: record of one running agent turn)
- channels.i18n::get_text (POS: localized channel copy)
- core.infra.background_task::spawn_observed_task (POS: background task whose failure is logged)
- channels.types::InboundMessage, OutboundMessage (POS: channel message envelopes)

[OUTPUT]
- RouterLifecycleMixin: ``start`` / ``stop`` / ``is_consume_loop_alive``, the consume loop that hands every inbound message to dispatch, the janitor (expired callbacks, streaming-session TTL, stale session state) and the stuck-task reaper

[POS]
Run-loop segment of ``AgentRouter``. ``stop`` ends every in-flight turn and approval wait; the janitor is the only evictor of expired callbacks and stuck turns, so one failed sweep never ends it.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.channels.i18n import get_text
from app.channels.routing.pipeline.hosts import RouterLifecycleHost
from app.channels.routing.router_constants import (
    _CLEANUP_TTL,
    _JANITOR_INTERVAL,
    _MAX_CONCURRENT_AGENTS,
    _STUCK_TASK_TIMEOUT,
)
from app.channels.routing.router_models import _ActiveTask
from app.channels.types import InboundMessage, OutboundMessage
from app.core.infra.background_task import spawn_observed_task

logger = logging.getLogger("app.channels.routing.router")


class RouterLifecycleMixin:
    """Mixin: start and stop the router, the janitor sweep and the stuck-task watchdog."""

    # Assigned here, created in ``AgentRouter.__init__``.
    _task: asyncio.Task[None] | None
    _janitor_task: asyncio.Task[None] | None

    def is_consume_loop_alive(self: RouterLifecycleHost) -> bool:
        """Whether the consume loop task is still running; a finished task means it died."""
        return self._running and self._task is not None and not self._task.done()

    async def start(self: RouterLifecycleHost) -> None:
        """Start the inbound message consumption loop.

        Also the restart entry point: when the previous task has finished (a crash the
        loop could not absorb) a new task starts, so the gateway health cycle can call
        this to bring inbound routing back.
        """
        if self.is_consume_loop_alive():
            return
        self._running = True
        self._task = spawn_observed_task(self._consume_loop(), name="agent_router_consume")
        self._start_janitor()
        logger.info("AgentRouter started (max_concurrent=%d)", _MAX_CONCURRENT_AGENTS)

    async def stop(self: RouterLifecycleHost) -> None:
        """Stop the consumption loop and cancel all in-flight agent tasks.

        Delegated tasks are interrupted first, while the channels are still up, so each tells its chat the work was cut short.
        """
        self._running = False
        await self._delegation_coordinator.interrupt_all()

        for entry in self._active_tasks.values():
            entry.cancel_token.cancel("Router stopping")
            if not entry.task.done():
                entry.task.cancel()

        self._active_tasks.clear()
        self._cleanups.clear()
        self._pending_approvals.clear()

        await self._stop_janitor()

        if self._task:
            if not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None

        self._seen_messages.clear()
        self._gate.clear()
        logger.info("AgentRouter stopped")

    def _start_janitor(self: RouterLifecycleHost) -> None:
        if self._janitor_task is None or self._janitor_task.done():
            self._janitor_task = spawn_observed_task(self._janitor_loop(), name="agent_router_janitor")

    async def _stop_janitor(self: RouterLifecycleHost) -> None:
        if self._janitor_task and not self._janitor_task.done():
            self._janitor_task.cancel()
            try:
                await self._janitor_task
            except asyncio.CancelledError:
                pass

    _SESSION_STATE_TTL = 86400.0  # 24h TTL for session-level state (yolo/personality)

    _NEW_SESSION_PEER_TTL = 3600.0  # 1h TTL for /new markers

    async def _janitor_loop(self: RouterLifecycleHost) -> None:
        while True:
            await asyncio.sleep(_JANITOR_INTERVAL)
            try:
                await self._janitor_sweep()
            except Exception:
                # The janitor is the only evictor of expired callbacks, streaming sessions and
                # stuck tasks, so one failed sweep must not end it.
                logger.exception("[JANITOR] Sweep failed, retrying next cycle")

    async def _janitor_sweep(self: RouterLifecycleHost) -> None:
        now = time.monotonic()
        expired_keys = [key for key, entry in self._cleanups.items() if now - entry.created_at > _CLEANUP_TTL]
        for key in expired_keys:
            entry = self._cleanups.pop(key, None)
            if entry:
                try:
                    await entry.cleanup()
                except Exception as e:
                    logger.warning("[JANITOR] Cleanup failed for %s: %s", key, e)
        if expired_keys:
            logger.info("[JANITOR] Cleaned up %d expired callbacks", len(expired_keys))

        coordinator_cleaned = self._stream_coordinator.cleanup_expired_sessions()
        estimator_cleaned = self._progress_estimator.cleanup_expired_sessions()
        if coordinator_cleaned > 0 or estimator_cleaned > 0:
            logger.info(
                "[JANITOR] Streaming TTL cleanup: coordinator=%d, estimator=%d",
                coordinator_cleaned,
                estimator_cleaned,
            )

        self._cleanup_stale_session_state(now)
        await self._reap_stuck_tasks(now)

    def _cleanup_stale_session_state(self: RouterLifecycleHost, now_monotonic: float) -> None:
        """Evict stale entries from _new_session_peers, _session_yolo, _session_personality."""
        peer_cutoff = now_monotonic - self._NEW_SESSION_PEER_TTL
        stale_peers = [k for k, ts in self._new_session_peers.items() if ts < peer_cutoff]
        for k in stale_peers:
            del self._new_session_peers[k]

        # _session_yolo uses time.time() (wall clock), not monotonic
        wall_now = time.time()
        yolo_cutoff = wall_now - self._SESSION_STATE_TTL
        stale_yolo = [k for k, (enabled_at, _timeout) in self._session_yolo.items() if enabled_at < yolo_cutoff]
        for k in stale_yolo:
            del self._session_yolo[k]

        if len(self._session_personality) > 1000:
            stale_personality = [
                k for k in self._session_personality if k not in self._session_yolo and k not in self._active_tasks
            ]
            for k in stale_personality:
                del self._session_personality[k]

        total_cleaned = len(stale_peers) + len(stale_yolo)
        if total_cleaned > 0:
            logger.info(
                "[JANITOR] Session state cleanup: peers=%d, yolo=%d",
                len(stale_peers),
                len(stale_yolo),
            )

    async def _reap_stuck_tasks(self: RouterLifecycleHost, now: float) -> None:
        """Cancel agent tasks that exceed _STUCK_TASK_TIMEOUT and release all held resources.

        For each stuck task: cancel the CancellationToken + asyncio.Task, stop typing
        indicators, clean up placeholders, remove from _active_tasks, release the SessionGate
        turn the task ran as (a no-op when the cancelled task already ended it), and notify the
        user with a localized timeout message.
        """
        stuck_entries: list[tuple[str, _ActiveTask]] = [
            (key, entry)
            for key, entry in self._active_tasks.items()
            if now - entry.started_at > _STUCK_TASK_TIMEOUT and not entry.task.done()
        ]
        for state_key, entry in stuck_entries:
            elapsed = int(now - entry.started_at)
            logger.warning(
                "[JANITOR] Stuck task detected: key=%s channel=%s chat=%s elapsed=%ds (limit=%ds), cancelling",
                state_key,
                entry.channel,
                entry.chat_id,
                elapsed,
                int(_STUCK_TASK_TIMEOUT),
            )
            entry.cancel_token.cancel("Stuck task watchdog timeout")
            if not entry.task.done():
                entry.task.cancel()

            self._active_tasks.pop(state_key, None)
            self._cleanups.pop(state_key, None)
            self._pending_approvals.pop(state_key)

            synthetic_msg = InboundMessage(
                channel=entry.channel,
                sender_id="",
                content="",
                chat_id=entry.chat_id,
                metadata={"locale": entry.locale} if entry.locale else {},
            )

            try:
                await self._fx.stop_typing_keepalive(entry.channel, entry.chat_id)
                await self._fx.set_typing(entry.channel, entry.chat_id, composing=False)
            except Exception:
                logger.debug("[JANITOR] Typing cleanup failed for %s (non-critical)", state_key)

            timeout_msg = get_text(
                synthetic_msg,
                "stuck_task_timeout_user_message",
                elapsed=elapsed,
            )
            if entry.placeholder_id:
                try:
                    await self._fx.cleanup_placeholder(entry.channel, entry.chat_id, entry.placeholder_id, timeout_msg)
                except Exception:
                    logger.debug(
                        "[JANITOR] Placeholder cleanup failed for %s (non-critical)",
                        state_key,
                    )
            else:
                try:
                    reply = OutboundMessage(
                        channel=entry.channel,
                        recipient_id=entry.chat_id,
                        content=timeout_msg,
                        user_id="",
                    )
                    await self._bus.publish_outbound(reply)
                except Exception:
                    logger.debug(
                        "[JANITOR] Timeout notification failed for %s (non-critical)",
                        state_key,
                    )

            self._gate.release_turn(entry.gate_key, entry.gate_turn)
            logger.info("[JANITOR] Stuck task reaped: key=%s elapsed=%ds", state_key, elapsed)

        if stuck_entries:
            logger.warning("[JANITOR] Reaped %d stuck task(s)", len(stuck_entries))

        self._delegation_coordinator.reap_stale_tasks()

    async def _consume_loop(self: RouterLifecycleHost) -> None:
        """Continuously consume inbound messages and dispatch via SessionGate.

        Uses CommandRegistry.resolve() for O(1) slash command dispatch instead
        of a linear if-elif chain. Approval commands are still checked first
        because they include non-slash shortcuts (1, y, yes, etc.).

        One message is dispatched at a time in isolation: a handler error is logged and
        the loop keeps consuming, so a single poisoned message cannot stop every channel.
        """
        while self._running:
            try:
                msg = await asyncio.wait_for(self._bus.consume_inbound(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await self._dispatch_inbound_message(msg)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Inbound message dispatch failed (channel=%s, message_id=%s); continuing",
                    msg.channel,
                    msg.message_id,
                )
