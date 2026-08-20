"""Unit tests for conditional skill market/manage mount in build_general_agent."""

from __future__ import annotations

import ast
from pathlib import Path


def _factory_source() -> str:
    factory_path = Path(__file__).resolve().parents[3] / "app" / "ai_agents" / "general_agent" / "factory.py"
    return factory_path.read_text(encoding="utf-8")


def _tool_setup_source() -> str:
    tool_setup_path = Path(__file__).resolve().parents[3] / "app" / "ai_agents" / "general_agent" / "tool_setup.py"
    return tool_setup_path.read_text(encoding="utf-8")


def test_build_general_agent_mounts_skill_market_via_tool_setup() -> None:
    """skill_market_tool must mount through ToolSetupMixin, not get_meta_tools backends."""
    factory_source = _factory_source()
    tool_setup_source = _tool_setup_source()
    assert "_setup_skill_market_tool(tools, market_service)" in factory_source
    assert "def _setup_skill_market_tool" in tool_setup_source
    assert "market_backend=None" in factory_source


def test_build_general_agent_mounts_skill_manage_via_tool_setup() -> None:
    """skill_manage_tool must mount through ToolSetupMixin when evolution or /learn forces it."""
    factory_source = _factory_source()
    tool_setup_source = _tool_setup_source()
    tree = ast.parse(factory_source)
    mount_manage_assign = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "mount_skill_manage" for target in node.targets)
    )
    mount_expr = ast.unparse(mount_manage_assign.value)
    assert "enable_skill_manage" in mount_expr
    assert "force_skill_manage" in mount_expr
    assert "_setup_skill_manage_tool(" in factory_source
    assert "def _setup_skill_manage_tool" in tool_setup_source
    assert "write_backend=None" in factory_source


def test_build_general_agent_defaults_skill_mount_flags_off() -> None:
    """Default getattr fallbacks must keep both mounts off when flags are absent."""
    source = _factory_source()
    tree = ast.parse(source)
    mount_market_assign = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "mount_skill_market" for target in node.targets)
    )
    mount_expr = ast.unparse(mount_market_assign.value)
    assert "enable_skill_market" in mount_expr
    assert "False" in mount_expr
