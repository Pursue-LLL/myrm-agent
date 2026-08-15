"""Tests for MCPBridgeProvider._inject_since_cursor with dict args_schema.

Harness MCP tools carry a native JSON Schema ``dict`` as ``args_schema``
(see tool_converter); the bridge must read ``properties`` from the dict
instead of assuming a Pydantic model, otherwise incremental-sync cursors
are silently dropped for every MCP-backed integration.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.memory.imports.mcp_bridge_provider import MCPBridgeProvider


def _tool(name: str, args_schema: object) -> SimpleNamespace:
    return SimpleNamespace(name=name, args_schema=args_schema)


def _provider(server_tools: list[SimpleNamespace]) -> MCPBridgeProvider:
    connection = SimpleNamespace(
        tools_by_server={"gdrive": server_tools},
    )
    provider = MCPBridgeProvider(
        server_name="gdrive",
        connection=connection,  # type: ignore[arg-type]
        fetch_tool_name="search",
    )
    return provider


def test_inject_since_cursor_with_dict_schema() -> None:
    """dict args_schema (harness MCP tools) must inject the cursor."""
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "updated_since": {"type": "string"},
        },
    }
    provider = _provider([_tool("search", schema)])
    params: dict[str, object] = {}
    provider._inject_since_cursor(params, "2026-08-01T00:00:00Z")
    assert params == {"updated_since": "2026-08-01T00:00:00Z"}


def test_inject_since_cursor_skips_missing_param_dict() -> None:
    """No time-filter param in a dict schema → full-fetch fallback (no injection)."""
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
    }
    provider = _provider([_tool("search", schema)])
    params: dict[str, object] = {}
    provider._inject_since_cursor(params, "2026-08-01T00:00:00Z")
    assert params == {}


def test_inject_since_cursor_with_pydantic_model_schema() -> None:
    """Legacy Pydantic-model args_schema path keeps working."""

    class _Model:
        model_fields = {"query": object, "after": object}

    provider = _provider([_tool("search", _Model())])
    params: dict[str, object] = {}
    provider._inject_since_cursor(params, "cursor-1")
    assert params == {"after": "cursor-1"}
