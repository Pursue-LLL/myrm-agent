"""MCP surface mode normalization for server agent specs."""

from __future__ import annotations

from app.services.agent.mcp_surface_mode import normalize_mcp_surface_engine_params


def test_normalize_catalog_invoke_to_auto() -> None:
    mode, params = normalize_mcp_surface_engine_params({"mcp_surface_mode": "catalog_invoke", "timeout_seconds": 120})

    assert mode == "auto"
    assert params == {"mcp_surface_mode": "auto", "timeout_seconds": 120}


def test_normalize_missing_engine_params() -> None:
    mode, params = normalize_mcp_surface_engine_params(None)

    assert mode == "auto"
    assert params is None


def test_normalize_direct_fc_preserved() -> None:
    mode, params = normalize_mcp_surface_engine_params({"mcp_surface_mode": "direct_fc"})

    assert mode == "direct_fc"
    assert params == {"mcp_surface_mode": "direct_fc"}
