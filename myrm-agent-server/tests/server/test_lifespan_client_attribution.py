"""Startup announces the application to model gateways before the first request can build a model.

The call has to sit directly in the phase body: inside a ``try`` that logs and carries on, or behind a condition, a
failure or a skipped branch would leave every request unattributed with nothing to show for it.
"""

from __future__ import annotations

import ast
import inspect

from app.server import lifespan


def _top_level_calls(function_source: str) -> set[tuple[str, str]]:
    """(callee, argument) for each statement of the function body that is a bare ``callee(argument)`` of two names."""
    function = ast.parse(function_source).body[0]
    assert isinstance(function, ast.AsyncFunctionDef)
    return {
        (statement.value.func.id, statement.value.args[0].id)
        for statement in function.body
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and len(statement.value.args) == 1
        and isinstance(statement.value.args[0], ast.Name)
    }


def test_startup_registers_the_client_attribution_unconditionally() -> None:
    source = inspect.getsource(lifespan._phase_1a_sequential).lstrip()
    assert ("set_client_attribution", "CLIENT_ATTRIBUTION") in _top_level_calls(source)
