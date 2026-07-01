"""Integration smoke: conftest wiring → tests.support.browser_process_cleanup."""

from __future__ import annotations

import ast
from pathlib import Path


def test_server_conftest_cleanup_hook_runs() -> None:
    from tests.conftest import _cleanup_browser_child_processes

    _cleanup_browser_child_processes()


def test_server_cleanup_markers_match_harness_mirror() -> None:
    server_path = Path(__file__).resolve().parent / "browser_process_cleanup.py"
    harness_path = (
        Path(__file__).resolve().parents[4]
        / "myrm-agent-harness"
        / "tests"
        / "support"
        / "browser_process_cleanup.py"
    )
    assert harness_path.is_file(), f"Missing harness mirror: {harness_path}"

    assert _automation_markers_from_file(server_path) == _automation_markers_from_file(harness_path)


def _automation_markers_from_file(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "_AUTOMATION_CMD_MARKERS" and node.value is not None:
                value = ast.literal_eval(node.value)
                if isinstance(value, tuple):
                    return tuple(str(item) for item in value)
    raise AssertionError(f"_AUTOMATION_CMD_MARKERS not found in {path}")
