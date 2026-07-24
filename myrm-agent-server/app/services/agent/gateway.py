"""Agent Execution Gateway — concurrency, timeout, memory pressure, and observability.

Unified entry point for all Agent executions.
Provides global + per-user concurrency control, memory pressure circuit breaker,
execution timeout, graceful queue rejection, and structured logging.

[INPUT]
- AsyncGenerator[dict, None]: bound agent stream from any Agent type

[OUTPUT]
- AsyncGenerator[dict, None]: same events, wrapped with lifecycle management
- AgentQueueTimeout: raised when queue wait exceeds limit
- AgentExecutionTimeout: raised when execution exceeds limit

[POS]
Agent 执行网关。所有 Agent 执行（General / FastSearch）
都经过此网关，确保并发控制、内存压力熔断、超时保护和可观测性。
"""

from __future__ import annotations

import asyncio
import logging
import time
import weakref
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.base_agent import BaseAgent
    from myrm_agent_harness.runtime.memory_pressure import PressureEvent

logger = logging.getLogger(__name__)


class AgentQueueTimeout(Exception):
    """Raised when waiting for an execution slot exceeds the queue timeout."""


class AgentExecutionTimeout(Exception):
    """Raised when agent execution exceeds the execution timeout."""


class AgentBusyError(Exception):
    """Raised when attempting to execute a request on a session that is already active."""


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    """Configuration for AgentGateway."""

    max_global: int = 20
    max_per_user: int = 3
    queue_timeout: float = 10.0
    execution_timeout: float = 300.0

    @classmethod
    def from_settings(cls) -> GatewayConfig:
        from app.config.settings import settings

        ag = settings.agent
        return cls(
            max_global=ag.max_concurrent,
            max_per_user=ag.max_per_user,
            queue_timeout=ag.queue_timeout,
            execution_timeout=ag.execution_timeout,
        )


@dataclass(slots=True)
class ActiveSessionInfo:
    """Metadata for a currently executing agent session."""

    chat_id: str
    agent_type: str
    started_at: float = field(default_factory=time.monotonic)
    agent: "weakref.ReferenceType[BaseAgent] | None" = None
    current_message_id: str | None = None
    agent_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "chatId": self.chat_id,
            "agentType": self.agent_type,
            "elapsedSeconds": round(time.monotonic() - self.started_at, 1),
        }
        if self.agent_id is not None:
            result["agentId"] = self.agent_id
        return result


class AgentGateway:
    """Unified execution gateway for all Agent types.

    Wraps any agent's async event stream with:
    - Global concurrency limit (prevents server overload)
    - Per-user concurrency limit (prevents single-user monopoly)
    - Memory pressure circuit breaker (queues new agents until pressure resolves)
    - Queue timeout (graceful 429 instead of infinite wait)
    - Execution timeout (kills zombie agents)
    - Structured logging (duration, status, agent_type)

    Implements PressureSubscriber to receive memory pressure notifications.
    When pressure reaches CRITICAL or EMERGENCY, new agent executions wait
    until pressure de-escalates or queue_timeout expires.
    """

    def __init__(self, config: GatewayConfig | None = None) -> None:
        cfg = config or GatewayConfig.from_settings()
        self._config = cfg
        self._global_sem = asyncio.Semaphore(cfg.max_global)
        self._user_sems: dict[str, asyncio.Semaphore] = {}
        self._active_count = 0
        self._interrupt_events: dict[str, dict[str, asyncio.Event]] = {}
        self._active_sessions: set[str] = set()
        self._session_info: dict[str, ActiveSessionInfo] = {}

        from myrm_agent_harness.runtime.memory_pressure import PressureLevel

        self._memory_pressure_level: PressureLevel = PressureLevel.NORMAL
        self._pressure_resolved = asyncio.Event()
        self._pressure_resolved.set()

        logger.info(
            "AgentGateway initialized: max_global=%d, max_per_user=%d, queue_timeout=%.0fs, execution_timeout=%.0fs",
            cfg.max_global,
            cfg.max_per_user,
            cfg.queue_timeout,
            cfg.execution_timeout,
        )

    @property
    def active_count(self) -> int:
        return self._active_count

    @property
    def config(self) -> GatewayConfig:
        return self._config

    def _get_user_sem(self, user_id: str) -> asyncio.Semaphore:
        sem = self._user_sems.get(user_id)
        if sem is None:
            sem = asyncio.Semaphore(self._config.max_per_user)
            self._user_sems[user_id] = sem
        return sem

    def interrupt(self) -> bool:
        """Signal all running agents for a user to stop.

        Returns True if any agent was interrupted, False if no active agent found.
        Called by the CP pipeline via /api/agent/interrupt endpoint.
        """
        user_events = self._interrupt_events.get("sandbox")
        if user_events:
            for event in user_events.values():
                event.set()
            logger.info(
                "Interrupt signal sent for sandbox (%d agents)", len(user_events)
            )
            return True
        logger.debug("No active agent to interrupt for sandbox user")
        return False

    def interrupt_session(self, chat_id: str) -> bool:
        """Signal a single chat session to stop.

        Returns True when an interrupt event was set for ``chat_id``.
        """
        user_events = self._interrupt_events.get("sandbox")
        if not user_events:
            return False
        event = user_events.get(chat_id)
        if event is None:
            return False
        event.set()
        logger.info("Interrupt signal sent for chat_id=%s", chat_id)
        return True

    def get_active_message_id(self, chat_id: str) -> str | None:
        info = self._session_info.get(chat_id)
        return info.current_message_id if info else None

    def get_active_sessions(self) -> list[dict[str, object]]:
        """Get active session info for a specific user (for Multi-Pane status)."""
        return [info.to_dict() for info in self._session_info.values()]

    def get_available_slots(self) -> int:
        """Get the number of available concurrent execution slots for a user."""
        sem = self._user_sems.get("sandbox")
        if sem is None:
            return self._config.max_per_user
        return max(0, sem._value)

    def get_active_browser_session(
        self, session_id: str | None = None
    ) -> object | None:
        """Get the BrowserSession from any currently active agent, if available.

        Args:
            session_id: Optional chat/session ID to filter by.
        """
        if session_id:
            info = self._session_info.get(session_id)
            if not info or info.agent is None:
                return None
            agent = info.agent()
            return getattr(agent, "_browser_session", None) if agent else None

        for info in self._session_info.values():
            if info.agent is None:
                continue
            agent = info.agent()
            if agent is None:
                continue
            session = getattr(agent, "_browser_session", None)
            if session is not None:
                return session
        return None

    def get_active_desktop_session(
        self, session_id: str | None = None
    ) -> object | None:
        """Get the DesktopSession from any currently active agent, if available.

        Args:
            session_id: Optional chat/session ID to filter by.
        """
        if session_id:
            info = self._session_info.get(session_id)
            if not info or info.agent is None:
                return None
            agent = info.agent()
            return getattr(agent, "_desktop_session", None) if agent else None

        for info in self._session_info.values():
            if info.agent is None:
                continue
            agent = info.agent()
            if agent is None:
                continue
            session = getattr(agent, "_desktop_session", None)
            if session is not None:
                return session
        return None

    def reset_all_desktop_session_permission_caches(self) -> int:
        """Reset harness desktop session in-memory approval shortcuts on all agents."""
        cleared = 0
        for info in self._session_info.values():
            if info.agent is None:
                continue
            agent = info.agent()
            if agent is None:
                continue
            session = getattr(agent, "_desktop_session", None)
            if session is None:
                continue
            reset_fn = getattr(session, "reset_runtime_permission_cache", None)
            if callable(reset_fn):
                reset_fn()
                cleared += 1
        return cleared

    def get_active_event_log_backend(self) -> tuple[str, object] | None:
        """Get (session_id, EventLogBackend) from the first active agent that has one."""
        for info in self._session_info.values():
            if info.agent is None:
                continue
            agent = info.agent()
            if agent is None:
                continue
            backend = getattr(agent, "event_log_backend", None)
            if backend is not None:
                return info.chat_id, backend
        return None

    def interrupt_all(self) -> int:
        """Interrupt all running agents. Returns count of interrupted users."""
        count = 0
        for user_events in self._interrupt_events.values():
            for event in user_events.values():
                event.set()
            count += 1
        return count

    async def on_pressure_change(self, event: "PressureEvent") -> None:
        """PressureSubscriber callback — update circuit breaker state.

        CRITICAL/EMERGENCY → block new executions (clear the Event).
        NORMAL/WARNING → allow new executions (set the Event).
        Already-running agents are NOT interrupted — only new ones are queued.
        """
        from myrm_agent_harness.runtime.memory_pressure import PressureLevel

        self._memory_pressure_level = event.level
        if event.level >= PressureLevel.CRITICAL:
            self._pressure_resolved.clear()
            logger.warning(
                "AgentGateway: memory pressure circuit breaker OPEN (level=%s, mem=%.1f%%)",
                event.level.name,
                event.memory_percent,
            )
        else:
            self._pressure_resolved.set()
            if event.de_escalated:
                logger.info(
                    "AgentGateway: memory pressure circuit breaker CLOSED (level=%s, mem=%.1f%%)",
                    event.level.name,
                    event.memory_percent,
                )

    # 长时目标（代码重构、大规模分析）禁用常规超时所用的上限
    GOAL_ACTIVE_TIMEOUT_SECONDS = 3600.0

    def _resolve_effective_timeout(
        self, *, goal_active: bool, fission_active: bool
    ) -> float:
        """Resolve execution timeout by tier (goal > fission > default).

        - goal_active: 长时任务禁用常规超时。
        - fission_active: Swarm Fission 并行子任务需 2x 时间。
        - default: 配置的 execution_timeout。
        """
        if goal_active:
            return self.GOAL_ACTIVE_TIMEOUT_SECONDS
        if fission_active:
            return self._config.execution_timeout * 2
        return self._config.execution_timeout

    async def execute_stream(
        self,
        stream: AsyncGenerator[dict[str, object], None],
        *,
        agent_type: str,
        session_id: str | None = None,
        agent_instance: "BaseAgent | None" = None,
        active_message_id: str | None = None,
        goal_active: bool = False,
        fission_active: bool = False,
        agent_id: str | None = None,
    ) -> AsyncGenerator[dict[str, object], None]:
        """Execute an agent stream with full lifecycle management.

        Args:
            stream: Bound agent event stream (from agent.process_stream).
            agent_type: Agent category for logging ("general").
            session_id: Optional chat/session ID for concurrency protection.
            agent_instance: Optional BaseAgent for weak-ref tracking.
            goal_active: When True, disables execution timeout to allow
                long-running goals (code refactoring, large-scale analysis)
                to complete without interruption.
            fission_active: When True, extends execution timeout for Swarm
                Fission parallel subagent batches.
            agent_id: Optional agent profile ID for Fleet Overview status.

        Yields:
            Agent events (dict), transparently forwarded.

        Raises:
            AgentQueueTimeout: Queue wait exceeded queue_timeout.
            AgentExecutionTimeout: Execution exceeded execution_timeout.
            AgentBusyError: Session is already active.
        """
        if session_id:
            if session_id in self._active_sessions:
                raise AgentBusyError(f"Session {session_id} is already active")
            self._active_sessions.add(session_id)
            self._session_info[session_id] = ActiveSessionInfo(
                chat_id=session_id,
                agent_type=agent_type,
                agent=weakref.ref(agent_instance) if agent_instance else None,
                current_message_id=active_message_id,
                agent_id=agent_id,
            )

        user_sem = self._get_user_sem("sandbox")

        try:
            async with asyncio.timeout(self._config.queue_timeout):
                # Phase 1: Wait for memory pressure to resolve (if CRITICAL/EMERGENCY)
                if not self._pressure_resolved.is_set():
                    logger.info(
                        "AgentGateway: queuing new %s execution — memory pressure %s",
                        agent_type,
                        self._memory_pressure_level.name,
                    )
                    await self._pressure_resolved.wait()

                # Phase 2: Acquire concurrency slots
                await self._global_sem.acquire()
                try:
                    await user_sem.acquire()
                except BaseException:
                    self._global_sem.release()
                    raise
        except TimeoutError:
            if session_id:
                self._active_sessions.discard(session_id)
                self._session_info.pop(session_id, None)
            reason = (
                f"Memory pressure ({self._memory_pressure_level.name})"
                if not self._pressure_resolved.is_set()
                else f"active={self._active_count}/{self._config.max_global}"
            )
            raise AgentQueueTimeout(
                f"Queue timeout ({self._config.queue_timeout:.0f}s) — {reason}"
            ) from None

        self._active_count += 1
        started_at = time.monotonic()
        status = "success"

        if session_id:
            from app.services.agent.streaming_support.multiplexer import (
                WorkspaceMultiplexer,
            )

            WorkspaceMultiplexer.get().publish_session_status(
                session_id, "generating", agent_type
            )

        interrupt_event = asyncio.Event()
        event_key = session_id or f"_anon_{id(interrupt_event)}"
        self._interrupt_events.setdefault("sandbox", {})[event_key] = interrupt_event

        def _recursive_scrub(data: object) -> object:
            from myrm_agent_harness.toolkits.code_execution.executors.models import (
                scrub_sensitive_info,
            )

            if isinstance(data, dict):
                return {k: _recursive_scrub(v) for k, v in data.items()}
            if isinstance(data, list):
                return [_recursive_scrub(item) for item in data]
            if isinstance(data, str):
                return scrub_sensitive_info(data)
            return data

        effective_timeout = self._resolve_effective_timeout(
            goal_active=goal_active, fission_active=fission_active
        )

        try:
            async with asyncio.timeout(effective_timeout):
                async for event in stream:
                    if interrupt_event.is_set():
                        status = "interrupted"
                        logger.info("Agent interrupted for sandbox user")
                        break

                    # Myrm-Guard: Final outbound filter at the very edge of the server
                    scrubbed = _recursive_scrub(event)
                    if isinstance(scrubbed, dict):
                        yield {str(k): v for k, v in scrubbed.items()}
                    else:
                        yield {"payload": scrubbed}
        except TimeoutError:
            status = "timeout"
            raise AgentExecutionTimeout(
                f"Execution timeout ({effective_timeout:.0f}s)"
            ) from None
        except GeneratorExit:
            status = "cancelled"
            raise
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.monotonic() - started_at
            self._active_count -= 1
            user_events = self._interrupt_events.get("sandbox")
            if user_events is not None:
                user_events.pop(event_key, None)
                if not user_events:
                    del self._interrupt_events["sandbox"]
            if session_id:
                desktop = self.get_active_desktop_session(session_id)
                if desktop is not None:
                    close_fn = getattr(desktop, "close", None)
                    if close_fn is not None:
                        try:
                            await close_fn()
                        except Exception as exc:
                            logger.debug(
                                "Desktop session close error (non-fatal): %s", exc
                            )
                self._active_sessions.discard(session_id)
                self._session_info.pop(session_id, None)
                from app.services.agent.streaming_support.multiplexer import (
                    WorkspaceMultiplexer,
                )

                WorkspaceMultiplexer.get().publish_session_status(
                    session_id, "idle", agent_type
                )
            user_sem.release()
            self._global_sem.release()
            logger.info(
                "AgentGateway: %s user=%s type=%s duration=%.1fs active=%d",
                status,
                "sandbox",
                agent_type,
                duration,
                self._active_count,
            )


_gateway: AgentGateway | None = None


def get_agent_gateway() -> AgentGateway:
    """Get the singleton AgentGateway instance."""
    global _gateway  # noqa: PLW0603
    if _gateway is None:
        _gateway = AgentGateway()
    return _gateway
