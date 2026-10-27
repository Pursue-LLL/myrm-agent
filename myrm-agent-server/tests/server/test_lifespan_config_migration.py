"""Startup seals the secrets saved before their config key was encrypted, together with the history that repeats them.

The history migration is the only thing that removes the plaintext copies the audit log kept of such a secret; if the
startup stops calling it, an installation that was fixed keeps those copies until every config is saved again by hand.
A sandbox seals new writes with the key its control plane provides, so it needs the same sweep for the rows saved earlier.

[INPUT]
app.server.lifespan::_phase_1a_sequential (POS: the startup phase that runs the config sweep)

[OUTPUT]
That the startup phase runs ``seal_stored_configs`` whatever the deploy mode, and that a failing sweep never blocks it.

[POS]
Reads the startup function's source, like the other lifespan tests: running it would start the whole server. What the
sweep seals is covered in ``services/config/test_seal_stored_configs.py``.
"""

from __future__ import annotations

import ast
import inspect

from app.server import lifespan


def _sweep_ancestors() -> list[ast.AST]:
    """The statements that enclose the one ``await seal_stored_configs()`` of the startup phase, innermost first."""
    tree = ast.parse(inspect.getsource(lifespan._phase_1a_sequential).lstrip())
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    sweeps = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Await)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "seal_stored_configs"
    ]
    assert len(sweeps) == 1, "the startup phase must run the config sweep exactly once"
    ancestors: list[ast.AST] = []
    node: ast.AST = sweeps[0]
    while node in parents:
        node = parents[node]
        ancestors.append(node)
    return ancestors


def test_the_sweep_runs_in_every_deploy_mode() -> None:
    assert not [node for node in _sweep_ancestors() if isinstance(node, ast.If)]


def test_a_failing_sweep_is_logged_and_never_blocks_startup() -> None:
    guards = [
        node
        for node in _sweep_ancestors()
        if isinstance(node, ast.Try)
        and any(isinstance(h.type, ast.Name) and h.type.id == "Exception" for h in node.handlers)
        and not any(isinstance(inner, ast.Raise) for h in node.handlers for inner in ast.walk(h))
    ]

    assert guards
