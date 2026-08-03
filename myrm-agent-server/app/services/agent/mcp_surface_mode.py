"""Normalize MCP surface mode from agent profile engine_params."""

from __future__ import annotations


def normalize_mcp_surface_engine_params(
    engine_params: dict[str, object] | None,
) -> tuple[str, dict[str, object] | None]:
    """Return canonical surface mode and engine_params with obsolete values removed."""
    from myrm_agent_harness.agent._factory.mcp_surface import parse_mcp_surface_mode

    if engine_params is None:
        return "auto", None

    params = dict(engine_params)
    raw_mode = params.get("mcp_surface_mode")
    mode = parse_mcp_surface_mode(str(raw_mode) if raw_mode is not None else None)
    params["mcp_surface_mode"] = mode.value
    return mode.value, params
