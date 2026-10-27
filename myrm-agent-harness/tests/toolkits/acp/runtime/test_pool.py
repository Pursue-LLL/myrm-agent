"""Tests for the runtime pool: registration, turns, cancellation, concurrency and backend creation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.acp.core.event_bus import EventBus
from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import (
    BackendCapabilities,
    BackendInfo,
    RuntimeConfig,
    RuntimeEventType,
    create_event,
)

_POOL_FACTORY = "myrm_agent_harness.toolkits.acp.runtime.pool._create_runtime"


class TestRuntimePool:
    class _DummyRuntimeBackend:
        def __init__(self, name: str = "test-backend") -> None:
            self._name = name
            self.closed = False

        @property
        def name(self) -> str:
            return self._name

        @property
        def capabilities(self):
            return BackendCapabilities()

        @property
        def is_alive(self) -> bool:
            return not self.closed

        async def run_turn(self, prompt: str, session_id: str, *, mcp_servers=None, images=None):
            yield create_event(RuntimeEventType.STATUS_UPDATE, session_id, status="starting")
            yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content=prompt)
            yield create_event(RuntimeEventType.DONE, session_id, stop_reason="end_turn")

        async def cancel(self, session_id: str) -> None:
            return None

        async def resume(self, session_id: str) -> bool:
            return False

        async def get_info(self):
            return BackendInfo(name=self._name)

        async def close(self) -> None:
            self.closed = True

    def test_available_backends(self) -> None:
        pool = RuntimePool()
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))
        pool.register("codex", RuntimeConfig(backend_type="cli", command="codex"))
        assert sorted(pool.available_backends) == ["claude", "codex"]

    def test_get_known_backend(self) -> None:
        pool = RuntimePool()
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))
        backend = pool.get("claude")
        assert backend.name == "claude"

    def test_get_unknown_backend_raises(self) -> None:
        pool = RuntimePool()
        with pytest.raises(KeyError, match="Unknown backend"):
            pool.get("nonexistent")

    def test_get_returns_same_instance(self) -> None:
        pool = RuntimePool()
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))
        b1 = pool.get("claude")
        b2 = pool.get("claude")
        assert b1 is b2

    @pytest.mark.asyncio
    async def test_prompt_persistent_mode_keeps_backend(self) -> None:
        pool = RuntimePool()
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))
        backend = self._DummyRuntimeBackend("claude")

        with patch.object(pool, "get", return_value=backend):
            result = await pool.prompt("claude", "task", mode="persistent")

        assert result == "task"
        assert not backend.closed

    @pytest.mark.asyncio
    async def test_prompt_oneshot_closes_its_own_backend(self) -> None:
        pool = RuntimePool()
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))
        backend = self._DummyRuntimeBackend("claude")

        with patch(_POOL_FACTORY, return_value=backend):
            result = await pool.prompt("claude", "task", mode="oneshot")

        assert result == "task"
        assert backend.closed

    @pytest.mark.asyncio
    async def test_prompt_invalid_mode_raises(self) -> None:
        pool = RuntimePool()
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))

        with pytest.raises(ValueError, match="Invalid mode"):
            await pool.prompt("claude", "task", mode="invalid")

    @pytest.mark.asyncio
    async def test_run_turn_oneshot_closes_its_own_backend(self) -> None:
        pool = RuntimePool()
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))
        backend = self._DummyRuntimeBackend("claude")

        with patch(_POOL_FACTORY, return_value=backend):
            events = [e async for e in pool.run_turn("claude", "task", session_id="s-1", mode="oneshot")]

        assert len(events) == 3
        assert backend.closed
        assert pool._oneshot_backends == {}

    @pytest.mark.asyncio
    async def test_run_turn_invalid_mode_raises(self) -> None:
        pool = RuntimePool()
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))
        with pytest.raises(ValueError, match="Invalid mode"):
            [e async for e in pool.run_turn("claude", "task", "s-1", mode="bad")]

    @pytest.mark.asyncio
    async def test_event_bus_emits_events(self) -> None:
        bus = EventBus()
        recorded = []
        bus.subscribe(callback=lambda e: recorded.append(e))

        pool = RuntimePool(event_bus=bus)
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))
        backend = self._DummyRuntimeBackend("claude")

        with patch.object(pool, "get", return_value=backend):
            events = [e async for e in pool.run_turn("claude", "task", "s-1")]

        assert recorded == events


class TestRuntimePoolCloseAll:
    @pytest.mark.asyncio
    async def test_close_all_handles_errors(self) -> None:
        pool = RuntimePool()
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))
        backend = MagicMock()
        backend.close = AsyncMock(side_effect=RuntimeError("close failed"))
        pool._backends["claude"] = backend
        await pool.close_all()
        assert pool._backends == {}

    @pytest.mark.asyncio
    async def test_close_all_empty(self) -> None:
        pool = RuntimePool()
        await pool.close_all()


class TestRuntimePoolConcurrency:
    """Tests for RuntimePool semaphore-based concurrency control."""

    class _SlowBackend:
        def __init__(self, name: str, delay: float = 0.05) -> None:
            self._name = name
            self._delay = delay
            self.concurrent_count = 0
            self.max_concurrent = 0
            self.closed = False

        @property
        def name(self) -> str:
            return self._name

        @property
        def capabilities(self):
            return BackendCapabilities()

        @property
        def is_alive(self) -> bool:
            return True

        async def run_turn(self, prompt: str, session_id: str, *, mcp_servers=None, images=None):
            self.concurrent_count += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent_count)
            await asyncio.sleep(self._delay)
            self.concurrent_count -= 1
            yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content="ok")
            yield create_event(RuntimeEventType.DONE, session_id, stop_reason="end_turn")

        async def cancel(self, session_id: str) -> None:
            pass

        async def resume(self, session_id: str) -> bool:
            return False

        async def get_info(self):
            return BackendInfo(name=self._name)

        async def close(self) -> None:
            self.closed = True

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self) -> None:
        pool = RuntimePool(max_concurrent=2)
        pool.register("a", RuntimeConfig(backend_type="acp", command="a"))
        backend = self._SlowBackend("a", delay=0.05)

        with patch.object(pool, "get", return_value=backend):
            tasks = [asyncio.create_task(pool.prompt("a", f"task-{i}")) for i in range(4)]
            await asyncio.gather(*tasks)

        assert backend.max_concurrent <= 2


class TestRuntimePoolCancel:
    @pytest.mark.asyncio
    async def test_cancel_calls_backend_cancel(self) -> None:
        pool = RuntimePool()
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))
        mock_backend = MagicMock()
        mock_backend.cancel = AsyncMock()
        pool._backends["claude"] = mock_backend
        await pool.cancel("claude", "sess-1")
        mock_backend.cancel.assert_awaited_once_with("sess-1")

    @pytest.mark.asyncio
    async def test_cancel_noop_for_uninstantiated(self) -> None:
        pool = RuntimePool()
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))
        await pool.cancel("claude", "sess-1")

    @pytest.mark.asyncio
    async def test_cancel_noop_for_unknown(self) -> None:
        pool = RuntimePool()
        await pool.cancel("nonexistent", "sess-1")


class TestRuntimePoolGetConfig:
    def test_returns_config(self) -> None:
        pool = RuntimePool()
        cfg = RuntimeConfig(backend_type="cli", command="claude", max_turns=42, description="test agent")
        pool.register("claude", cfg)
        assert pool.get_config("claude") is cfg
        assert pool.get_config("claude").max_turns == 42
        assert pool.get_config("claude").description == "test agent"

    def test_returns_none_for_unknown(self) -> None:
        pool = RuntimePool()
        assert pool.get_config("nonexistent") is None


class TestRuntimePoolFactory:
    """Tests for _create_runtime factory function and backend_type dispatching."""

    def test_create_acp_runtime(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime.pool import _create_runtime

        cfg = RuntimeConfig(backend_type="acp", command="claude")
        rt = _create_runtime("test", cfg)
        assert rt.name == "test"
        assert rt.capabilities.supports_resume is True

    def test_create_cli_runtime(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime.pool import _create_runtime

        cfg = RuntimeConfig(backend_type="cli", command="claude")
        rt = _create_runtime("test", cfg)
        assert rt.name == "test"
        assert rt.capabilities.supports_resume is True

    def test_create_cli_runtime_no_resume(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime.pool import _create_runtime

        cfg = RuntimeConfig(backend_type="cli", command="gemini")
        rt = _create_runtime("test", cfg)
        assert rt.name == "test"
        assert rt.capabilities.supports_resume is False

    def test_unknown_backend_type_raises(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime.pool import _create_runtime

        cfg = RuntimeConfig(backend_type="acp", command="test")  # type: ignore[arg-type]
        object.__setattr__(cfg, "backend_type", "unknown_type")
        with pytest.raises(ValueError, match="Unknown backend_type"):
            _create_runtime("test", cfg)


class TestRuntimePoolRunTurnWithoutBus:
    """Tests for RuntimePool run_turn without event bus."""

    @pytest.mark.asyncio
    async def test_run_turn_no_bus_still_yields_events(self) -> None:
        pool = RuntimePool()
        pool.register("test", RuntimeConfig(backend_type="cli", command="echo"))

        class _SimpleBackend:
            @property
            def name(self) -> str:
                return "test"

            @property
            def capabilities(self):
                return BackendCapabilities()

            @property
            def is_alive(self) -> bool:
                return True

            async def run_turn(self, prompt, session_id, *, mcp_servers=None, images=None):
                yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content="hi")
                yield create_event(RuntimeEventType.DONE, session_id, stop_reason="end_turn")

            async def cancel(self, session_id):
                pass

            async def resume(self, session_id):
                return False

            async def get_info(self) -> BackendInfo:
                return BackendInfo(name="test")

            async def close(self) -> None:
                pass

        pool._backends["test"] = _SimpleBackend()
        events = [e async for e in pool.run_turn("test", "task", "s-1")]
        assert len(events) == 2
