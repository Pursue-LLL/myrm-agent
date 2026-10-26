"""``get_workspace_root`` answers for the active run, and for the process only outside a run."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from myrm_agent_harness.core.context_vars import workspace_root_var

from app.platform_utils.workspace_root import get_workspace_root


@pytest.fixture(autouse=True)
def _unbound_run() -> Iterator[None]:
    token = workspace_root_var.set("")
    yield
    workspace_root_var.reset(token)


def test_outside_a_run_the_root_is_the_process_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert get_workspace_root() == tmp_path.resolve()


def test_inside_a_run_the_root_is_the_one_bound_to_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chat_ws = tmp_path / "chat_ws"
    chat_ws.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    workspace_root_var.set(str(chat_ws))

    assert get_workspace_root() == chat_ws
