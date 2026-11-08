"""The generator decides which MCP skills may list their functions in the L1 catalog, under the names the model imports."""

from __future__ import annotations

from types import SimpleNamespace

from myrm_agent_harness.agent.skills.mcp.core_generator import SKILL_USAGE_TEMPLATE, MCPSkillGenerator
from myrm_agent_harness.agent.skills.mcp.tool_name_utils import resolve_mcp_tool_name
from myrm_agent_harness.agent.skills.runtime.ptc_calling import CALL_SYNTAX, CALL_WORKFLOW


def _tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, description=f"{name} tool", args_schema=None)


def _generate(tools: list[str], *, instructions: str | None = None):
    return MCPSkillGenerator()._create_skill_metadata(
        "cluster", [_tool(name) for name in tools], user_description="Cluster tools", instructions=instructions
    )


class TestInlineFunctions:
    def test_every_function_is_listed_under_the_name_the_model_imports(self) -> None:
        tools = ["mcp__cluster__get-items", "plain_tool", "foo bar", "foo_bar"]

        meta = _generate(tools)

        assert meta.mcp is not None
        assert len(meta.mcp.inline_functions) == len(tools) == len(set(meta.mcp.inline_functions))
        assert meta.mcp.inline_functions[:2] == ["get_items", "plain_tool"]
        assert [resolve_mcp_tool_name(name, tools) for name in meta.mcp.inline_functions] == tools

    def test_a_server_that_ships_instructions_keeps_the_select_first_path(self) -> None:
        meta = _generate(["list_pods"], instructions="Always pass a namespace; never delete in prod.")

        assert meta.mcp is not None
        assert meta.mcp.inline_functions == []

    def test_blank_instructions_do_not_block_the_index(self) -> None:
        meta = _generate(["list_pods"], instructions="  \n ")

        assert meta.mcp is not None
        assert meta.mcp.inline_functions == ["list_pods"]


class TestOneCallingConvention:
    def test_the_skill_document_template_embeds_the_shared_convention(self) -> None:
        assert CALL_SYNTAX in SKILL_USAGE_TEMPLATE
        assert CALL_WORKFLOW in SKILL_USAGE_TEMPLATE

    def test_the_skill_document_names_the_skill_in_the_shared_import_rule(self) -> None:
        document = MCPSkillGenerator().generate_skill_content(_generate(["list_pods"]))

        for line in CALL_SYNTAX.format(skill_name="mcp_cluster_skill").splitlines():
            assert line in document
        for line in CALL_WORKFLOW.splitlines():
            assert line in document
