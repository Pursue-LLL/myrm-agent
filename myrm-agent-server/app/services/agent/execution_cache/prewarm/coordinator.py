"""Chat turn prewarm — coalesced agent cache warm + memory brief snapshot.

[INPUT]
- app.ai_agents.general_agent.agent::GeneralAgent (POS: 通用 Agent 核心实现)
- execution_cache.registry::ChatAgentExecutionCache (POS: 缓存注册表)
- stream_session.memory_brief::build_memory_brief_snapshot (POS: 流式会话的记忆预检构建器)

[OUTPUT]
- TurnPrewarmCoordinator: ensure_warming, join_for_turn, coalesced_acquire

[POS]
execution_cache prewarm 协调器。空 chat 聚焦与发送路径共享同一个 in-flight 预热任务。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from app.ai_agents.agents import AgentFactory
from app.services.agent.execution_cache.fingerprint import (
    build_execution_scope_key,
    compute_execution_fingerprint,
)
from app.services.agent.execution_cache.prewarm.brief_cache import BriefCache
from app.services.agent.execution_cache.prewarm.types import TurnPrewarmJoinResult
from app.services.agent.execution_cache.registry import get_execution_cache
from app.services.agent.execution_cache.types import ExecutionMode
from app.services.agent.execution_cache.unit_ops import capture_built_unit
from app.services.agent.runtime_context import resolve_stream_execution_mode

if TYPE_CHECKING:
    from app.ai_agents import GeneralAgentParams
    from app.ai_agents.general_agent.agent import GeneralAgent
    from app.services.agent.execution_cache.registry import BuildUnitFn
    from app.services.agent.execution_cache.types import BuiltExecutionUnit

logger = logging.getLogger(__name__)

_BRIEF_BACKGROUND_TIMEOUT_SECONDS = 2.5
_DEFAULT_JOIN_TIMEOUT_SECONDS = 0.3
_AGENT_READY_TTL_SECONDS = 600.0
_AGENT_READY_MAX_ENTRIES = 1024


class TurnPrewarmCoordinator:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._inflight_acquire: dict[str, asyncio.Task[BuiltExecutionUnit]] = {}
        self._inflight_brief: dict[str, asyncio.Task[None]] = {}
        self._brief_cache = BriefCache()
        self._agent_ready_at: dict[str, float] = {}

    def _prune_agent_ready_at(self) -> None:
        self._brief_cache.prune_expired()
        now = time.monotonic()
        stale_keys = [key for key, ready_at in self._agent_ready_at.items() if now - ready_at > _AGENT_READY_TTL_SECONDS]
        for key in stale_keys:
            self._agent_ready_at.pop(key, None)
        if len(self._agent_ready_at) > _AGENT_READY_MAX_ENTRIES:
            excess = len(self._agent_ready_at) - _AGENT_READY_MAX_ENTRIES
            oldest = sorted(self._agent_ready_at, key=lambda key: self._agent_ready_at[key])[:excess]
            for key in oldest:
                self._agent_ready_at.pop(key, None)

    @staticmethod
    def _task_key(scope_key: str, fingerprint: str) -> str:
        return f"{scope_key}:{fingerprint}"

    def _should_warm_agent(self, action_mode: str) -> bool:
        if resolve_stream_execution_mode() == ExecutionMode.EPHEMERAL:
            return False
        return action_mode != "fast"

    def has_brief_cached(self, scope_key: str, fingerprint: str) -> bool:
        return self._brief_cache.get(scope_key, fingerprint) is not None

    async def ensure_warming(
        self,
        params: GeneralAgentParams,
        *,
        action_mode: str = "agent",
    ) -> None:
        self._prune_agent_ready_at()
        if params.incognito_mode or not params.chat_id or not params.chat_id.strip():
            return

        scope_key = build_execution_scope_key(params.chat_id, params.agent_id)
        if scope_key is None:
            return

        wrapper = AgentFactory.create_general_agent(params)
        fingerprint = compute_execution_fingerprint(wrapper)
        task_key = self._task_key(scope_key, fingerprint)

        if self._should_warm_agent(action_mode):
            await self._schedule_agent_warm(scope_key, fingerprint, wrapper, params, task_key)

        if params.enable_memory and params.embedding_config is not None:
            await self._schedule_brief_warm(scope_key, fingerprint, params, task_key)

    async def cancel_scope(self, chat_id: str, agent_id: str | None) -> None:
        scope_key = build_execution_scope_key(chat_id, agent_id)
        if scope_key is None:
            return
        prefix = f"{scope_key}:"
        async with self._lock:
            for key, task in list(self._inflight_acquire.items()):
                if key.startswith(prefix) and not task.done():
                    task.cancel()
            for key, task in list(self._inflight_brief.items()):
                if key.startswith(prefix) and not task.done():
                    task.cancel()
            self._inflight_acquire = {k: v for k, v in self._inflight_acquire.items() if not k.startswith(prefix)}
            self._inflight_brief = {k: v for k, v in self._inflight_brief.items() if not k.startswith(prefix)}
        self._brief_cache.invalidate_scope(scope_key)
        self._agent_ready_at = {key: ready_at for key, ready_at in self._agent_ready_at.items() if not key.startswith(prefix)}

    async def join_for_turn(
        self,
        params: GeneralAgentParams,
        *,
        action_mode: str = "agent",
        join_timeout: float = _DEFAULT_JOIN_TIMEOUT_SECONDS,
    ) -> TurnPrewarmJoinResult:
        self._prune_agent_ready_at()
        if not params.chat_id or not params.chat_id.strip():
            return TurnPrewarmJoinResult(
                preview=None,
                snapshot=None,
                brief_status={"state": "skipped", "reason": "no_chat_id"},
                prewarm_hit=False,
                prewarm_ms=None,
                still_warming=False,
            )

        scope_key = build_execution_scope_key(params.chat_id, params.agent_id)
        if scope_key is None:
            return TurnPrewarmJoinResult(
                preview=None,
                snapshot=None,
                brief_status={"state": "skipped", "reason": "no_scope"},
                prewarm_hit=False,
                prewarm_ms=None,
                still_warming=False,
            )

        wrapper = AgentFactory.create_general_agent(params)
        fingerprint = compute_execution_fingerprint(wrapper)
        task_key = self._task_key(scope_key, fingerprint)

        warm_agent = self._should_warm_agent(action_mode)
        warm_brief = params.enable_memory and params.embedding_config is not None

        if warm_agent:
            await self._schedule_agent_warm(scope_key, fingerprint, wrapper, params, task_key)

        if warm_brief:
            await self._schedule_brief_warm(scope_key, fingerprint, params, task_key)

        prewarm_hit = False
        prewarm_ms: int | None = None
        still_warming = False

        cache = get_execution_cache()
        if warm_agent:
            if await cache.is_warm(scope_key, fingerprint):
                prewarm_hit = True
                ready_at = self._agent_ready_at.pop(task_key, None)
                if ready_at is not None:
                    prewarm_ms = max(0, int((time.monotonic() - ready_at) * 1000))
            else:
                agent_task = self._inflight_acquire.get(task_key)
                if agent_task is not None and not agent_task.done():
                    still_warming = True
                    try:
                        await asyncio.wait_for(asyncio.shield(agent_task), timeout=join_timeout)
                        prewarm_hit = await cache.is_warm(scope_key, fingerprint)
                        still_warming = not prewarm_hit
                    except asyncio.TimeoutError:
                        still_warming = True
                    except asyncio.CancelledError:
                        still_warming = False
                    except Exception as exc:
                        logger.warning("Turn prewarm join agent task failed: %s", exc)
                        still_warming = False

        preview: dict[str, object] | None = None
        snapshot: dict[str, object] | None = None
        cached = self._brief_cache.get(scope_key, fingerprint)
        if cached is not None:
            preview = cached.preview
            snapshot = cached.snapshot
            brief_status: dict[str, object] = {"state": "ready", "source": "preflight"}
        elif warm_brief:
            brief_task = self._inflight_brief.get(task_key)
            if brief_task is not None and not brief_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(brief_task), timeout=join_timeout)
                except asyncio.TimeoutError:
                    pass
                except Exception as exc:
                    logger.warning("Turn prewarm join brief task failed: %s", exc)
                cached = self._brief_cache.get(scope_key, fingerprint)
                if cached is not None:
                    preview = cached.preview
                    snapshot = cached.snapshot
            brief_status = (
                {"state": "ready", "source": "preflight"}
                if preview is not None
                else {"state": "skipped", "reason": "brief_pending"}
            )
        else:
            brief_status = {"state": "skipped", "reason": "memory_disabled"}

        return TurnPrewarmJoinResult(
            preview=preview,
            snapshot=snapshot,
            brief_status=brief_status,
            prewarm_hit=prewarm_hit,
            prewarm_ms=prewarm_ms,
            still_warming=still_warming,
        )

    async def coalesced_acquire(
        self,
        scope_key: str,
        fingerprint: str,
        build_unit: BuildUnitFn,
    ) -> BuiltExecutionUnit:
        self._prune_agent_ready_at()
        task_key = self._task_key(scope_key, fingerprint)
        cache = get_execution_cache()
        if await cache.is_warm(scope_key, fingerprint):
            self._agent_ready_at[task_key] = time.monotonic()
            return await cache.acquire(scope_key, fingerprint, build_unit)

        async with self._lock:
            existing = self._inflight_acquire.get(task_key)
            if existing is not None and not existing.done():
                task = existing
            else:

                async def _run() -> BuiltExecutionUnit:
                    unit = await cache.acquire(scope_key, fingerprint, build_unit)
                    self._agent_ready_at[task_key] = time.monotonic()
                    return unit

                task = asyncio.create_task(_run())
                self._inflight_acquire[task_key] = task

        try:
            return await task
        finally:
            async with self._lock:
                current = self._inflight_acquire.get(task_key)
                if current is task and task.done():
                    del self._inflight_acquire[task_key]

    async def _schedule_agent_warm(
        self,
        scope_key: str,
        fingerprint: str,
        wrapper: GeneralAgent,
        params: GeneralAgentParams,
        task_key: str,
    ) -> None:
        cache = get_execution_cache()
        if await cache.is_warm(scope_key, fingerprint):
            return

        async with self._lock:
            existing = self._inflight_acquire.get(task_key)
            if existing is not None and not existing.done():
                return

        effective_chat_id = params.chat_id or "default"

        async def build_unit() -> BuiltExecutionUnit:
            from app.ai_agents.general_agent.factory import build_general_agent

            skill_agent = await build_general_agent(
                wrapper,
                effective_chat_id,
                user_id=None,
            )
            return capture_built_unit(wrapper, skill_agent)

        asyncio.create_task(self.coalesced_acquire(scope_key, fingerprint, build_unit))

    async def _schedule_brief_warm(
        self,
        scope_key: str,
        fingerprint: str,
        params: GeneralAgentParams,
        task_key: str,
    ) -> None:
        if self._brief_cache.get(scope_key, fingerprint) is not None:
            return

        async with self._lock:
            existing = self._inflight_brief.get(task_key)
            if existing is not None and not existing.done():
                return

            async def _run_brief() -> None:
                from app.services.agent.stream_session.memory_brief import (
                    build_memory_brief_snapshot,
                )

                try:
                    bundle = await asyncio.wait_for(
                        build_memory_brief_snapshot(params),
                        timeout=_BRIEF_BACKGROUND_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.info(
                        "Turn prewarm brief timed out after %.1fs",
                        _BRIEF_BACKGROUND_TIMEOUT_SECONDS,
                    )
                    return
                except Exception as exc:
                    logger.warning("Turn prewarm brief failed: %s", exc)
                    return
                if bundle is None:
                    return
                preview, snapshot = bundle
                self._brief_cache.put(scope_key, fingerprint, preview, snapshot)

            self._inflight_brief[task_key] = asyncio.create_task(_run_brief())


_coordinator: TurnPrewarmCoordinator | None = None


def get_turn_prewarm_coordinator() -> TurnPrewarmCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = TurnPrewarmCoordinator()
    return _coordinator


def _reset_turn_prewarm_coordinator_for_testing() -> None:
    """Drop process singleton so asyncio locks bind to the active test event loop."""
    global _coordinator
    _coordinator = None
