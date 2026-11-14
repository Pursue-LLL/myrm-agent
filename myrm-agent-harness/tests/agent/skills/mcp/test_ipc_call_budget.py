"""Call budget of the MCP IPC server.

The budget guards against one runaway script becoming an unbounded external-API
amplifier. It is not a per-chat counter that never resets. These tests pin its two properties:

1. the budget belongs to one script execution (an id minted by the server), so scripts do not starve each other;
2. a session-wide ceiling per time window still bounds a chat that keeps starting scripts.
"""

from __future__ import annotations

import asyncio
import re
import sys
import uuid

import pytest

from myrm_agent_harness.agent.skills.mcp import ipc_call_budget
from myrm_agent_harness.agent.skills.mcp import proxy_service as proxy_service_module
from myrm_agent_harness.agent.skills.mcp.client_templates import generate_ipc_client_code
from myrm_agent_harness.agent.skills.mcp.ipc_call_budget import (
    DEFAULT_MAX_CALLS_PER_EXECUTION,
    SESSION_CALL_WINDOW_SECONDS,
    CallBudget,
)
from myrm_agent_harness.agent.skills.mcp.ipc_endpoint import mcp_ipc_endpoint
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import CallerScope, IPCEndpoint


def _budget(**limits: int) -> CallBudget:
    return CallBudget(**limits)


class TestExecutionBudget:
    def test_executions_have_independent_budgets(self) -> None:
        budget = _budget(max_calls_per_execution=2)

        assert budget.consume("chat", "t1") is None
        assert budget.consume("chat", "t1") is None
        exhausted = budget.consume("chat", "t1")

        assert exhausted is not None
        assert "budget exhausted" in exhausted
        assert "2/2" in exhausted
        assert budget.consume("chat", "t2") is None, "a new script in the same chat starts fresh"

    def test_rejected_call_is_not_charged(self) -> None:
        budget = _budget(max_calls_per_execution=1, session_call_ceiling=10)
        budget.consume("chat", "t1")

        for _ in range(3):
            assert budget.consume("chat", "t1") is not None

        assert budget._execution_calls["t1"] == 1
        assert budget._session_windows["chat"].calls == 1

    def test_request_without_session_is_only_bound_by_the_execution_budget(self) -> None:
        budget = _budget(max_calls_per_execution=1)

        assert budget.consume(None, "t1") is None
        assert budget.consume(None, "t1") is not None
        assert budget._session_windows == {}

    def test_default_budget_is_the_shared_ptc_number(self) -> None:
        assert DEFAULT_MAX_CALLS_PER_EXECUTION == 50


class TestSessionCeiling:
    def test_ceiling_spans_the_executions_of_one_session(self) -> None:
        budget = _budget(max_calls_per_execution=50, session_call_ceiling=3)

        for execution_id in ("t1", "t2", "t3"):
            assert budget.consume("chat", execution_id) is None
        blocked = budget.consume("chat", "t4")

        assert blocked is not None
        assert "ceiling" in blocked
        assert budget.consume("other-chat", "t5") is None, "ceilings are per session"

    def test_window_rolls_over(self, monkeypatch: pytest.MonkeyPatch) -> None:
        now = [1000.0]
        monkeypatch.setattr(ipc_call_budget.time, "monotonic", lambda: now[0])
        budget = _budget(session_call_ceiling=1)

        assert budget.consume("chat", "t1") is None
        assert budget.consume("chat", "t2") is not None
        now[0] += SESSION_CALL_WINDOW_SECONDS

        assert budget.consume("chat", "t3") is None


class TestBoundedBookkeeping:
    def test_tracking_tables_never_outgrow_the_bound(self) -> None:
        budget = _budget()
        overflow = ipc_call_budget._MAX_TRACKED_BUCKETS + 10

        for index in range(overflow):
            assert budget.consume(f"chat-{index}", f"trace-{index}") is None

        assert len(budget._execution_calls) == ipc_call_budget._MAX_TRACKED_BUCKETS
        assert len(budget._session_windows) == ipc_call_budget._MAX_TRACKED_BUCKETS
        assert "trace-0" not in budget._execution_calls, "the oldest bucket is the one evicted"
        assert f"trace-{overflow - 1}" in budget._execution_calls


class _FakeProxyService:
    async def invoke_tool(self, skill: str, tool: str, params: dict[str, object], **_: object) -> dict[str, str]:
        return {"ok": "1"}


def _client(endpoint: IPCEndpoint) -> str:
    return generate_ipc_client_code(
        endpoint.socket_path, auth_token=endpoint.auth_token, trace_nonce=endpoint.trace_nonce
    )


def _loop_script(calls: int) -> str:
    return (
        "from skills.demo import ping\n"
        "async def main():\n"
        "    done = 0\n"
        "    try:\n"
        f"        for i in range({calls}):\n"
        "            await ping(n=i)\n"
        "            done += 1\n"
        "    finally:\n"
        "        print('done', done)\n"
        "asyncio.run(main())\n"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="Unix socket semantics")
@pytest.mark.asyncio
async def test_real_client_scripts_in_one_chat_do_not_starve_each_other(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end over the wire: real generated client, separate OS processes, one chat.

    A per-chat counter that never resets would kill the second script at its 21st call and
    leave the third unable to make a single call.
    """
    monkeypatch.setattr(proxy_service_module, "get_mcp_skill_proxy_service", lambda: _FakeProxyService())
    scope = CallerScope(session_id=f"chat_{uuid.uuid4().hex}")

    async def run(calls: int) -> tuple[int, int, str]:
        async with mcp_ipc_endpoint(scope) as endpoint:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                f"{_client(endpoint)}\n{_loop_script(calls)}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        done = re.search(r"done (\d+)", stdout.decode())
        assert done is not None, stderr.decode()
        return proc.returncode or 0, int(done.group(1)), stderr.decode()

    assert (await run(30))[:2] == (0, 30)
    assert (await run(30))[:2] == (0, 30)
    assert (await run(1))[:2] == (0, 1)

    code, done, stderr = await run(DEFAULT_MAX_CALLS_PER_EXECUTION + 10)
    assert code != 0
    assert done == DEFAULT_MAX_CALLS_PER_EXECUTION, "a runaway loop is still cut off at the budget"
    assert "Script tool-call budget exhausted" in stderr
