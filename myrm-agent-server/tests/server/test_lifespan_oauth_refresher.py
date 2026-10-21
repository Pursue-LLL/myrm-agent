"""Startup hands the subscription token freshener to the harness before the first request can reach a model.

Without it a model instance that outlives one access token (a long agent run, a cached agent) keeps sending the
expired token until the user reconnects.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable, Coroutine

from app.server import lifespan


def _single_name_calls(function: Callable[[], Coroutine[object, object, None]]) -> set[tuple[str, str]]:
    """(callee, argument) for every ``callee(argument)`` call whose callee and argument are plain names."""
    tree = ast.parse(inspect.getsource(function).lstrip())
    return {
        (node.func.id, node.args[0].id)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
    }


def test_startup_registers_the_subscription_token_freshener() -> None:
    assert ("set_api_key_refresher", "freshen_api_key") in _single_name_calls(lifespan._phase_1a_sequential)
