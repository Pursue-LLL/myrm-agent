"""Normalize MCP surface mode from agent profile engine_params.

[INPUT]
- engine_params dict from agent profile

[OUTPUT]
- (canonical_mode, cleaned_engine_params) tuple

[POS]
Thin adapter that canonicalizes MCP surface mode without importing harness internals.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_VALID_MODES = {"auto", "direct_fc"}
_OBSOLETE_ALIASES = {"catalog_invoke", "catalog-invoke"}


def _parse_surface_mode(raw: str | None) -> str:
    """Parse surface mode string to canonical value with safe default."""
    if not raw:
        return "auto"
    normalized = str(raw).strip().lower()
    if normalized in _OBSOLETE_ALIASES:
        logger.warning(
            "mcp_surface_mode=%r is obsolete; using auto (direct vs MCP→Skill only)",
            raw,
        )
        return "auto"
    return normalized if normalized in _VALID_MODES else "auto"


def normalize_mcp_surface_engine_params(
    engine_params: dict[str, object] | None,
) -> tuple[str, dict[str, object] | None]:
    """Return canonical surface mode and engine_params with obsolete values removed."""
    if engine_params is None:
        return "auto", None

    params = dict(engine_params)
    raw_mode = params.get("mcp_surface_mode")
    mode = _parse_surface_mode(str(raw_mode) if raw_mode is not None else None)
    params["mcp_surface_mode"] = mode
    return mode, params
