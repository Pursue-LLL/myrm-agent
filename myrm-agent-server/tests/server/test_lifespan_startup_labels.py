"""Every parallel startup task has exactly one log label.

The labels are zipped with the gathered results in strict mode, so a task added or removed on one side only
turns into a ValueError that aborts server startup.
"""

from __future__ import annotations

import ast
import inspect

from app.server import lifespan


def _count_parallel_tasks_and_labels() -> tuple[int, int]:
    tree = ast.parse(inspect.getsource(lifespan))
    tasks = labels = -1
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name, value = node.targets[0].id, node.value
        if name == "_labels" and isinstance(value, ast.List):
            labels = len(value.elts)
        elif name == "results" and isinstance(value, ast.Await) and isinstance(value.value, ast.Call):
            tasks = len(value.value.args)
    return tasks, labels


def test_parallel_startup_tasks_and_labels_line_up() -> None:
    tasks, labels = _count_parallel_tasks_and_labels()
    assert tasks > 0
    assert tasks == labels
