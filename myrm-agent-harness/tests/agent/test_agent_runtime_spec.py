"""AgentRuntimeSpec: its field contract, and what the factory does with it."""

import ast
import dataclasses
import inspect
from unittest.mock import AsyncMock

import pytest
from langchain_core.tools import tool

from myrm_agent_harness.agent._factory import builder as factory
from myrm_agent_harness.agent._factory.builder import create_skill_agent
from myrm_agent_harness.agent.types import AgentRuntimeSpec, WorkspaceBinding

# Display label only: the factory builds no runtime behaviour from it.
_LABEL_ONLY_FIELDS = frozenset({"name"})


def test_agent_runtime_spec_initialization() -> None:
    spec = AgentRuntimeSpec(
        name="Test Agent",
        system_prompt="Test prompt",
        mcp_servers=[],
        agent_id="test_agent",
        workspace_binding=WorkspaceBinding(root_path="/tmp/test", mode="chat"),
    )

    assert spec.system_prompt == "Test prompt"
    assert spec.agent_id == "test_agent"
    assert spec.workspace_binding is not None
    assert spec.workspace_binding.root_path == "/tmp/test"
    assert spec.workspace_binding.mode == "chat"


def test_workspace_binding_modes() -> None:
    binding = WorkspaceBinding(root_path="/tmp/test", mode="background")
    assert binding.mode == "background"

    binding2 = WorkspaceBinding(root_path="/tmp/test", mode="subagent")
    assert binding2.mode == "subagent"


def test_every_spec_field_is_read_by_the_factory() -> None:
    """A field the factory never reads is a silent no-op: the caller sets it and nothing changes."""
    tree = ast.parse(inspect.getsource(factory))
    read = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "spec"
    }
    declared = {field.name for field in dataclasses.fields(AgentRuntimeSpec)}

    unread = declared - read - _LABEL_ONLY_FIELDS

    assert not unread, f"AgentRuntimeSpec fields the factory never reads: {sorted(unread)}"


def test_every_factory_parameter_is_read() -> None:
    """A parameter the factory never reads is a silent no-op: the caller passes it and nothing changes."""
    tree = ast.parse(inspect.getsource(create_skill_agent))
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef))
    declared = {arg.arg for arg in function.args.args + function.args.kwonlyargs}
    read = {
        node.id
        for statement in function.body
        for node in ast.walk(statement)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }

    unread = declared - read

    assert not unread, f"create_skill_agent parameters the factory never reads: {sorted(unread)}"


@pytest.mark.asyncio
async def test_the_model_resolver_reaches_the_agent() -> None:
    resolver = object()
    spec = AgentRuntimeSpec(agent_id="t", name="t", system_prompt=None)

    agent = await create_skill_agent(spec=spec, llm=AsyncMock(), checkpointer=None, model_resolver=resolver)

    assert agent.model_resolver is resolver


@tool
def domain_lookup_tool() -> str:
    """A domain tool the caller supplies."""
    return "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize(("no_builtin_tools", "has_shell"), [(False, True), (True, False)])
async def test_no_builtin_tools_decides_whether_the_agent_gets_the_built_in_tools(
    no_builtin_tools: bool, has_shell: bool
) -> None:
    spec = AgentRuntimeSpec(agent_id="t", name="t", system_prompt=None, no_builtin_tools=no_builtin_tools)
    agent = await create_skill_agent(spec=spec, llm=AsyncMock(), tools=[domain_lookup_tool], checkpointer=None)

    names = {t.name for t in await agent._build_tools()}

    assert ("bash_code_execute_tool" in names) is has_shell
    assert "domain_lookup_tool" in names
