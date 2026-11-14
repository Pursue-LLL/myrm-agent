"""The MCP IPC server lives exactly as long as the script execution it serves.

``mcp_ipc_endpoint`` starts a server for one execution, scoped to that execution's caller (session, agent, workspace,
read-only state), and stops it however the execution ends.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

from myrm_agent_harness.agent.skills.mcp import ipc_endpoint as ipc_endpoint_module
from myrm_agent_harness.agent.skills.mcp.ipc_call_budget import CallBudget
from myrm_agent_harness.agent.skills.mcp.ipc_endpoint import mcp_ipc_endpoint
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import CallerScope, IPCEndpoint, MCPIPCServer

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix socket transport")


def _scope() -> CallerScope:
    return CallerScope(session_id=f"chat_{uuid.uuid4().hex}")


async def _call(endpoint: IPCEndpoint, body: dict[str, object], *, token: str | None = None) -> dict[str, object]:
    reader, writer = await asyncio.open_unix_connection(endpoint.socket_path)
    try:
        payload = json.dumps({"auth_token": token or endpoint.auth_token, **body}).encode()
        writer.write(len(payload).to_bytes(4, "big") + payload)
        await writer.drain()
        size = int.from_bytes(await reader.readexactly(4), "big")
        response: dict[str, object] = json.loads(await reader.readexactly(size))
        return response
    finally:
        writer.close()
        await writer.wait_closed()


def _notify() -> dict[str, object]:
    return {"skill_name": "__builtin__", "tool_name": "notify", "params": {"message": "m"}}


async def _refuses_connections(socket_path: str) -> bool:
    try:
        _, writer = await asyncio.open_unix_connection(socket_path)
    except (ConnectionRefusedError, FileNotFoundError):
        return True
    writer.close()
    return False


class TestLifetime:
    async def test_server_answers_inside_the_block_and_is_gone_after_it(self) -> None:
        async with mcp_ipc_endpoint(_scope()) as endpoint:
            assert os.path.exists(endpoint.socket_path)
            assert (await _call(endpoint, _notify()))["success"] is True

        assert not os.path.exists(endpoint.socket_path)
        assert await _refuses_connections(endpoint.socket_path)

    async def test_server_is_stopped_when_the_execution_raises(self) -> None:
        with pytest.raises(RuntimeError, match="script died"):
            async with mcp_ipc_endpoint(_scope()) as endpoint:
                raise RuntimeError("script died")

        assert not os.path.exists(endpoint.socket_path)

    async def test_server_is_stopped_when_the_execution_is_cancelled(self) -> None:
        endpoints: list[IPCEndpoint] = []
        entered = asyncio.Event()

        async def execution() -> None:
            async with mcp_ipc_endpoint(_scope()) as endpoint:
                endpoints.append(endpoint)
                entered.set()
                await asyncio.sleep(30)

        task = asyncio.ensure_future(execution())
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert await _refuses_connections(endpoints[0].socket_path)

    async def test_a_call_still_running_when_the_execution_ends_is_cancelled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The script is gone, so nobody can use the answer; the MCP server must not keep working for it."""
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def slow_request(self: MCPIPCServer, message: str) -> str:
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()
                raise
            return "{}"

        monkeypatch.setattr(MCPIPCServer, "_process_request", slow_request)

        async with mcp_ipc_endpoint(_scope()) as endpoint:
            _, writer = await asyncio.open_unix_connection(endpoint.socket_path)
            payload = json.dumps({"skill_name": "s", "tool_name": "t", "params": {}}).encode()
            writer.write(len(payload).to_bytes(4, "big") + payload)
            await writer.drain()
            await asyncio.wait_for(started.wait(), 5)

        await asyncio.wait_for(cancelled.wait(), 5)
        writer.close()

    async def test_a_start_cancelled_after_the_listener_is_bound_leaves_nothing_behind(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """asyncio yields once after binding, before ``start()`` can record the listener; a cancel there leaks it."""
        bound: asyncio.Event = asyncio.Event()
        paths: list[str] = []
        real_start_unix_server = asyncio.start_unix_server

        async def start_unix_server_with_a_gap(*args: object, **kwargs: object) -> asyncio.Server:
            server = await real_start_unix_server(*args, **kwargs)  # type: ignore[arg-type]
            paths.append(str(kwargs["path"]))
            bound.set()
            await asyncio.sleep(0.2)
            return server

        monkeypatch.setattr(asyncio, "start_unix_server", start_unix_server_with_a_gap)

        async def execution() -> None:
            async with mcp_ipc_endpoint(_scope()):
                pytest.fail("the block must not run: start was cancelled")

        task = asyncio.ensure_future(execution())
        await asyncio.wait_for(bound.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 10)

        assert not os.path.exists(paths[0])
        assert await _refuses_connections(paths[0])

    async def test_start_failure_names_the_socket_and_leaves_nothing_behind(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        blocker = tmp_path / "not-a-directory"
        blocker.write_text("x", encoding="utf-8")
        monkeypatch.setattr(ipc_endpoint_module, "execution_ipc_socket_path", lambda: str(blocker / "s.sock"))

        with pytest.raises(RuntimeError, match=r"Failed to start MCP IPC server at .*s\.sock"):
            async with mcp_ipc_endpoint(_scope()):
                pytest.fail("the block must not run when the server could not start")


class TestIsolation:
    async def test_each_execution_has_its_own_socket_token_and_nonce(self) -> None:
        async with mcp_ipc_endpoint(_scope()) as first, mcp_ipc_endpoint(_scope()) as second:
            assert first.socket_path != second.socket_path
            assert first.auth_token != second.auth_token
            assert first.trace_nonce != second.trace_nonce

    async def test_one_execution_cannot_use_another_ones_token(self) -> None:
        async with mcp_ipc_endpoint(_scope()) as first, mcp_ipc_endpoint(_scope()) as second:
            body = await _call(second, _notify(), token=first.auth_token)

        assert body["success"] is False
        assert "unauthorized" in str(body["error"]).lower()

    async def test_concurrent_executions_are_served_as_their_own_callers(self) -> None:
        """Two executions in flight at once each keep their own read-only state; neither can borrow the other's."""
        from myrm_agent_harness.core.security.tool_registry.registry import register_ptc_safety_metadata
        from myrm_agent_harness.core.security.tool_registry.safety_table import SafetyMetadata

        register_ptc_safety_metadata(
            "mcp_demo_skill", "create-record", SafetyMetadata(is_read_only=False), {"readOnlyHint": False}
        )
        write_call = {"skill_name": "mcp_demo_skill", "tool_name": "create-record", "params": {}}

        async with (
            mcp_ipc_endpoint(CallerScope(session_id="a", readonly_workspace=True)) as read_only_run,
            mcp_ipc_endpoint(CallerScope(session_id="b")) as writing_run,
        ):
            blocked = await _call(read_only_run, write_call)
            reached_the_tool = await _call(writing_run, write_call)

        assert "read-only" in str(blocked["error"]).lower()
        assert "read-only" not in str(reached_the_tool.get("error") or "").lower()

    async def test_the_session_ceiling_adds_up_across_the_executions_of_one_chat(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ipc_endpoint_module, "_SESSION_BUDGET", CallBudget(session_call_ceiling=2))
        scope = _scope()
        results = []
        for _ in range(3):
            async with mcp_ipc_endpoint(scope) as endpoint:
                results.append(await _call(endpoint, _notify()))

        assert [r["success"] for r in results] == [True, True, False]
        assert "ceiling" in str(results[2]["error"]).lower()
