"""Unit tests for conditional skill market/manage mount in build_general_agent."""

from __future__ import annotations

import ast
from pathlib import Path


def _factory_source() -> str:
    factory_path = (
        Path(__file__).resolve().parents[3] / "app" / "ai_agents" / "general_agent" / "factory.py"
    )
    return factory_path.read_text(encoding="utf-8")


def test_build_general_agent_gates_skill_market_on_enable_flag() -> None:
    """market_backend must be None unless enable_skill_market is true."""
    source = _factory_source()
    assert 'mount_skill_market = getattr(agent_wrapper, "enable_skill_market", False)' in source
    assert "market_backend=market_service if mount_skill_market else None" in source


def test_build_general_agent_gates_skill_manage_on_evolution_or_learn() -> None:
    """write_backend must be None unless evolution is on or /learn forces manage."""
    source = _factory_source()
    assert 'mount_skill_manage = getattr(agent_wrapper, "enable_skill_manage", False) or getattr(' in source
    assert "write_backend=skill_creation_service if mount_skill_manage else None" in source


def test_build_general_agent_defaults_skill_mount_flags_off() -> None:
    """Default getattr fallbacks must keep both mounts off when flags are absent."""
    source = _factory_source()
    tree = ast.parse(source)
    mount_market_assign = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "mount_skill_market"
            for target in node.targets
        )
    )
    mount_expr = ast.unparse(mount_market_assign.value)
    assert "enable_skill_market" in mount_expr
    assert "False" in mount_expr
