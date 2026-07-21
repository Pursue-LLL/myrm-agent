"""Tests for app.services.agent.params.mcp_selection."""

from __future__ import annotations

from app.core.types import MCPServerConfig
from app.services.agent.params.mcp_selection import (
    apply_agent_mcp_selection,
    coerce_tool_selections,
)


def _cfg(name: str, **kwargs: object) -> MCPServerConfig:
    return MCPServerConfig(name=name, type="stdio", command="echo", **kwargs)


# ── coerce_tool_selections ─────────────────────────────────────────


class TestCoerceToolSelections:
    def test_none_returns_none(self) -> None:
        assert coerce_tool_selections(None) is None

    def test_non_dict_returns_none(self) -> None:
        assert coerce_tool_selections("invalid") is None
        assert coerce_tool_selections(42) is None
        assert coerce_tool_selections([]) is None

    def test_empty_dict_returns_none(self) -> None:
        assert coerce_tool_selections({}) is None

    def test_list_values(self) -> None:
        result = coerce_tool_selections({"srv": ["t1", "t2"]})
        assert result == {"srv": ("t1", "t2")}

    def test_tuple_values(self) -> None:
        result = coerce_tool_selections({"srv": ("t1",)})
        assert result == {"srv": ("t1",)}

    def test_string_scalar(self) -> None:
        result = coerce_tool_selections({"srv": "single_tool"})
        assert result == {"srv": ("single_tool",)}

    def test_filters_non_string_items(self) -> None:
        result = coerce_tool_selections({"srv": ["t1", 42, None, "t2"]})
        assert result == {"srv": ("t1", "t2")}

    def test_skips_empty_tool_list(self) -> None:
        result = coerce_tool_selections({"empty": [], "valid": ["t1"]})
        assert result == {"valid": ("t1",)}

    def test_all_empty_returns_none(self) -> None:
        assert coerce_tool_selections({"a": [], "b": []}) is None

    def test_skips_non_coercible_values(self) -> None:
        result = coerce_tool_selections({"a": 123, "b": ["ok"]})
        assert result == {"b": ("ok",)}


# ── apply_agent_mcp_selection ──────────────────────────────────────


class TestApplyAgentMcpSelection:
    def test_empty_configs_returns_empty(self) -> None:
        assert apply_agent_mcp_selection([], None, None) == []

    def test_no_filters_returns_all(self) -> None:
        cfgs = [_cfg("a"), _cfg("b")]
        result = apply_agent_mcp_selection(cfgs, None, None)
        assert len(result) == 2
        assert [c.name for c in result] == ["a", "b"]

    def test_server_level_filtering(self) -> None:
        cfgs = [_cfg("a"), _cfg("b"), _cfg("c")]
        result = apply_agent_mcp_selection(cfgs, mcp_ids=("a", "c"), mcp_tool_selections=None)
        assert [c.name for c in result] == ["a", "c"]

    def test_tool_level_filtering(self) -> None:
        cfgs = [_cfg("srv1"), _cfg("srv2")]
        result = apply_agent_mcp_selection(
            cfgs,
            mcp_ids=None,
            mcp_tool_selections={"srv1": ("tool_a",)},
        )
        assert len(result) == 2
        assert result[0].tool_include == ["tool_a"]
        assert result[1].tool_include is None

    def test_tool_level_filtering_preserves_host_serial(self) -> None:
        cfgs = [_cfg("stateful", host_serial=True)]
        result = apply_agent_mcp_selection(
            cfgs,
            mcp_ids=None,
            mcp_tool_selections={"stateful": ("tool_a",)},
        )
        assert len(result) == 1
        assert result[0].tool_include == ["tool_a"]
        assert result[0].host_serial is True

    def test_combined_server_and_tool_filtering(self) -> None:
        cfgs = [_cfg("a"), _cfg("b"), _cfg("c")]
        result = apply_agent_mcp_selection(
            cfgs,
            mcp_ids=("a", "b"),
            mcp_tool_selections={"a": ("t1", "t2")},
        )
        assert len(result) == 2
        assert result[0].name == "a"
        assert result[0].tool_include == ["t1", "t2"]
        assert result[1].name == "b"
        assert result[1].tool_include is None

    def test_does_not_mutate_original(self) -> None:
        original = _cfg("srv")
        cfgs = [original]
        result = apply_agent_mcp_selection(
            cfgs,
            mcp_ids=None,
            mcp_tool_selections={"srv": ("t1",)},
        )
        assert original.tool_include is None
        assert result[0].tool_include == ["t1"]

    def test_empty_mcp_ids_tuple_acts_as_no_filter(self) -> None:
        cfgs = [_cfg("a"), _cfg("b")]
        result = apply_agent_mcp_selection(cfgs, mcp_ids=(), mcp_tool_selections=None)
        assert len(result) == 2

    def test_server_not_in_mcp_ids_excluded(self) -> None:
        cfgs = [_cfg("x")]
        result = apply_agent_mcp_selection(cfgs, mcp_ids=("y",), mcp_tool_selections=None)
        assert result == []

    def test_tool_selection_for_missing_server_ignored(self) -> None:
        cfgs = [_cfg("a")]
        result = apply_agent_mcp_selection(
            cfgs,
            mcp_ids=None,
            mcp_tool_selections={"nonexistent": ("t1",)},
        )
        assert len(result) == 1
        assert result[0].tool_include is None

    def test_empty_tool_selections_dict_no_op(self) -> None:
        cfgs = [_cfg("a")]
        result = apply_agent_mcp_selection(cfgs, mcp_ids=None, mcp_tool_selections={})
        assert len(result) == 1
        assert result[0].tool_include is None
