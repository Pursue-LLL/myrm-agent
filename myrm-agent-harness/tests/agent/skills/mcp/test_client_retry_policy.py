"""A generated MCP IPC client sends each call once and never replays it.

A connection failure can happen after the request reached the server, so replaying a call risks duplicate side
effects (two issues, two messages), and a server's own claim that a tool only reads cannot be checked.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from myrm_agent_harness.agent.skills.mcp.client_templates import generate_ipc_client_code

Namespace = dict[str, object]


def _build_client(make_failure: Callable[[Namespace], BaseException], attempts: list[str]) -> Namespace:
    """Compile the generated client and stub its transport with one that counts attempts and always fails."""
    source = generate_ipc_client_code("/tmp/does-not-matter.sock", auth_token="t", trace_nonce="n")
    namespace: Namespace = {}
    exec(compile(source, "<generated_client>", "exec"), namespace)  # noqa: S102 - executing our own generated module

    async def failing_request(skill: str, tool: str, params: dict[str, object]) -> object:
        attempts.append(f"{skill}.{tool}")
        raise make_failure(namespace)

    namespace["_ipc_request"] = failing_request
    return namespace


@pytest.mark.parametrize(
    "make_failure",
    [
        lambda _ns: ConnectionError("simulated mid-flight disconnect"),
        lambda _ns: BrokenPipeError("simulated broken pipe"),
        lambda _ns: FileNotFoundError("simulated missing socket"),
        lambda _ns: asyncio.IncompleteReadError(b"", 4),
    ],
    ids=["connection-error", "broken-pipe", "missing-socket", "incomplete-read"],
)
@pytest.mark.parametrize("tool", ["create-issue", "ping"])
def test_a_connection_failure_is_attempted_exactly_once(
    make_failure: Callable[[Namespace], BaseException], tool: str
) -> None:
    attempts: list[str] = []
    client = _build_client(make_failure, attempts)

    with pytest.raises(Exception, match="Connection"):
        asyncio.run(client["_call"]("mcp_skill", tool, {}))  # type: ignore[operator]

    assert attempts == [f"mcp_skill.{tool}"]


def test_a_host_reported_error_is_raised_as_it_came() -> None:
    """A server-side error is deterministic: it reaches the script after one attempt, not wrapped a second time."""
    attempts: list[str] = []
    client = _build_client(lambda ns: ns["MCPError"]("boom", "mcp_skill", "ping"), attempts)  # type: ignore[operator]

    with pytest.raises(Exception, match="boom") as raised:
        asyncio.run(client["_call"]("mcp_skill", "ping", {}))  # type: ignore[operator]

    assert str(raised.value) == "[mcp_skill.ping] boom"
    assert attempts == ["mcp_skill.ping"]


def test_an_unexpected_failure_reaches_the_script_as_an_mcp_error() -> None:
    attempts: list[str] = []
    client = _build_client(lambda _ns: ValueError("bad payload"), attempts)

    with pytest.raises(Exception, match=r"\[mcp_skill\.ping\] ValueError: bad payload") as raised:
        asyncio.run(client["_call"]("mcp_skill", "ping", {}))  # type: ignore[operator]

    assert type(raised.value).__name__ == "MCPError"
    assert attempts == ["mcp_skill.ping"]
