"""Startup hands the expired-image sweep of the channel image cache to the maintenance daemon.

The daily cleanup job runs at 03:00 only while the server is up, so a machine that is off at that hour keeps its cache
forever unless the sweep also runs when the server starts. The daemon takes it off the startup path.

[INPUT]
app.server.lifespan::optimized_lifespan (POS: the startup function that submits the sweep)

[OUTPUT]
That startup submits ``sweep_channel_image_cache_at_startup`` exactly once, after the daemon's worker has been started.

[POS]
Reads the startup function's source, like the other lifespan tests: running it would start the whole server. What the
sweep removes is covered in ``channels/media/test_channel_image_retention.py``.
"""

from __future__ import annotations

import ast
import inspect

from app.server import lifespan


def _calls_on_daemon(method: str) -> list[ast.Call]:
    tree = ast.parse(inspect.getsource(lifespan.optimized_lifespan).lstrip())
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "maintenance_daemon"
    ]


def test_startup_submits_the_channel_image_sweep_once() -> None:
    submitted = [
        call.args[0].id
        for call in _calls_on_daemon("submit")
        if call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "sweep_channel_image_cache_at_startup"
    ]

    assert submitted == ["sweep_channel_image_cache_at_startup"]


def test_the_sweep_is_submitted_after_the_daemon_worker_has_started() -> None:
    [start] = _calls_on_daemon("start")
    submits = [
        call
        for call in _calls_on_daemon("submit")
        if call.args and getattr(call.args[0], "id", "") == "sweep_channel_image_cache_at_startup"
    ]

    assert submits
    assert all(call.lineno > start.lineno for call in submits)
