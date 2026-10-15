"""Tests for local persistent root wiring."""

from __future__ import annotations

from pathlib import Path

import myrm_agent_harness.runtime.context.context_branches as branches_module
import myrm_agent_harness.runtime.context.session.session_context_pins as pins_module
import myrm_agent_harness.runtime.paths.execution_paths as execution_paths
import pytest

from app.platform_utils.persistent_root import configure_persistent_root_for_local_dev

_REBOUND_CONSTANTS = (
    "PERSISTENT_ROOT",
    "WORKSPACE_ROOT",
    "CONTEXT_ROOT",
    "ARTIFACTS_ROOT",
    "MEMORIES_ROOT",
    "SYSTEM_CONFIG_ROOT",
    "LEGACY_SYSTEM_CONFIG_ROOT",
)


def test_configure_persistent_root_for_local_dev_uses_state_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if Path("/persistent").is_dir():
        pytest.skip("/persistent mounted — local dev mapping not exercised")

    # Registers each constant so the rebinding below is undone after the test.
    for name in _REBOUND_CONSTANTS:
        monkeypatch.setattr(execution_paths, name, getattr(execution_paths, name))

    root = configure_persistent_root_for_local_dev(str(tmp_path))
    expected = str(tmp_path / "harness")
    assert root == expected
    assert execution_paths.PERSISTENT_ROOT == expected
    assert pins_module._pin_path("chat-1") == Path(expected) / ".context" / "chat-1" / "pinned_context_files.json"
    assert branches_module._branch_path("chat-1") == Path(expected) / ".context" / "chat-1" / "branches.json"
    assert Path(expected).is_dir()
