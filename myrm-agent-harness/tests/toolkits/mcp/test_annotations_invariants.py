"""Invariants of the MCP tool annotations a server declares about itself.

A server's hints are its own unverified statements, so they may tighten what the host does and may let tools of
different servers run side by side, but nothing else. Each test drives one family of consumers, through a real MCP
server and the production connection pool, and asserts the consumers stay as strict as for an unannotated tool.

[INPUT]
- tests.support.mcp_testkit.probe_connection::connect_probe_server, ProbeServer (POS: the probe server seen through the production pool)
- myrm_agent_harness.agent.middlewares.approval.batch_processor::evaluate_tool_batch (POS: approval verdicts of a tool batch)
- myrm_agent_harness.agent.sub_agents.builder::filter_tools (POS: the tools a read-only child receives)
- myrm_agent_harness.agent.skills.mcp.ipc_request_policy (POS: refusals of the PTC IPC server in read-only scopes)
- myrm_agent_harness.agent.skills.mcp.executor::SkillExecutor (POS: injects the generated PTC client)
- myrm_agent_harness.agent._factory.mcp_routing::_wrap_direct_tool_with_cache (POS: the direct-call result cache)

[OUTPUT]
- Tests of the approval, read-only sandbox, IPC gate, untrusted-turn, no-replay and cache invariants.

[POS]
Guards the hand-off from a server's declarations to every consumer of the host's safety metadata, so a later change
that lets a claim loosen one of them fails here instead of in production.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace

import pytest
import pytest_asyncio
from langchain_core.messages import ToolCall

from myrm_agent_harness.agent._factory.mcp_routing import _wrap_direct_tool_with_cache
from myrm_agent_harness.agent.middlewares.approval._allow_always import protected_instruction_file_target
from myrm_agent_harness.agent.middlewares.approval.batch_processor import evaluate_tool_batch
from myrm_agent_harness.agent.middlewares.completion.completion_guard.safety import is_mutating_tool
from myrm_agent_harness.agent.middlewares.tooling._runtime_tool_governance import derive_runtime_allowed_tools
from myrm_agent_harness.agent.security.types import PathPolicy, SecurityConfig
from myrm_agent_harness.agent.skills.mcp.cache_policy import get_cache_buckets
from myrm_agent_harness.agent.skills.mcp.executor import SkillExecutor
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import CallerScope, IPCEndpoint, MCPIPCRequest
from myrm_agent_harness.agent.skills.mcp.ipc_request_policy import read_only_policy_error, script_file_policy_error
from myrm_agent_harness.agent.skills.runtime.registry import SkillRegistry
from myrm_agent_harness.agent.sub_agents.builder import filter_tools
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig, WorkspacePolicy
from myrm_agent_harness.backends.skills.types import MCPSkillData, SkillMetadata
from myrm_agent_harness.core.context_vars import chat_id_var
from myrm_agent_harness.toolkits.code_execution import MCPConfigItem
from myrm_agent_harness.toolkits.mcp.config import MCPConfig
from tests.support.mcp_testkit.probe_connection import SERVER_NAME, ProbeServer, connect_probe_server

_ENDPOINT = IPCEndpoint(socket_path="/tmp/sock", tcp_port=0, auth_token="token", trace_nonce="nonce")
_USER_CODE_MARKER = "\n\n# === User Code ===\n"


@pytest_asyncio.fixture(scope="module")
async def _connected(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[ProbeServer]:
    async with connect_probe_server("streamable_http", tmp_path_factory.mktemp("probe")) as probe:
        yield probe


@pytest.fixture
def probe(_connected: ProbeServer) -> ProbeServer:
    """The connected probe server with its registrations in place (``tests/conftest.py`` empties them per test)."""
    _connected.register()
    return _connected


def _spellings(probe: ProbeServer) -> list[str]:
    """Every name a consumer may look a probe tool up by: the declared one and the one the model calls."""
    return [*probe.tools, *(probe.call_name(name) for name in probe.tools)]


async def test_no_call_is_approved_without_asking(probe: ProbeServer) -> None:
    direct = [ToolCall(name=probe.call_name(name), args={}, id=f"direct-{name}") for name in probe.tools]
    proxied = [
        ToolCall(
            name="bash_code_execute_tool",
            args={"command": f'python -c "from skills.{probe.skill_name} import _{name}; _{name}()"'},
            id=f"proxied-{name}",
        )
        for name in probe.tools
    ]

    approved, _denied, pending = await evaluate_tool_batch(
        tool_calls=[*direct, *proxied],
        config=SecurityConfig(auto_mode_enabled=False, path_policy=PathPolicy()),
        is_cron=False,
        workspace_root="/workspace",
        session_key="annotations-invariants",
        args_hashes={},
    )

    assert approved == []
    assert len(pending) == len(direct) + len(proxied)


def test_read_only_sandbox_holds_no_mcp_tool(probe: ProbeServer) -> None:
    sandbox = replace(SubagentConfig(system_prompt="child"), workspace_policy=WorkspacePolicy.READ_ONLY_SANDBOX)

    assert filter_tools(sandbox, list(probe.tools.values())) == []


def test_read_only_scopes_refuse_every_script_call(probe: ProbeServer) -> None:
    for tool_name in _spellings(probe):
        request = MCPIPCRequest(skill_name=probe.skill_name, tool_name=tool_name, params={})

        assert read_only_policy_error(request, CallerScope(readonly_workspace=True)), tool_name
        assert script_file_policy_error(request, CallerScope(script_file=True)), tool_name


def test_every_tool_still_counts_as_effectful(probe: ProbeServer) -> None:
    names = [probe.call_name(name) for name in probe.tools]

    assert all(is_mutating_tool(name) for name in names)
    assert all(protected_instruction_file_target(name, {"path": "/workspace/AGENTS.md"}) for name in names)

    sentinel = "file_read_tool"
    allowed, reasons = derive_runtime_allowed_tools(
        tool_names=[sentinel, *names], recent_human_text="Explain what is stored."
    )
    assert reasons == ("readonly_intent_gate",)
    assert allowed == frozenset({sentinel})


async def test_ptc_client_never_replays_a_call(probe: ProbeServer, monkeypatch: pytest.MonkeyPatch) -> None:
    skill = SkillMetadata(
        name=probe.skill_name,
        description="probe",
        mcp=MCPSkillData(server=SERVER_NAME, tools=_spellings(probe), config=[]),
    )
    registry = SkillRegistry()
    registry.register(skill)
    monkeypatch.setattr("myrm_agent_harness.agent.skills.runtime.registry.skill_registry", registry)
    executor = SkillExecutor()
    monkeypatch.setattr(executor, "detect_skill_in_command", lambda _command: (True, probe.skill_name))
    monkeypatch.setattr(executor, "_extract_python_code", lambda _command: "pass")
    monkeypatch.setattr(
        executor, "get_skill_mcp_config", lambda _name: [MCPConfigItem(name="p", type="stdio", command="echo", args=[])]
    )

    prepared = executor.prepare_for_execution("python -c pass", _ENDPOINT).prepared_code
    client: dict[str, object] = {}
    exec(compile(prepared.split(_USER_CODE_MARKER)[0], "<generated_client>", "exec"), client)  # noqa: S102 - our own generated module

    attempts: list[str] = []

    async def disconnect(skill_name: str, tool_name: str, params: dict[str, object]) -> object:
        attempts.append(tool_name)
        raise ConnectionError("simulated mid-flight disconnect")

    client["_ipc_request"] = disconnect
    for tool_name in _spellings(probe):
        attempts.clear()
        with pytest.raises(Exception, match="Connection"):
            await client["_call"](probe.skill_name, tool_name, {})  # type: ignore[operator]
        assert attempts == [tool_name], f"{tool_name} must be attempted exactly once"


async def test_a_write_clears_the_direct_result_cache_whatever_it_declares(probe: ProbeServer) -> None:
    config = MCPConfig(
        name=SERVER_NAME, type="stdio", command="echo", cache_ttl_seconds=60, cacheable_tools=["list_items"]
    )
    list_items = _wrap_direct_tool_with_cache(probe.tools["list_items"], config)
    append_item = _wrap_direct_tool_with_cache(probe.tools["append_item"], config)
    items_file = probe.marks_dir / "items.txt"
    items_file.unlink(missing_ok=True)
    get_cache_buckets().clear()
    token = chat_id_var.set("annotations-invariants")
    try:
        first = await list_items.ainvoke({})
        items_file.write_text("outside\n")
        assert await list_items.ainvoke({}) == first, (
            "the read must be served from the cache for this test to mean anything"
        )

        await append_item.ainvoke({"item": "a"})

        assert '"result": "outside,a"' in await list_items.ainvoke({})
    finally:
        chat_id_var.reset(token)
        get_cache_buckets().clear()
