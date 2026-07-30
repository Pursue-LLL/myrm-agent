"""Tests for local persistent root wiring."""

from __future__ import annotations

from pathlib import Path

import myrm_agent_harness.runtime.context.context_branches as branches_module
import myrm_agent_harness.runtime.context.session_context_pins as pins_module
import myrm_agent_harness.runtime.execution_paths as execution_paths
import pytest

from app.platform_utils.persistent_root import configure_persistent_root_for_local_dev


def test_configure_persistent_root_for_local_dev_uses_state_harness(
    tmp_path: pytest.TempPathFactory,
) -> None:
    if Path("/persistent").is_dir():
        pytest.skip("/persistent mounted — local dev mapping not exercised")

    root = configure_persistent_root_for_local_dev(str(tmp_path))
    expected = str(Path(tmp_path) / "harness")
    assert root == expected
    assert execution_paths.PERSISTENT_ROOT == expected
    assert pins_module.PERSISTENT_ROOT == expected
    assert branches_module.PERSISTENT_ROOT == expected
    assert Path(expected).is_dir()
