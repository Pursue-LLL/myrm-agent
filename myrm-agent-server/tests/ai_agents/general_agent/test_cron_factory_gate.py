"""Unit tests for cron tool load gate in build_general_agent."""

from __future__ import annotations

import ast
from pathlib import Path


def test_build_general_agent_gates_cron_setup_on_entitlement() -> None:
    """Verify factory source gates _setup_cron_tools behind _should_enable_cron_tools()."""
    factory_path = Path(__file__).resolve().parents[3] / "app" / "ai_agents" / "general_agent" / "factory.py"
    source = factory_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found_if = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = ast.unparse(node.test)
        if "_should_enable_cron_tools()" not in test:
            continue
        body = ast.unparse(node)
        if "_setup_cron_tools" in body:
            found_if = True
            break

    assert found_if, "expected `if _should_enable_cron_tools(): await _setup_cron_tools(...)` in factory.py"
