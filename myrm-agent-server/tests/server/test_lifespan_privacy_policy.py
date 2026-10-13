"""Startup publishes the saved privacy policy before the first request can reach a model.

Without this call the harness' process-wide policy stays empty after every restart, and the model calls that have
no agent run (titles, summaries, memory extraction) go out unprotected until the user happens to re-save settings.
"""

from __future__ import annotations

import ast
import inspect

from app.server import lifespan


def _awaited_names(function: object) -> set[str]:
    tree = ast.parse(inspect.getsource(function).lstrip())  # type: ignore[arg-type]
    return {
        node.value.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
    }


def test_startup_applies_the_saved_privacy_policy() -> None:
    assert "apply_privacy_policy_from_db" in _awaited_names(lifespan._phase_1a_sequential)
