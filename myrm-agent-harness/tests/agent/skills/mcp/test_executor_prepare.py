"""Unit tests for SkillExecutor command preparation and client payload assembly.

[INPUT]
- myrm_agent_harness.agent.skills.mcp::executor (POS: PTC detection, client assembly)
- myrm_agent_harness.agent.skills.runtime::registry (POS: MCP skill metadata lookup)

[OUTPUT]
- Coverage for prepare_for_execution, regex fallback, import rewrite, client assembly from an endpoint,
  and read-only tool collection.

[POS]
Executor preparation tests. Keeps PTC detection and generated-client assembly covered
without spawning a sandbox or an IPC server.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.skills.mcp.executor import SkillExecutor
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import IPCEndpoint
from myrm_agent_harness.agent.skills.runtime.registry import SkillRegistry
from myrm_agent_harness.backends.skills.types import MCPSkillData, SkillMetadata
from myrm_agent_harness.toolkits.code_execution import MCPConfigItem

_ENDPOINT = IPCEndpoint(socket_path="/tmp/sock", tcp_port=0, auth_token="token", trace_nonce="nonce")


def _mcp_skill(name: str, tools: list[str], config: list[dict[str, object]]) -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description=f"MCP skill {name}",
        mcp=MCPSkillData(server=name, tools=tools, config=config),
    )


def test_prepare_without_ptc_returns_original_command(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = SkillExecutor()
    monkeypatch.setattr(executor, "detect_skill_in_command", lambda _command: (False, None))

    context = executor.prepare_for_execution("echo hi", _ENDPOINT)

    assert context.is_skill is False
    assert context.prepared_code == "echo hi"
    assert context.original_code == "echo hi"


def test_prepare_with_ptc_but_no_python_returns_original(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = SkillExecutor()
    monkeypatch.setattr(executor, "detect_skill_in_command", lambda _command: (True, "demo_skill"))
    monkeypatch.setattr(executor, "_extract_python_code", lambda _command: None)

    context = executor.prepare_for_execution("echo hi", _ENDPOINT)

    assert context.is_skill is False
    assert context.prepared_code == "echo hi"


def test_prepare_mcp_skill_uses_config_and_injected_client(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = SkillExecutor()
    config = [MCPConfigItem(name="demo", type="stdio", command="echo", args=[])]
    monkeypatch.setattr(executor, "detect_skill_in_command", lambda _command: (True, "demo_skill"))
    monkeypatch.setattr(executor, "_extract_python_code", lambda _command: "from skills.demo_skill import ping")
    monkeypatch.setattr(executor, "get_skill_mcp_config", lambda _name: config)
    monkeypatch.setattr(executor, "_rewrite_skill_imports", lambda code: code)
    monkeypatch.setattr(executor, "_generate_mcp_client_code", lambda *args, **kwargs: "CLIENT")
    monkeypatch.setattr(executor, "_collect_read_only_tools", lambda _name: frozenset())

    context = executor.prepare_for_execution("python3 -c 'from skills.demo_skill import ping'", _ENDPOINT)

    assert context.is_skill is True
    assert context.skill_name == "demo_skill"
    assert context.mcp_config == config
    assert context.prepared_code.startswith("CLIENT")


def test_prepare_builtin_does_not_look_up_mcp_config(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = SkillExecutor()
    monkeypatch.setattr(executor, "detect_skill_in_command", lambda _command: (True, "__builtin__"))
    monkeypatch.setattr(executor, "_extract_python_code", lambda _command: "from tools.notify import notify")
    monkeypatch.setattr(
        executor,
        "get_skill_mcp_config",
        lambda _name: pytest.fail("builtin must not resolve an MCP config"),
    )
    monkeypatch.setattr(executor, "_rewrite_skill_imports", lambda code: code)
    monkeypatch.setattr(executor, "_generate_mcp_client_code", lambda *args, **kwargs: "CLIENT")
    monkeypatch.setattr(executor, "_collect_read_only_tools", lambda _name: frozenset())

    context = executor.prepare_for_execution("python3 -c 'from tools.notify import notify'", _ENDPOINT)

    assert context.is_skill is True
    assert context.skill_name == "__builtin__"
    assert context.mcp_config is None


def test_detect_skill_in_command_without_python(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = SkillExecutor()
    monkeypatch.setattr(executor, "_extract_python_code", lambda _command: None)

    assert executor.detect_skill_in_command("echo hi") == (False, None)


def test_regex_fallback_detects_builtin_tools_import() -> None:
    assert SkillExecutor()._detect_ptc_by_regex("from tools.notify import notify") == (True, "__builtin__")


def test_rewrite_bare_skill_import_adds_prefix() -> None:
    rewritten = SkillExecutor()._rewrite_skill_imports("from demo_skill import ping")

    assert rewritten == "from skills.demo_skill import ping"


def test_generate_client_forwards_the_endpoint_and_read_only_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    import myrm_agent_harness.agent.skills.mcp.client_templates as client_templates

    captured: dict[str, object] = {}

    def fake_generate(socket_path: str, **kwargs: object) -> str:
        captured["socket_path"] = socket_path
        captured.update(kwargs)
        return "CLIENT"

    monkeypatch.setattr(client_templates, "generate_ipc_client_code", fake_generate)
    endpoint = IPCEndpoint(socket_path="/tmp/sock", tcp_port=4242, auth_token="token", trace_nonce="nonce")

    code = SkillExecutor._generate_mcp_client_code(endpoint, frozenset({"demo.ping"}))

    assert code == "CLIENT"
    assert captured == {
        "socket_path": "/tmp/sock",
        "auth_token": "token",
        "trace_nonce": "nonce",
        "read_only_tools": frozenset({"demo.ping"}),
        "tcp_port": 4242,
    }


def test_collect_read_only_tools_for_builtin_and_missing_skills(monkeypatch: pytest.MonkeyPatch) -> None:
    assert SkillExecutor._collect_read_only_tools("__builtin__") == frozenset()

    registry = SkillRegistry()
    monkeypatch.setattr("myrm_agent_harness.agent.skills.runtime.registry.skill_registry", registry)
    assert SkillExecutor._collect_read_only_tools("missing_skill") == frozenset()


def test_collect_read_only_tools_reads_safety_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = SkillRegistry()
    registry.register(_mcp_skill("demo_skill", ["ping", "write_row"], []))
    monkeypatch.setattr("myrm_agent_harness.agent.skills.runtime.registry.skill_registry", registry)

    read_only = MagicMock(is_read_only=True)
    writable = MagicMock(is_read_only=False)

    def fake_metadata(skill_name: str, tool_name: str) -> tuple[object, ...]:
        assert skill_name == "demo_skill"
        return (read_only if tool_name == "ping" else writable,)

    monkeypatch.setattr(
        "myrm_agent_harness.core.security.tool_registry.registry.get_ptc_safety_metadata",
        fake_metadata,
    )

    assert SkillExecutor._collect_read_only_tools("demo_skill") == frozenset({"demo_skill.ping"})
