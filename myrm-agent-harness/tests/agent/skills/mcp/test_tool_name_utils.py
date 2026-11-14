"""Tests for MCP tool name resolution SSOT."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.skills.mcp.tool_name_utils import (
    build_tool_name_map,
    mcp_tool_short_name,
    resolve_mcp_tool_name,
    suggest_mcp_tool_names,
    to_python_identifier,
)


class TestMcpToolShortName:
    def test_strips_server_prefix(self) -> None:
        assert mcp_tool_short_name("mcp__12306__get_current_date") == "get_current_date"

    def test_passthrough_non_prefixed(self) -> None:
        assert mcp_tool_short_name("create_issue") == "create_issue"

    def test_keeps_double_underscore_inside_raw_name(self) -> None:
        # Only the mcp__<server>__ prefix is stripped; the raw name may contain "__".
        assert mcp_tool_short_name("mcp__srv__foo__bar") == "foo__bar"


class TestPythonIdentifiers:
    def test_folds_invalid_characters(self) -> None:
        assert to_python_identifier("foo.bar") == "foo_bar"
        assert to_python_identifier("foo bar") == "foo_bar"
        assert to_python_identifier("foo-bar") == "foo_bar"

    def test_prefixes_leading_digit(self) -> None:
        assert to_python_identifier("1foo") == "_1foo"

    def test_empty_name(self) -> None:
        assert to_python_identifier("...") == "unnamed"
        assert to_python_identifier("") == "unnamed"

    def test_every_mapped_name_compiles(self) -> None:
        tools = ["mcp__srv__foo.bar", "mcp__srv__foo bar", "mcp__srv__1foo", "mcp__srv__foo__bar", "mcp__srv__bar"]
        mapping = build_tool_name_map(tools)
        assert len(set(mapping.values())) == len(tools)
        for python_name in mapping.values():
            compile(f"from skills.x import {python_name}", "<t>", "exec")

    def test_collision_gets_deterministic_suffix(self) -> None:
        # A hyphen/underscore pair folds to the same identifier, so the loser takes _2.
        tools = ["mcp__srv__foo-bar", "mcp__srv__foo_bar"]
        mapping = build_tool_name_map(tools)
        assert sorted(mapping.values()) == ["foo_bar", "foo_bar_2"]
        assert mapping == build_tool_name_map(tools)

    def test_double_underscore_stays_distinct(self) -> None:
        # foo__bar must not collapse into bar; it is a different upstream tool.
        mapping = build_tool_name_map(["mcp__srv__foo__bar", "mcp__srv__bar"])
        assert sorted(mapping.values()) == ["bar", "foo__bar"]

    def test_preserves_unicode_letters(self) -> None:
        assert to_python_identifier("中文工具") == "中文工具"
        assert to_python_identifier("中文-工具") == "中文_工具"
        assert to_python_identifier("中文 工具") == "中文_工具"
        assert "中文工具".isidentifier()

    def test_unicode_names_compile_and_resolve(self) -> None:
        tools = ["mcp__srv__中文工具", "mcp__srv__中文-工具", "mcp__srv__中文工具2"]
        mapping = build_tool_name_map(tools)
        assert sorted(mapping.values()) == ["中文_工具", "中文工具", "中文工具2"]
        for canonical, python_name in mapping.items():
            compile(f"from skills.x import {python_name}", "<t>", "exec")
            assert resolve_mcp_tool_name(python_name, tools) == canonical

    def test_python_keywords_are_prefixed(self) -> None:
        keywords = ("class", "def", "import", "from", "lambda", "None", "True", "False", "async", "await")
        tools = [f"mcp__srv__{name}" for name in keywords]
        mapping = build_tool_name_map(tools)
        for canonical, python_name in mapping.items():
            assert python_name.startswith("_"), (canonical, python_name)
            compile(f"from skills.x import {python_name}", "<t>", "exec")
            assert resolve_mcp_tool_name(python_name, tools) == canonical

    def test_generated_names_do_not_shadow_canonical_names(self) -> None:
        # The model imports `foo_bar_2` for `foo bar`; exact `foo_bar` must stay
        # the unrelated canonical tool, not the generated alias.
        tools = ["foo.bar", "foo_bar", "foo bar"]
        mapping = build_tool_name_map(tools)
        assert mapping["foo_bar"] == "foo_bar"
        for canonical, python_name in mapping.items():
            compile(f"from skills.x import {python_name}", "<t>", "exec")
            assert resolve_mcp_tool_name(python_name, tools) == canonical

        for tools in (["None", "_None"], ["1foo", "_1foo"]):
            mapping = build_tool_name_map(tools)
            for canonical, python_name in mapping.items():
                compile(f"from skills.x import {python_name}", "<t>", "exec")
                assert resolve_mcp_tool_name(python_name, tools) == canonical


class TestResolveMcpToolName:
    def test_exact_match(self) -> None:
        assert resolve_mcp_tool_name("create_issue", ["create_issue", "list_prs"]) == "create_issue"

    def test_hyphen_to_underscore(self) -> None:
        assert resolve_mcp_tool_name("create-issue", ["create_issue"]) == "create_issue"

    def test_underscore_to_hyphen(self) -> None:
        assert resolve_mcp_tool_name("create_issue", ["create-issue"]) == "create-issue"

    def test_server_prefix_strip(self) -> None:
        assert resolve_mcp_tool_name("github:create_issue", ["create_issue"]) == "create_issue"

    def test_mcp_double_underscore_suffix_match(self) -> None:
        tools = ["mcp__12306__get_current_date", "mcp__12306__get_tickets"]
        assert resolve_mcp_tool_name("get_current_date", tools) == "mcp__12306__get_current_date"
        assert resolve_mcp_tool_name("get-current-date", tools) == "mcp__12306__get_current_date"

    def test_cross_server_collision_stays_callable(self) -> None:
        # Two servers exposing "search" get distinct python names; both resolve back.
        tools = ["mcp__a__search", "mcp__b__search"]
        assert resolve_mcp_tool_name("search", tools) == "mcp__a__search"
        assert resolve_mcp_tool_name("search_2", tools) == "mcp__b__search"

    def test_no_match(self) -> None:
        assert resolve_mcp_tool_name("missing", ["create_issue"]) is None


class TestRuntimeProxyNameRoundTrip:
    """The identifier L2 prints is the one the generated runtime proxy hands to the resolver."""

    def test_generated_skill_function_passes_the_python_name_through(self, monkeypatch) -> None:
        import asyncio
        import sys
        import types

        from myrm_agent_harness.agent.skills.mcp import client_templates

        calls: list[tuple[str, str]] = []

        async def _fake_call(skill: str, tool: str, kwargs: dict[str, object]) -> str:
            calls.append((skill, tool))
            return "ok"

        namespace: dict[str, object] = {
            "_call": _fake_call,
            "asyncio": asyncio,
            "sys": sys,
            "types": types,
        }
        exec(client_templates._generate_module_system(), namespace)  # noqa: S102 - the generated runtime source
        skill_function = namespace["_SkillFunction"]
        assert asyncio.run(skill_function("mcp_x_skill", "get_ticket_2")(a="1")) == "ok"
        assert calls == [("mcp_x_skill", "get_ticket_2")]

        tools = ["mcp__srv__get-ticket", "mcp__srv__get_ticket"]
        assert resolve_mcp_tool_name("get_ticket_2", tools) == "mcp__srv__get_ticket"

    def test_positional_skill_call_is_rejected_with_actionable_error(self) -> None:
        import asyncio
        import sys
        import types

        from myrm_agent_harness.agent.skills.mcp import client_templates

        async def _fake_call(skill: str, tool: str, kwargs: dict[str, object]) -> str:
            return "ok"

        namespace: dict[str, object] = {
            "_call": _fake_call,
            "asyncio": asyncio,
            "sys": sys,
            "types": types,
        }
        exec(client_templates._generate_module_system(), namespace)  # noqa: S102 - the generated runtime source
        skill_function = namespace["_SkillFunction"]
        with pytest.raises(TypeError, match="keyword-only"):
            asyncio.run(skill_function("mcp_x_skill", "get_ticket")("positional"))


class TestRenderedL2Names:
    """Every identifier printed in L2 must resolve back to a canonical tool."""

    def test_each_rendered_function_name_resolves(self) -> None:
        from myrm_agent_harness.agent.skills.mcp.core_generator import mcp_skill_generator
        from myrm_agent_harness.backends.skills.types import SkillMetadata
        from myrm_agent_harness.backends.skills.types.types_requires import MCPSkillData

        tools = [
            "mcp__srv__foo.bar",
            "mcp__srv__foo-bar",
            "mcp__srv__1foo",
            "mcp__srv__foo__bar",
            "mcp__srv__class",
            "mcp__srv__中文工具",
        ]
        schemas = {
            tool: {"description": "Query.", "inputSchema": {"properties": {"a": {"type": "string"}}}} for tool in tools
        }
        meta = SkillMetadata(
            name="mcp_srv_skill",
            description="d",
            mcp=MCPSkillData(server="srv", tools=tools, config=[], skill_content=None, tool_schemas=schemas),
        )
        content = mcp_skill_generator.generate_skill_content(meta)
        rendered = [line[2 : line.index("(")] for line in content.splitlines() if line.startswith("- ") and "(" in line]
        assert len(rendered) == len(tools)
        for func_name in rendered:
            compile(f"from skills.x import {func_name}", "<t>", "exec")
            assert resolve_mcp_tool_name(func_name, tools) is not None, func_name


class TestSuggestMcpToolNames:
    """The nearest-name hint must surface a tool a plain "first five" listing would bury."""

    TOOLS = [f"decoy_tool_{i:02d}" for i in range(30)] + ["get_pod_logs", "list_pods", "restart_pod"]

    @pytest.mark.parametrize(
        ("wrong", "expected"),
        [
            ("get_pod_log", "get_pod_logs"),  # dropped a letter
            ("list_pod", "list_pods"),  # singular for plural
            ("getPodLogs", "get_pod_logs"),  # camelCase
            ("restart-pod", "restart_pod"),  # kebab separator
            ("mcp__k8s__list_podz", "list_pods"),  # server prefix + typo
        ],
    )
    def test_closest_name_is_first(self, wrong: str, expected: str) -> None:
        assert suggest_mcp_tool_names(wrong, self.TOOLS)[0] == expected

    def test_returns_callable_names_not_raw_mcp_names(self) -> None:
        tools = ["mcp__k8s__get-pod-logs", "mcp__k8s__list-pods"]

        assert suggest_mcp_tool_names("get_pod_log", tools, limit=1) == ["get_pod_logs"]

    def test_limit_and_small_catalog(self) -> None:
        assert len(suggest_mcp_tool_names("anything", self.TOOLS)) == 3
        assert len(suggest_mcp_tool_names("anything", self.TOOLS, limit=5)) == 5
        assert suggest_mcp_tool_names("anything", ["only_tool"]) == ["only_tool"]
        assert suggest_mcp_tool_names("anything", []) == []

    def test_case_is_ignored_but_original_spelling_is_returned(self) -> None:
        assert suggest_mcp_tool_names("GET_POD_LOGS_X", ["Get_Pod_Logs", "other"], limit=1) == ["Get_Pod_Logs"]
