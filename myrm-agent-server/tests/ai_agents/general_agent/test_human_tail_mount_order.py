"""Mount order of the Human-tail middlewares in build_general_agent.

[INPUT]
- app/ai_agents/general_agent/factory/ (POS: source under inspection)

[OUTPUT]
- Tests that the tail blocks are mounted after the context pipeline and that the knowledge pack precedes the session deltas.

[POS]
The order decides what the model reads last: compression must not see the tail blocks, and explicit session deltas
stay closest to the end of the user turn.
"""

from __future__ import annotations

import ast
from pathlib import Path

FACTORY_PATH = Path(__file__).resolve().parents[3] / "app" / "ai_agents" / "general_agent" / "factory" / "middlewares.py"
_TAIL_GROUP = ["proactive_pack_middleware", "ephemeral_delta_middleware", "two_layer_context_middleware"]


def _names_of(node: ast.List) -> list[str]:
    return [element.id for element in node.elts if isinstance(element, ast.Name)]


def _middleware_lists() -> tuple[list[str], list[list[str]]]:
    """The base `middlewares_list = [...]` literal and the lists later passed to `middlewares_list.extend`."""
    tree = ast.parse(FACTORY_PATH.read_text(encoding="utf-8"))
    base: list[str] = []
    extensions: list[list[str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "middlewares_list" for t in node.targets):
            if isinstance(node.value, ast.List):
                base = _names_of(node.value)
        elif isinstance(node, ast.Call) and ast.unparse(node.func) == "middlewares_list.extend":
            argument = node.args[0]
            if isinstance(argument, ast.List):
                extensions.append(_names_of(argument))
    return base, extensions


def test_the_tail_blocks_are_mounted_after_the_context_pipeline_in_a_fixed_order() -> None:
    base, extensions = _middleware_lists()

    assert "context_pipeline_middleware" in base
    assert not set(_TAIL_GROUP) & set(base)
    assert _TAIL_GROUP in extensions
