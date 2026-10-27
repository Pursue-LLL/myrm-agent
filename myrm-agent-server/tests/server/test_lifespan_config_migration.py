"""Startup seals the secrets saved before their config key was encrypted, together with the history that repeats them.

The history migration is the only thing that removes the plaintext copies the audit log kept of such a secret; if the
startup stops calling it, an installation that was fixed keeps those copies until every config is saved again by hand.

[INPUT]
app.server.lifespan::_phase_1a_sequential (POS: the startup phase that runs the local-mode config migrations)

[OUTPUT]
That the startup phase awaits both the config migration and the config history migration.

[POS]
Reads the startup function's source, like the other lifespan tests: running it would start the whole server.
"""

from __future__ import annotations

import ast
import inspect

from app.server import lifespan


def _awaited_names() -> set[str]:
    tree = ast.parse(inspect.getsource(lifespan._phase_1a_sequential).lstrip())
    return {
        node.value.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
    }


def test_startup_seals_secret_configs_and_the_history_that_repeats_them() -> None:
    awaited = _awaited_names()

    assert "migrate_configs_to_encrypted" in awaited
    assert "migrate_config_history_to_encrypted" in awaited
