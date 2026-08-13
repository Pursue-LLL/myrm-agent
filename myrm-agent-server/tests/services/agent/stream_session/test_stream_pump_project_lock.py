"""Tests for stream_pump.py project turn-lock integration.

Validates the real consumption chain of ProjectOrchestrator inside pump_to_buffer:
1. Locked project → waiting_for_turn SSE emitted before acquire, waiting_for_turn_clear after
2. Unlocked project → no waiting_for_turn SSE emitted
3. Concurrent turns on the same project serialize (second waits for first)
4. Error path still releases the lock in finally

All dependencies are injected via monkeypatch (idempotent) so concurrent pump
invocations share the same injected state — nested ``with patch`` would restore
the real stream function when one pump exits, breaking the other waiting on lock.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.agent.stream_session.stream_pump import pump_to_buffer
from app.services.project.orchestrator import ProjectOrchestrator


def _make_session(
    *,
    project_id: str | None,
    message_id: str = "test-msg-456",
) -> MagicMock:
    session = MagicMock()
    session.is_long_running_task = False
    session.cancel_token.is_cancelled = False
    session.durable_registered = False
    session.had_fatal_error = False
    session.request.chat_id = "test-chat-123"
    session.params.message_id = message_id
    session.params.project_id = project_id
    session.collector = MagicMock()
    session.http_request.is_disconnected = AsyncMock(return_value=True)
    session.registry.remove = AsyncMock()
    return session


def _make_buffer() -> MagicMock:
    buf = MagicMock()
    buf.append = AsyncMock()
    buf.end_stream = AsyncMock()
    buf.subscribe = MagicMock(return_value=iter([]))
    return buf


def _appended_chunks(buf: MagicMock) -> list[str]:
    return [call.args[0] for call in buf.append.call_args_list]


def _install_mocks(monkeypatch, orch: ProjectOrchestrator, stream_factory) -> None:
    """注入 orchestrator + stream/mux/notification 依赖（全部 monkeypatch，幂等）。"""
    monkeypatch.setattr("app.services.project.orchestrator.project_orchestrator", orch)

    async def _fake_stream(_session):
        gen = stream_factory(_session)
        async for chunk in gen:
            yield chunk

    monkeypatch.setattr(
        "app.services.agent.stream_session.stream_pump.generate_cancellable_stream",
        _fake_stream,
    )

    mock_mux = MagicMock()
    mock_mux.get.return_value.publish = AsyncMock()
    monkeypatch.setattr(
        "app.services.agent.streaming_support.multiplexer.WorkspaceMultiplexer",
        mock_mux,
    )
    monkeypatch.setattr(
        "app.services.infra.system_notification.SystemNotificationService.create_notification",
        AsyncMock(),
    )


def _const_stream(chunk: str):
    """固定 chunk 的流工厂（忽略 session）。"""

    async def factory(_session):
        yield chunk

    return factory


async def _run_pump(
    session: MagicMock,
    buf: MagicMock,
    stream_factory,
    monkeypatch,
    orch: ProjectOrchestrator,
) -> None:
    _install_mocks(monkeypatch, orch, stream_factory)
    await pump_to_buffer(session, buf)


_CHUNK = 'data: {"type": "message", "data": "hello"}\n\n'


@pytest.mark.asyncio
async def test_locked_project_emits_waiting_turn_then_clear(monkeypatch):
    """Locked project → waiting_for_turn SSE, then waiting_for_turn_clear after acquire.

    Simulates a real concurrent scenario: another agent holds the lock while a new
    turn waits in pump_to_buffer, then the holder releases and the turn proceeds.
    """
    orch = ProjectOrchestrator()
    await orch.acquire("proj-1")

    session = _make_session(project_id="proj-1")
    buf = _make_buffer()

    _install_mocks(monkeypatch, orch, _const_stream(_CHUNK))

    pump_task = asyncio.create_task(pump_to_buffer(session, buf))

    # 等待 pump 运行到 acquire 挂起（已发出 waiting_for_turn）
    for _ in range(50):
        if orch._locks.get("proj-1") is not None and orch._locks["proj-1"]._waiters:
            break
        await asyncio.sleep(0.01)
    assert orch._locks["proj-1"]._waiters, "pump 应等待锁"

    chunks = "".join(_appended_chunks(buf))
    assert '"step_key":"waiting_for_turn"' in chunks
    assert '"status":"waiting"' in chunks

    # 持有者释放锁 → pump 继续并完成
    orch.release("proj-1")
    await asyncio.wait_for(pump_task, timeout=5)

    chunks = "".join(_appended_chunks(buf))
    assert '"step_key":"waiting_for_turn_clear"' in chunks
    assert orch.is_locked("proj-1") is False


@pytest.mark.asyncio
async def test_unlocked_project_no_waiting_turn(monkeypatch):
    """Unlocked project → no waiting_for_turn SSE emitted."""
    orch = ProjectOrchestrator()
    session = _make_session(project_id="proj-1")
    buf = _make_buffer()

    await _run_pump(session, buf, _const_stream(_CHUNK), monkeypatch, orch)

    chunks = "".join(_appended_chunks(buf))
    assert '"step_key":"waiting_for_turn"' not in chunks
    assert '"step_key":"waiting_for_turn_clear"' in chunks
    assert orch.is_locked("proj-1") is False


@pytest.mark.asyncio
async def test_no_project_no_lock_sse(monkeypatch):
    """No project_id → no lock-related SSE at all."""
    orch = ProjectOrchestrator()
    session = _make_session(project_id=None)
    buf = _make_buffer()

    await _run_pump(session, buf, _const_stream(_CHUNK), monkeypatch, orch)

    chunks = "".join(_appended_chunks(buf))
    assert "waiting_for_turn" not in chunks


@pytest.mark.asyncio
async def test_concurrent_turns_serialize_and_second_waits(monkeypatch):
    """Two concurrent turns on same project serialize; second emits waiting_for_turn."""
    orch = ProjectOrchestrator()
    order: list[str] = []

    def _tagged_stream(tag: str):
        async def factory(_session):
            order.append(f"{tag}-start")
            await asyncio.sleep(0.05)
            order.append(f"{tag}-end")
            yield 'data: {"type": "message", "data": "done"}\n\n'

        return factory

    async def _run(tag: str):
        session = _make_session(project_id="shared", message_id=f"msg-{tag}")
        buf = _make_buffer()
        await _run_pump(session, buf, _tagged_stream(tag), monkeypatch, orch)
        return "".join(_appended_chunks(buf))

    chunks_a, chunks_b = await asyncio.wait_for(
        asyncio.gather(_run("a"), _run("b")), timeout=10
    )

    # 串行：a 完整结束后 b 才开始
    assert order == ["a-start", "a-end", "b-start", "b-end"]
    assert '"step_key":"waiting_for_turn"' in chunks_b
    assert '"step_key":"waiting_for_turn"' not in chunks_a
    assert orch.is_locked("shared") is False


@pytest.mark.asyncio
async def test_error_path_releases_lock(monkeypatch):
    """Stream raises → finally still releases the project lock."""
    orch = ProjectOrchestrator()
    session = _make_session(project_id="proj-1")
    buf = _make_buffer()

    async def factory(_session):
        yield 'data: {"type": "message", "data": "partial"}\n\n'
        raise RuntimeError("boom")

    await _run_pump(session, buf, factory, monkeypatch, orch)

    assert orch.is_locked("proj-1") is False
    assert len(orch._locks) == 0


@pytest.mark.asyncio
async def test_cancel_while_waiting_aborts_acquire_without_releasing_holder(
    monkeypatch,
):
    """Cancel while queued on a held lock aborts promptly and must not release the holder.

    Regression guard: pump's finally used to call release(project_id) unconditionally,
    which would steal the project lock from the agent that actually owns it and let
    a third agent run concurrently on the same workspace.
    """
    orch = ProjectOrchestrator()
    await orch.acquire("proj-1")  # 另一 agent 持有锁

    class _FakeToken:
        is_cancelled = False

    token = _FakeToken()
    session = _make_session(project_id="proj-1")
    session.cancel_token = token
    buf = _make_buffer()
    _install_mocks(monkeypatch, orch, _const_stream(_CHUNK))

    pump_task = asyncio.create_task(pump_to_buffer(session, buf))

    # 等待 pump 排队在锁上（waiting SSE 已发出）
    for _ in range(100):
        lock = orch._locks.get("proj-1")
        if lock is not None and lock._waiters:
            break
        await asyncio.sleep(0.01)
    assert orch._locks["proj-1"]._waiters, "pump 应排队等待锁"

    chunks = "".join(_appended_chunks(buf))
    assert '"step_key":"waiting_for_turn"' in chunks
    assert '"step_key":"waiting_for_turn_clear"' not in chunks

    # 用户取消 → pump 应在 ~1s 内退出（acquire 分片轮询检测 token）
    token.is_cancelled = True
    await asyncio.wait_for(pump_task, timeout=3)

    # 持有者（另一 agent）的锁必须仍然持有，未被误释放
    assert orch.is_locked("proj-1") is True
    # buffer 清理已执行（finally 走到了）
    buf.end_stream.assert_awaited()

    # 持有者正常释放后，锁彻底空闲
    orch.release("proj-1")
    assert orch.is_locked("proj-1") is False
    assert len(orch._locks) == 0


@pytest.mark.asyncio
async def test_cancel_path_releases_lock(monkeypatch):
    """Task cancellation → finally still releases the project lock.

    Real scenario: the user cancels/stops their request while another agent
    holds the project lock. pump_to_buffer swallows CancelledError then runs
    its finally cleanup, so the lock must never leak.
    """
    orch = ProjectOrchestrator()
    session = _make_session(project_id="proj-1")
    buf = _make_buffer()

    async def factory(_session):
        yield 'data: {"type": "message", "data": "partial"}\n\n'
        await asyncio.sleep(30)

    _install_mocks(monkeypatch, orch, factory)
    pump_task = asyncio.create_task(pump_to_buffer(session, buf))
    await asyncio.sleep(0.05)
    assert orch.is_locked("proj-1") is True

    pump_task.cancel()
    # CancelledError is swallowed by pump_to_buffer, then finally releases lock.
    await asyncio.wait_for(pump_task, timeout=5)

    assert orch.is_locked("proj-1") is False
    assert len(orch._locks) == 0


@pytest.mark.asyncio
async def test_cancel_while_waiting_releases_reserved_gateway_session(monkeypatch):
    """Cancel while queued on a held lock must release the pre-reserved gateway session.

    Regression guard for the permanent-busy bug: try_reserve adds the chat to
    AgentGateway._active_sessions before the turn reaches execute_stream. When the
    turn is cancelled while queued on the project lock, execute_stream never takes
    over — without the pump cleanup the reservation leaked and the chat stayed
    busy forever for all subsequent turns (user sees AgentBusyError 409 even long
    after the lock was released).
    """
    from app.services.agent.gateway import get_agent_gateway

    orch = ProjectOrchestrator()
    await orch.acquire("proj-1")  # 另一 agent 持有锁

    class _FakeToken:
        is_cancelled = False

    token = _FakeToken()
    session = _make_session(project_id="proj-1")
    session.cancel_token = token
    buf = _make_buffer()
    _install_mocks(monkeypatch, orch, _const_stream(_CHUNK))

    gateway = get_agent_gateway()
    gateway.reserve_session("test-chat-123", active_message_id="test-msg-456")
    assert gateway.is_session_active("test-chat-123") is True

    try:
        pump_task = asyncio.create_task(pump_to_buffer(session, buf))

        # 等待 pump 排队在锁上（waiting SSE 已发出）
        for _ in range(100):
            lock = orch._locks.get("proj-1")
            if lock is not None and lock._waiters:
                break
            await asyncio.sleep(0.01)
        assert orch._locks["proj-1"]._waiters, "pump 应排队等待锁"

        # 用户取消 → pump 退出，reserved gateway session 必须被释放
        token.is_cancelled = True
        await asyncio.wait_for(pump_task, timeout=3)

        assert (
            gateway.is_session_active("test-chat-123") is False
        ), "reserved gateway session leaked — the chat would stay busy forever"
        # 持有者（另一 agent）的项目锁必须仍然持有
        assert orch.is_locked("proj-1") is True
    finally:
        gateway.release_session("test-chat-123")
        orch.release("proj-1")
