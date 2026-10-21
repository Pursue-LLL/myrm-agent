"""Parallel snapshot batch_mode detection."""

from __future__ import annotations

from tests.support.e2e_parallel_snapshot import (  # noqa: E402
    _is_batch_file_invocation,
)


def test_batch_mode_detects_whole_file_marker_run() -> None:
    test_id = "tests/e2e/test_mcp_reload_confirm_chrome_e2e.py -m chrome_e2e"
    assert _is_batch_file_invocation(test_id) is True


def test_batch_mode_false_for_nodeid() -> None:
    test_id = "tests/e2e/test_mcp_reload_confirm_chrome_e2e.py::test_foo"
    assert _is_batch_file_invocation(test_id) is False
