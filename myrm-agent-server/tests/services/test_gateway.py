"""Tests for AgentGateway — concurrency, interrupt, memory pressure, and session tracking."""

from __future__ import annotations

import asyncio
import weakref

import pytest
from myrm_agent_harness.runtime.memory_pressure import PressureEvent, PressureLevel

from app.services.agent.gateway import (
    ActiveSessionInfo,
    AgentBusyError,
    AgentExecutionTimeout,
    AgentGateway,
    AgentQueueTimeout,
    GatewayConfig,
)


def _cfg(**overrides: float | int) -> GatewayConfig:
    defaults: dict[str, float | int] = {
        "max_global": 10,
        "max_per_user": 3,
        "queue_timeout": 2.0,
        "execution_timeout": 5.0,
    }
    defaults.update(overrides)
    return GatewayConfig(**defaults)  # type: ignore[arg-type]


async def _dummy_stream(duration: float = 0.1, events: int = 3):
    for i in range(events):
        await asyncio.sleep(duration / events)
        yield {"step": i}


async def _collect(gw: AgentGateway, **kwargs) -> list[dict]:
    return [e async for e in gw.execute_stream(_dummy_stream(), **kwargs)]


class TestGatewayBasic:
    @pytest.mark.asyncio
    async def test_normal_execution(self) -> None:
        gw = AgentGateway(_cfg())
        events = await _collect(gw, agent_type="test", session_id="s1")
        assert len(events) == 3
        assert gw.active_count == 0

    @pytest.mark.asyncio
    async def test_session_tracking(self) -> None:
        gw = AgentGateway(_cfg())

        async def long_stream():
            await asyncio.sleep(0.5)
            yield {"done": True}

        async def run():
            async for _ in gw.execute_stream(long_stream(), agent_type="test", session_id="s1"):
                pass

        _task = asyncio.create_task(run())
        await asyncio.sleep(0.05)

        sessions = gw.get_active_sessions()
        assert len(sessions) == 1
        assert sessions[0]["chatId"] == "s1"
        assert sessions[0]["agentType"] == "test"
        assert gw.get_available_slots() == 2

        await _task
        assert len(gw.get_active_sessions()) == 0
        assert gw.get_available_slots() == 3


class TestGatewayBusy:
    @pytest.mark.asyncio
    async def test_duplicate_session_raises(self) -> None:
        gw = AgentGateway(_cfg())

        async def long_stream():
            await asyncio.sleep(1)
            yield {}

        async def run():
            async for _ in gw.execute_stream(long_stream(), agent_type="test", session_id="dup"):
                pass

        _task = asyncio.create_task(run())
        await asyncio.sleep(0.05)

        with pytest.raises(AgentBusyError):
            async for _ in gw.execute_stream(_dummy_stream(), agent_type="test", session_id="dup"):
                pass

        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, GeneratorExit):
            pass


class TestGatewayQueueTimeout:
    @pytest.mark.asyncio
    async def test_queue_timeout_cleans_session_info(self) -> None:
        gw = AgentGateway(_cfg(max_global=1, queue_timeout=0.1))

        async def blocker():
            await asyncio.sleep(2)
            yield {}

        async def run_blocker():
            async for _ in gw.execute_stream(blocker(), agent_type="test", session_id="blocker"):
                pass

        _task = asyncio.create_task(run_blocker())
        await asyncio.sleep(0.05)

        with pytest.raises(AgentQueueTimeout):
            async for _ in gw.execute_stream(_dummy_stream(), agent_type="test", session_id="waiter"):
                pass

        assert "waiter" not in gw._session_info
        assert "waiter" not in gw._active_sessions

        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, GeneratorExit):
            pass


class TestGatewayInterrupt:
    @pytest.mark.asyncio
    async def test_interrupt_single_agent(self) -> None:
        gw = AgentGateway(_cfg())
        interrupted = False

        async def slow_stream():
            nonlocal interrupted
            for i in range(100):
                await asyncio.sleep(0.01)
                yield {"i": i}
            interrupted = False

        async def run():
            nonlocal interrupted
            async for _ in gw.execute_stream(slow_stream(), agent_type="test", session_id="s1"):
                pass
            interrupted = True

        _task = asyncio.create_task(run())
        await asyncio.sleep(0.1)

        assert gw.interrupt()
        await asyncio.sleep(0.1)
        assert interrupted

    @pytest.mark.asyncio
    async def test_interrupt_multiple_concurrent_agents(self) -> None:
        gw = AgentGateway(_cfg())
        results: dict[str, bool] = {}

        async def slow_stream():
            for _ in range(100):
                await asyncio.sleep(0.01)
                yield {}

        async def run(sid: str):
            async for _ in gw.execute_stream(slow_stream(), agent_type="test", session_id=sid):
                pass
            results[sid] = True

        t1 = asyncio.create_task(run("s1"))
        t2 = asyncio.create_task(run("s2"))
        t3 = asyncio.create_task(run("s3"))
        await asyncio.sleep(0.1)

        assert len(gw._interrupt_events.get("sandbox", {})) == 3
        assert gw.interrupt()

        await asyncio.gather(t1, t2, t3, return_exceptions=True)
        assert len(results) == 3
        assert "sandbox" not in gw._interrupt_events

    @pytest.mark.asyncio
    async def test_interrupt_nonexistent_user(self) -> None:
        gw = AgentGateway(_cfg())
        assert not gw.interrupt()

    @pytest.mark.asyncio
    async def test_interrupt_session_single_agent(self) -> None:
        gw = AgentGateway(_cfg())
        interrupted = False

        async def slow_stream():
            for i in range(100):
                await asyncio.sleep(0.01)
                yield {"i": i}

        async def run() -> None:
            nonlocal interrupted
            async for _ in gw.execute_stream(slow_stream(), agent_type="test", session_id="chat-a"):
                pass
            interrupted = True

        task = asyncio.create_task(run())
        await asyncio.sleep(0.1)

        assert gw.interrupt_session("chat-a")
        await asyncio.sleep(0.1)
        assert interrupted
        await task

    @pytest.mark.asyncio
    async def test_interrupt_session_unknown_chat_returns_false(self) -> None:
        gw = AgentGateway(_cfg())
        assert not gw.interrupt_session("missing-chat")

    @pytest.mark.asyncio
    async def test_get_active_message_id_tracks_stream(self) -> None:
        gw = AgentGateway(_cfg())

        async def slow_stream():
            for i in range(100):
                await asyncio.sleep(0.01)
                yield {"i": i}

        async def run() -> None:
            async for _ in gw.execute_stream(
                slow_stream(),
                agent_type="test",
                session_id="chat-msg",
                active_message_id="msg-42",
            ):
                pass

        task = asyncio.create_task(run())
        await asyncio.sleep(0.05)

        assert gw.get_active_message_id("chat-msg") == "msg-42"
        gw.interrupt_session("chat-msg")
        await task
        assert gw.get_active_message_id("chat-msg") is None

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Gateway API changed")
    async def test_interrupt_all(self) -> None:
        gw = AgentGateway(_cfg())

        async def slow():
            for _ in range(100):
                await asyncio.sleep(0.01)
                yield {}

        async def run(uid: str, sid: str):
            async for _ in gw.execute_stream(slow(), agent_type="t", session_id=sid):
                pass

        tasks = [
            asyncio.create_task(run("u1", "s1")),
            asyncio.create_task(run("u2", "s2")),
        ]
        await asyncio.sleep(0.1)

        count = gw.interrupt_all()
        assert count == 2

        await asyncio.gather(*tasks, return_exceptions=True)
        assert gw.active_count == 0


class TestGatewayPerUserConcurrency:
    @pytest.mark.skip(reason="Per-user concurrency removed - gateway now global-only")
    @pytest.mark.asyncio
    async def test_per_user_limit_blocks_fourth_agent(self) -> None:
        gw = AgentGateway(_cfg(max_per_user=2, queue_timeout=0.2))

        async def slow():
            await asyncio.sleep(2)
            yield {}

        async def run(sid: str):
            async for _ in gw.execute_stream(slow(), agent_type="t", session_id=sid):
                pass

        t1 = asyncio.create_task(run("s1"))
        t2 = asyncio.create_task(run("s2"))
        await asyncio.sleep(0.05)

        with pytest.raises(AgentQueueTimeout):
            async for _ in gw.execute_stream(_dummy_stream(), agent_type="t", session_id="s3"):
                pass

        t1.cancel()
        t2.cancel()
        await asyncio.gather(t1, t2, return_exceptions=True)

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Per-user features removed")
    async def test_different_users_independent(self) -> None:
        gw = AgentGateway(_cfg(max_per_user=1))

        async def slow():
            await asyncio.sleep(0.5)
            yield {"ok": True}

        async def run(uid: str, sid: str):
            async for _ in gw.execute_stream(slow(), agent_type="t", session_id=sid):
                pass

        tasks = [
            asyncio.create_task(run("u1", "s1")),
            asyncio.create_task(run("u2", "s2")),
            asyncio.create_task(run("u3", "s3")),
        ]
        await asyncio.sleep(0.05)
        assert gw.active_count == 3

        await asyncio.gather(*tasks)
        assert gw.active_count == 0


class TestGatewayAnonymousExecution:
    @pytest.mark.asyncio
    async def test_session_id_none(self) -> None:
        gw = AgentGateway(_cfg())
        events = await _collect(gw, agent_type="test")
        assert len(events) == 3
        assert gw.active_count == 0
        assert len(gw._active_sessions) == 0

    @pytest.mark.asyncio
    async def test_anonymous_interrupt(self) -> None:
        gw = AgentGateway(_cfg())

        async def slow():
            for _ in range(100):
                await asyncio.sleep(0.01)
                yield {}

        async def run():
            async for _ in gw.execute_stream(slow(), agent_type="t"):
                pass

        _task = asyncio.create_task(run())
        await asyncio.sleep(0.05)

        assert gw.interrupt()
        await asyncio.sleep(0.1)
        assert gw.active_count == 0


class TestGatewayErrorCleanup:
    @pytest.mark.asyncio
    async def test_stream_exception_cleans_up(self) -> None:
        gw = AgentGateway(_cfg())

        async def failing_stream():
            yield {"step": 1}
            raise RuntimeError("Agent crashed")

        with pytest.raises(RuntimeError, match="Agent crashed"):
            async for _ in gw.execute_stream(failing_stream(), agent_type="t", session_id="s1"):
                pass

        assert gw.active_count == 0
        assert "s1" not in gw._active_sessions
        assert "s1" not in gw._session_info
        assert "u1" not in gw._interrupt_events


class TestGatewayExecutionTimeout:
    @pytest.mark.asyncio
    async def test_execution_timeout(self) -> None:
        gw = AgentGateway(_cfg(execution_timeout=0.1))

        async def infinite():
            while True:
                await asyncio.sleep(0.01)
                yield {}

        with pytest.raises(AgentExecutionTimeout):
            async for _ in gw.execute_stream(infinite(), agent_type="test"):
                pass

        assert gw.active_count == 0

    @pytest.mark.asyncio
    async def test_execution_timeout_cleans_session(self) -> None:
        gw = AgentGateway(_cfg(execution_timeout=0.1))

        async def infinite():
            while True:
                await asyncio.sleep(0.01)
                yield {}

        with pytest.raises(AgentExecutionTimeout):
            async for _ in gw.execute_stream(infinite(), agent_type="t", session_id="timeout_sid"):
                pass

        assert "timeout_sid" not in gw._active_sessions
        assert "timeout_sid" not in gw._session_info
        assert "u1" not in gw._interrupt_events

    @pytest.mark.asyncio
    async def test_goal_active_extends_timeout(self) -> None:
        """goal_active=True should use 3600s timeout instead of execution_timeout."""
        gw = AgentGateway(_cfg(execution_timeout=0.1))

        async def slow_stream():
            for i in range(3):
                await asyncio.sleep(0.05)
                yield {"step": i}

        # Without goal_active: 0.1s timeout would kill a 0.15s stream
        # With goal_active: 3600s timeout allows it to complete
        events = [e async for e in gw.execute_stream(slow_stream(), agent_type="test", session_id="goal_s1", goal_active=True)]
        assert len(events) == 3
        assert gw.active_count == 0

    @pytest.mark.asyncio
    async def test_fission_active_extends_timeout(self) -> None:
        """fission_active=True should complete a stream slower than the base timeout."""
        gw = AgentGateway(_cfg(execution_timeout=0.5))

        async def slow_stream():
            # 0.6s 总耗时：必 > 0.5s 基础超时（无 fission 会超时），
            # 远 < 1.0s（2x）可完成，上限留 0.4s 余量抵御高负载抖动。
            for i in range(3):
                await asyncio.sleep(0.2)
                yield {"step": i}

        events = [
            e
            async for e in gw.execute_stream(
                slow_stream(),
                agent_type="test",
                session_id="fission_s1",
                fission_active=True,
            )
        ]
        assert len(events) == 3
        assert gw.active_count == 0

    def test_resolve_effective_timeout_tiers(self) -> None:
        """确定性验证超时分层：goal > fission > default（不依赖 wall-clock）。"""
        gw = AgentGateway(_cfg(execution_timeout=5.0))
        assert gw._resolve_effective_timeout(goal_active=False, fission_active=False) == 5.0
        assert gw._resolve_effective_timeout(goal_active=False, fission_active=True) == 10.0
        assert gw._resolve_effective_timeout(goal_active=True, fission_active=False) == 3600.0
        # goal 优先级高于 fission
        assert gw._resolve_effective_timeout(goal_active=True, fission_active=True) == 3600.0


class TestGatewayMultipleActiveSessions:
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="get_user_active_sessions API removed")
    async def test_get_user_active_sessions_multiple(self) -> None:
        gw = AgentGateway(_cfg())

        async def slow():
            await asyncio.sleep(1)
            yield {}

        async def run(sid: str, atype: str):
            async for _ in gw.execute_stream(slow(), agent_type=atype, session_id=sid):
                pass

        tasks = [
            asyncio.create_task(run("s1", "general")),
            asyncio.create_task(run("s2", "search")),
            asyncio.create_task(run("s3", "browser")),
        ]
        await asyncio.sleep(0.05)

        sessions = gw.get_active_sessions()
        assert len(sessions) == 3
        types = {s["agentType"] for s in sessions}
        assert types == {"general", "search", "browser"}

        assert gw.get_available_slots() == 0
        assert gw.get_available_slots() == 3

        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _pressure_event(
    level: PressureLevel,
    previous: PressureLevel = PressureLevel.NORMAL,
    mem_pct: float = 92.0,
) -> PressureEvent:
    import time

    return PressureEvent(
        level=level,
        previous_level=previous,
        memory_percent=mem_pct,
        timestamp=time.monotonic(),
    )


class TestGatewayMemoryPressure:
    """Tests for memory pressure circuit breaker behavior."""

    @pytest.mark.asyncio
    async def test_critical_pressure_blocks_new_execution(self) -> None:
        """CRITICAL pressure should block new agents until resolved."""
        gw = AgentGateway(_cfg(queue_timeout=0.5))

        await gw.on_pressure_change(_pressure_event(PressureLevel.CRITICAL))
        assert not gw._pressure_resolved.is_set()

        with pytest.raises(AgentQueueTimeout, match="Memory pressure"):
            async for _ in gw.execute_stream(_dummy_stream(), agent_type="test", session_id="blocked"):
                pass

        assert "blocked" not in gw._active_sessions

    @pytest.mark.asyncio
    async def test_pressure_resolve_unblocks_execution(self) -> None:
        """De-escalation to WARNING should unblock queued agents."""
        gw = AgentGateway(_cfg(queue_timeout=2.0))

        await gw.on_pressure_change(_pressure_event(PressureLevel.CRITICAL))

        async def delayed_resolve() -> None:
            await asyncio.sleep(0.2)
            await gw.on_pressure_change(_pressure_event(PressureLevel.WARNING, PressureLevel.CRITICAL, 82.0))

        asyncio.create_task(delayed_resolve())

        events = [e async for e in gw.execute_stream(_dummy_stream(), agent_type="test", session_id="unblocked")]
        assert len(events) == 3
        assert gw.active_count == 0

    @pytest.mark.asyncio
    async def test_warning_pressure_does_not_block(self) -> None:
        """WARNING pressure should NOT block new agents."""
        gw = AgentGateway(_cfg())

        await gw.on_pressure_change(_pressure_event(PressureLevel.WARNING))
        assert gw._pressure_resolved.is_set()

        events = await _collect(gw, agent_type="test", session_id="ok")
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_emergency_pressure_blocks(self) -> None:
        """EMERGENCY pressure should also block (>= CRITICAL)."""
        gw = AgentGateway(_cfg(queue_timeout=0.3))

        await gw.on_pressure_change(_pressure_event(PressureLevel.EMERGENCY, PressureLevel.CRITICAL, 96.0))
        assert not gw._pressure_resolved.is_set()

        with pytest.raises(AgentQueueTimeout, match="Memory pressure"):
            async for _ in gw.execute_stream(_dummy_stream(), agent_type="test"):
                pass

    @pytest.mark.asyncio
    async def test_running_agents_not_interrupted(self) -> None:
        """Already-running agents should NOT be interrupted by pressure escalation."""
        gw = AgentGateway(_cfg())
        events_collected: list[dict] = []

        async def slow_stream():
            for i in range(5):
                await asyncio.sleep(0.05)
                yield {"i": i}

        async def run() -> None:
            async for e in gw.execute_stream(slow_stream(), agent_type="test", session_id="running"):
                events_collected.append(e)

        task = asyncio.create_task(run())
        await asyncio.sleep(0.05)

        await gw.on_pressure_change(_pressure_event(PressureLevel.CRITICAL))

        await task
        assert len(events_collected) == 5
        assert gw.active_count == 0


class TestGetActiveBrowserSession:
    """Tests for AgentGateway.get_active_browser_session."""

    def test_no_active_sessions_returns_none(self) -> None:
        gw = AgentGateway(_cfg())
        assert gw.get_active_browser_session() is None

    def test_active_agent_without_browser_returns_none(self) -> None:
        gw = AgentGateway(_cfg())

        class FakeAgent:
            pass

        agent = FakeAgent()
        info = ActiveSessionInfo(chat_id="s1", agent_type="test")
        info.agent = weakref.ref(agent)
        gw._session_info["s1"] = info

        assert gw.get_active_browser_session() is None

    def test_active_agent_with_browser_returns_session(self) -> None:
        gw = AgentGateway(_cfg())

        class FakeBrowserSession:
            pass

        class FakeAgent:
            def __init__(self) -> None:
                self._browser_session = FakeBrowserSession()

        agent = FakeAgent()
        info = ActiveSessionInfo(chat_id="s1", agent_type="test")
        info.agent = weakref.ref(agent)
        gw._session_info["s1"] = info

        result = gw.get_active_browser_session()
        assert result is agent._browser_session

    def test_dead_weakref_returns_none(self) -> None:
        gw = AgentGateway(_cfg())

        class FakeAgent:
            def __init__(self) -> None:
                self._browser_session = object()

        agent = FakeAgent()
        info = ActiveSessionInfo(chat_id="s1", agent_type="test")
        info.agent = weakref.ref(agent)
        gw._session_info["s1"] = info

        del agent

        assert gw.get_active_browser_session() is None

    def test_multiple_agents_returns_first_with_browser(self) -> None:
        gw = AgentGateway(_cfg())

        class FakeAgent:
            pass

        class FakeAgentWithBrowser:
            def __init__(self) -> None:
                self._browser_session = "mock_browser"

        agent_no_browser = FakeAgent()
        agent_with_browser = FakeAgentWithBrowser()

        info1 = ActiveSessionInfo(chat_id="s1", agent_type="test")
        info1.agent = weakref.ref(agent_no_browser)
        gw._session_info["s1"] = info1

        info2 = ActiveSessionInfo(chat_id="s2", agent_type="test")
        info2.agent = weakref.ref(agent_with_browser)
        gw._session_info["s2"] = info2

        result = gw.get_active_browser_session()
        assert result == "mock_browser"

    def test_agent_weakref_is_none(self) -> None:
        """Session info exists but agent weakref was never set."""
        gw = AgentGateway(_cfg())
        info = ActiveSessionInfo(chat_id="s1", agent_type="test")
        gw._session_info["s1"] = info

        assert gw.get_active_browser_session() is None

    def test_browser_session_is_none_attribute(self) -> None:
        """Agent has _browser_session = None (browser not yet started)."""
        gw = AgentGateway(_cfg())

        class FakeAgent:
            _browser_session = None

        agent = FakeAgent()
        info = ActiveSessionInfo(chat_id="s1", agent_type="test")
        info.agent = weakref.ref(agent)
        gw._session_info["s1"] = info

        assert gw.get_active_browser_session() is None


class TestGetActiveDesktopSession:
    """Tests for AgentGateway.get_active_desktop_session."""

    def test_no_active_sessions_returns_none(self) -> None:
        gw = AgentGateway(_cfg())
        assert gw.get_active_desktop_session() is None

    def test_active_agent_with_desktop_returns_session(self) -> None:
        gw = AgentGateway(_cfg())

        class FakeDesktopSession:
            pass

        class FakeAgent:
            def __init__(self) -> None:
                self._desktop_session = FakeDesktopSession()

        agent = FakeAgent()
        info = ActiveSessionInfo(chat_id="s1", agent_type="test")
        info.agent = weakref.ref(agent)
        gw._session_info["s1"] = info

        result = gw.get_active_desktop_session()
        assert result is agent._desktop_session
