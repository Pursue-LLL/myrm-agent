"""Default Agent must not bind control-plane orchestration signals, and the completion guard registers no tool.

Control-plane names live under ``agent/orchestration/`` and are excluded from
``_TOOL_LAYERS``. They must not inflate Turn-1 ``bind_tools`` (Prefix Cache protection).
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.orchestration.signals.catalog import (
    ORCHESTRATION_SIGNAL_NAMES,
)
from myrm_agent_harness.agent.tool_management.tool_layers import _TOOL_LAYERS

CONTROL_PLANE_TOOL_NAMES: frozenset[str] = frozenset(ORCHESTRATION_SIGNAL_NAMES)

SCHEMA_ONLY_CONTROL_PLANE_TOOL_NAMES: frozenset[str] = frozenset(
    name for name in ORCHESTRATION_SIGNAL_NAMES if name != "submit_verdict"
)

PTC_RUNTIME_TOOL_NAMES: frozenset[str] = frozenset({"spawn_subagent", "notify", "llm_query", "llm_query_batched"})


@pytest.mark.asyncio
async def test_default_resolve_excludes_internal_pseudo_tools() -> None:
    """Default build_tools: control-plane names stay out of resolve()."""
    from myrm_agent_harness.agent._internals._agent_build import (
        build_middlewares,
        build_tools,
        create_registry,
    )

    registry = create_registry()
    middlewares = build_middlewares(registry, [])

    resolved = await build_tools(registry, [], middlewares)
    resolved_names = {tool.name for tool in resolved}

    overlap = resolved_names & CONTROL_PLANE_TOOL_NAMES
    assert not overlap, f"Control-plane tools leaked into default bind_tools: {sorted(overlap)}"


@pytest.mark.asyncio
async def test_the_default_chain_registers_no_runtime_only_tool() -> None:
    """The completion guard speaks to the model through the request, not through a tool call."""
    from myrm_agent_harness.agent._internals._agent_build import (
        build_middlewares,
        build_tools,
        create_registry,
    )

    registry = create_registry()
    middlewares = build_middlewares(registry, [])

    await build_tools(registry, [], middlewares)

    assert registry.get_runtime_tools() == []
    assert not registry.has_tool("_completion_check")


@pytest.mark.asyncio
async def test_schema_only_tools_not_registered_in_default_build() -> None:
    """DR signal schemas are not registered unless their subsystems run."""
    from myrm_agent_harness.agent._internals._agent_build import (
        build_middlewares,
        build_tools,
        create_registry,
    )

    registry = create_registry()
    middlewares = build_middlewares(registry, [])

    await build_tools(registry, [], middlewares)

    for name in SCHEMA_ONLY_CONTROL_PLANE_TOOL_NAMES:
        assert not registry.has_tool(name), f"{name} must not be in default registry"


def test_ptc_runtime_tools_not_in_tool_layers_registry() -> None:
    """DW PTC bridge tools are runtime-only; must not inflate _TOOL_LAYERS."""
    overlap = set(_TOOL_LAYERS) & PTC_RUNTIME_TOOL_NAMES
    assert not overlap, f"PTC runtime tools must not be in _TOOL_LAYERS: {sorted(overlap)}"


def test_control_plane_not_in_tool_layers_registry() -> None:
    """Orchestration signals must not appear in _TOOL_LAYERS."""
    overlap = set(_TOOL_LAYERS) & CONTROL_PLANE_TOOL_NAMES
    assert not overlap, f"Control-plane names must not be in _TOOL_LAYERS: {sorted(overlap)}"
