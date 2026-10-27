"""Guard rails of the MCP session actor that the happy-path suites do not reach.

- stdio launch gates: a workspace-trust denial or an OSV malware advisory ends the actor for good, before any process
  is spawned and without start retries;
- ``start()`` gives up on an owner task that never reports readiness instead of hanging its caller;
- a crashing dynamic refresh keeps the previous tool map;
- the serve loop skips cancelled resource reads and never loses a call that arrives while a keepalive probe fails;
- a caller that gives up cancels its in-flight call and the loop serves the next one, while a cancelled loop still
  fails the call it was running;
- notification handler errors stay inside the handler; a missing SDK is reported for resource reads.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import ToolListChangedNotification

from myrm_agent_harness.toolkits.mcp import session_actor as sa
from myrm_agent_harness.toolkits.mcp.config import sanitize_mcp_name_component
from myrm_agent_harness.toolkits.mcp.session_actor import MCPSessionActor
from myrm_agent_harness.toolkits.mcp.session_actor_tools import (
    check_actor_stdio_security_gates,
    resolve_actor_tool,
    serve_actor_queue,
)
from myrm_agent_harness.toolkits.mcp.session_actor_types import (
    _SHUTDOWN,
    _ResourceRead,
    _ServeOutcome,
    _ToolCall,
    build_notification_handler,
    read_mcp_resource,
)
from tests.support.mcp_launch_gates import PATCH_OSV_CHECK, PATCH_TRUST_GATE, RecordingTrustGate

_NPX_CONN: dict[str, object] = {"transport": "stdio", "command": "npx", "args": ["-y", "left-pad"]}


class TestStdioLaunchGates:
    @pytest.mark.asyncio
    async def test_malware_advisory_stops_the_start_without_retries_or_a_spawn(self) -> None:
        osv = AsyncMock(return_value="MAL-2025-0001")
        actor = MCPSessionActor("evil", {"transport": "stdio", "command": "npx", "args": ["-y", "flatmap-stream"]})

        with (
            patch(PATCH_OSV_CHECK, osv),
            patch(PATCH_TRUST_GATE, return_value=None),
            patch.object(MCPSessionActor, "_build_client_target") as build_target,
            pytest.raises(RuntimeError, match=r"failed to start.*Malware advisory detected: MAL-2025-0001"),
        ):
            await actor.start()

        osv.assert_awaited_once_with("npx", ["-y", "flatmap-stream"], use_cache=True)
        build_target.assert_not_called()  # a security verdict is final: nothing is launched, nothing is retried
        assert actor._security_terminated is True
        assert actor.is_healthy() is False

    @pytest.mark.asyncio
    async def test_clean_package_passes_the_gate(self) -> None:
        osv = AsyncMock(return_value=None)
        actor = MCPSessionActor("fine", _NPX_CONN)

        with patch(PATCH_OSV_CHECK, osv), patch(PATCH_TRUST_GATE, return_value=None):
            await check_actor_stdio_security_gates(actor, _NPX_CONN)

        osv.assert_awaited_once_with("npx", ["-y", "left-pad"], use_cache=True)
        assert actor._security_terminated is False

    @pytest.mark.asyncio
    async def test_untrusted_workspace_terminates_the_actor_before_osv(self) -> None:
        gate = RecordingTrustGate(deny=True)
        conn: dict[str, object] = {
            "transport": "stdio",
            "command": "./bin/srv",
            "cwd": "/work/plugin",
            "plugin_root": "/work/plugin",
        }
        actor = MCPSessionActor("plugin", conn)
        osv = AsyncMock(return_value=None)

        with (
            patch(PATCH_OSV_CHECK, osv),
            patch(PATCH_TRUST_GATE, return_value=gate),
            pytest.raises(PermissionError, match="not trusted"),
        ):
            await check_actor_stdio_security_gates(actor, conn)

        assert gate.requests == [
            {"workspace_root": None, "cwd": "/work/plugin", "plugin_root": "/work/plugin", "trust_level": "untrusted"}
        ]
        osv.assert_not_awaited()
        assert actor._security_terminated is True

    @pytest.mark.asyncio
    async def test_remote_transports_never_consult_the_stdio_gates(self) -> None:
        osv = AsyncMock(side_effect=AssertionError("OSV must not be consulted for a remote server"))
        conn: dict[str, object] = {"transport": "streamable_http", "url": "https://mcp.example.test/mcp"}

        with (
            patch(PATCH_OSV_CHECK, osv),
            patch(PATCH_TRUST_GATE, side_effect=AssertionError("trust gate must not be consulted")),
        ):
            await check_actor_stdio_security_gates(MCPSessionActor("remote", conn), conn)

        osv.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_gives_up_when_the_owner_task_never_reports_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung owner task must not hang the caller: ``start()`` fails loudly once its budget is spent."""
    monkeypatch.setattr(sa, "_SESSION_START_BUDGET_SLACK", 0.05)
    monkeypatch.setattr(sa, "_SESSION_START_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(sa, "_SESSION_START_RETRY_BACKOFF", 0.0)
    monkeypatch.setattr(sa, "_CLOSE_TIMEOUT", 0.05)

    async def hang(self: MCPSessionActor) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(MCPSessionActor, "_run", hang)
    actor = MCPSessionActor("hung", {"transport": "stdio"}, connect_timeout=0.0)

    with pytest.raises(RuntimeError, match="did not become ready within"):
        await actor.start()

    assert actor.is_healthy() is False
    assert actor._task is not None
    assert actor._task.done()  # the stuck owner task was cancelled, not leaked


def test_prefixed_tool_name_that_is_not_registered_resolves_to_nothing() -> None:
    actor = MCPSessionActor("srv", {"transport": "stdio"})
    prefix = f"mcp__{sanitize_mcp_name_component('srv')}__"
    known = SimpleNamespace(name=f"{prefix}known")
    actor._tools = {known.name: known}  # type: ignore[dict-item]

    assert resolve_actor_tool(actor, "known") is actor._tools[known.name]
    assert resolve_actor_tool(actor, f"{prefix}missing") is None  # already prefixed: no second prefix attempt


@pytest.mark.asyncio
async def test_a_crashing_dynamic_refresh_keeps_the_previous_tools(caplog: pytest.LogCaptureFixture) -> None:
    actor = MCPSessionActor("srv", {"transport": "stdio"})
    keep = SimpleNamespace(name="mcp__srv__keep", description="Safe operation.")
    added = SimpleNamespace(name="mcp__srv__added", description="Safe operation.")
    actor._tools = {keep.name: keep}  # type: ignore[dict-item]
    session = MagicMock()
    session.list_tools = AsyncMock(return_value=MagicMock())
    session.call_tool = AsyncMock()

    with (
        patch("myrm_agent_harness.toolkits.mcp.tool_converter.convert_mcp_tools", return_value=[keep, added]),
        patch("myrm_agent_harness.toolkits.mcp.agent.MCPAgent.process_session_tools", return_value=[keep, added]),
        patch.object(actor, "_enforce_runtime_posture", side_effect=RuntimeError("scanner crashed")),
        caplog.at_level(logging.WARNING, logger="myrm_agent_harness.toolkits.mcp.session_actor_tools"),
    ):
        await actor._refresh_tools(session)

    assert list(actor._tools) == ["mcp__srv__keep"]
    assert "dynamic tool refresh failed" in caplog.text


class _ServeActor:
    """The slice of ``MCPSessionActor`` that ``serve_actor_queue`` drives."""

    server_name = "srv"

    def __init__(self, *, keepalive_interval: float = 0.0) -> None:
        self._queue: asyncio.Queue[object] = asyncio.Queue()
        self._keepalive_interval = keepalive_interval
        self.read_uris: list[str] = []
        self.entered: asyncio.Queue[str] = asyncio.Queue()
        self.cancelled: list[str] = []
        self.release = asyncio.Event()

    async def _invoke(self, tool_name: str, params: dict[str, object]) -> object:
        """``block`` waits for ``release`` (recording a cancellation); ``fail`` breaks the transport."""
        await self.entered.put(tool_name)
        if tool_name == "fail":
            raise ConnectionError("pipe closed")
        if tool_name == "self-cancel":
            raise asyncio.CancelledError
        if tool_name == "block":
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled.append(tool_name)
                raise
        return f"result:{tool_name}"

    async def _keepalive_ok(self, session: object) -> bool:
        return True

    async def _read_resource(self, session: object, uri: str) -> bytes:
        self.read_uris.append(uri)
        return b"payload"


class TestServeLoopEdges:
    @pytest.mark.asyncio
    async def test_a_cancelled_resource_read_is_skipped(self) -> None:
        actor = _ServeActor()
        loop = asyncio.get_running_loop()
        cancelled: asyncio.Future[object] = loop.create_future()
        cancelled.cancel()
        live: asyncio.Future[object] = loop.create_future()
        await actor._queue.put(_ResourceRead("res://cancelled", cancelled))
        await actor._queue.put(_ResourceRead("res://live", live))
        await actor._queue.put(_SHUTDOWN)

        outcome = await serve_actor_queue(actor, object())  # type: ignore[arg-type]

        assert outcome is _ServeOutcome.SHUTDOWN
        assert actor.read_uris == ["res://live"]
        assert live.result() == b"payload"

    @pytest.mark.asyncio
    async def test_a_call_arriving_during_a_failed_keepalive_is_kept_for_the_next_session(self) -> None:
        actor = _ServeActor(keepalive_interval=0.01)
        call = _ToolCall("echo", {}, asyncio.get_running_loop().create_future())

        async def failing_keepalive(session: object) -> bool:
            await actor._queue.put(call)  # arrives while the probe is in flight
            await asyncio.sleep(0.05)  # the pending queue read consumes it meanwhile
            return False

        actor._keepalive_ok = failing_keepalive  # type: ignore[method-assign]

        outcome = await serve_actor_queue(actor, object())  # type: ignore[arg-type]

        assert outcome is _ServeOutcome.RECONNECT
        assert actor._queue.get_nowait() is call

    @pytest.mark.asyncio
    async def test_a_caller_that_gives_up_cancels_its_call_and_the_loop_serves_the_next_one(self) -> None:
        actor = _ServeActor()
        loop = asyncio.get_running_loop()
        blocked = _ToolCall("block", {}, loop.create_future())
        next_call = _ToolCall("echo", {}, loop.create_future())
        await actor._queue.put(blocked)
        await actor._queue.put(next_call)
        serving = asyncio.create_task(serve_actor_queue(actor, object()))  # type: ignore[arg-type]
        try:
            assert await asyncio.wait_for(actor.entered.get(), timeout=2) == "block"

            blocked.future.cancel()  # the caller was stopped while its call is in flight

            assert await asyncio.wait_for(next_call.future, timeout=2) == "result:echo"
            assert actor.cancelled == ["block"]
            await actor._queue.put(_SHUTDOWN)
            assert await asyncio.wait_for(serving, timeout=2) is _ServeOutcome.SHUTDOWN
        finally:
            serving.cancel()

    @pytest.mark.asyncio
    async def test_a_cancelled_loop_cancels_the_call_it_runs_and_fails_the_caller(self) -> None:
        actor = _ServeActor()
        blocked = _ToolCall("block", {}, asyncio.get_running_loop().create_future())
        await actor._queue.put(blocked)
        serving = asyncio.create_task(serve_actor_queue(actor, object()))  # type: ignore[arg-type]
        assert await asyncio.wait_for(actor.entered.get(), timeout=2) == "block"

        serving.cancel()

        with pytest.raises(asyncio.CancelledError):
            await serving
        with pytest.raises(RuntimeError, match="closed during call"):
            blocked.future.result()
        assert actor.cancelled == ["block"]  # no call is left running behind a stopped loop

    @pytest.mark.asyncio
    async def test_a_call_that_cancels_itself_is_not_taken_for_a_caller_leaving(self) -> None:
        actor = _ServeActor()
        call = _ToolCall("self-cancel", {}, asyncio.get_running_loop().create_future())
        await actor._queue.put(call)

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(serve_actor_queue(actor, object()), timeout=2)  # type: ignore[arg-type]

        with pytest.raises(RuntimeError, match="closed during call"):
            call.future.result()

    @pytest.mark.asyncio
    async def test_a_transport_error_from_the_call_reaches_the_caller_and_reconnects(self) -> None:
        actor = _ServeActor()
        call = _ToolCall("fail", {}, asyncio.get_running_loop().create_future())
        await actor._queue.put(call)

        outcome = await asyncio.wait_for(serve_actor_queue(actor, object()), timeout=2)  # type: ignore[arg-type]

        assert outcome is _ServeOutcome.RECONNECT
        with pytest.raises(ConnectionError, match="pipe closed"):
            call.future.result()


class TestSdkGuards:
    @pytest.mark.asyncio
    async def test_notification_handler_errors_stay_inside_the_handler(self, caplog: pytest.LogCaptureFixture) -> None:
        queue = MagicMock()
        queue.put_nowait.side_effect = RuntimeError("queue closed")
        handler = build_notification_handler("srv", queue)
        assert handler is not None

        with caplog.at_level(logging.ERROR, logger="myrm_agent_harness.toolkits.mcp.session_actor_types"):
            await handler(ToolListChangedNotification(method="notifications/tools/list_changed"))

        assert "Error in MCP notification handler for 'srv'" in caplog.text

    @pytest.mark.asyncio
    async def test_resource_read_reports_a_missing_sdk(self) -> None:
        with (
            patch.dict("sys.modules", {"mcp.types": None}),
            pytest.raises(RuntimeError, match="MCP SDK not available for resource reading"),
        ):
            await read_mcp_resource(MagicMock(), "res://anything", 1.0)
