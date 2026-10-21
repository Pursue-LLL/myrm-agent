"""Tests for local persistent root wiring."""

from __future__ import annotations

import os
from pathlib import Path

import myrm_agent_harness.runtime.context.context_branches as branches_module
import myrm_agent_harness.runtime.context.session.session_context_pins as pins_module
import pytest
from myrm_agent_harness.runtime.paths.execution_paths import PERSISTENT_ROOT_ENV, get_persistent_root

from app.platform_utils.persistent_root import configure_persistent_root_for_local_dev


@pytest.fixture
def unset_persistent_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start without a configured root; the monkeypatch undoes whatever the shim sets."""
    monkeypatch.setenv(PERSISTENT_ROOT_ENV, "placeholder")
    monkeypatch.delenv(PERSISTENT_ROOT_ENV)


@pytest.mark.usefixtures("unset_persistent_root")
def test_configure_persistent_root_for_local_dev_uses_state_harness(tmp_path: Path) -> None:
    if Path("/persistent").is_dir():
        pytest.skip("/persistent mounted — local dev mapping not exercised")

    root = configure_persistent_root_for_local_dev(str(tmp_path))
    expected = str(tmp_path / "harness")

    assert root == expected
    assert os.environ[PERSISTENT_ROOT_ENV] == expected
    assert get_persistent_root() == expected
    assert pins_module._pin_path("chat-1") == Path(expected) / ".context" / "chat-1" / "pinned_context_files.json"
    assert branches_module._branch_path("chat-1") == Path(expected) / ".context" / "chat-1" / "branches.json"
    assert Path(expected).is_dir()


def test_configure_persistent_root_for_local_dev_keeps_a_root_the_deployment_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployed = tmp_path / "deployed"
    monkeypatch.setenv(PERSISTENT_ROOT_ENV, str(deployed))

    root = configure_persistent_root_for_local_dev(str(tmp_path / "state"))

    assert root == str(deployed)
    assert os.environ[PERSISTENT_ROOT_ENV] == str(deployed)
    assert not (tmp_path / "state" / "harness").exists()
