"""Healing a mistyped path never carries a read into a file the permission engine guards.

The engine judges the spelling the model typed; ``find_existing_unicode_path`` then probes other spellings of it. A
spelling that normalises into a credential file, a link to one, or a file in a forbidden directory would be opened
under a verdict that never saw it, so healing refuses it and the typed spelling is read as typed. Spellings of
ordinary files still heal, and a typed spelling that is guarded itself is not touched: the engine has asked about it.
"""

from __future__ import annotations

import os
import sys
import unicodedata
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.agent.meta_tools.file_search.path_hint import find_existing_unicode_path
from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver
from myrm_agent_harness.utils.errors import ToolError

CANARY = "ocean-blue-7"
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs privileges on Windows")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".env").write_text(CANARY)
    return root


@pytest.fixture
def home_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace that is the user's home: the forbidden ``.ssh`` directory lies inside it."""
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "config").write_text(CANARY)
    (home / ".ssh" / ".env").write_text(CANARY)
    monkeypatch.setattr(
        "myrm_agent_harness.core.security.path.filesystem.DANGEROUS_PATHS",
        frozenset({os.path.realpath(home / ".ssh")}),
    )
    return home


@pytest.mark.parametrize(
    "typed",
    [
        pytest.param('".env"', id="ascii-quotes"),
        pytest.param(" .env", id="leading-space"),
        pytest.param("\u2018.env\u2019", id="curly-quotes"),
        pytest.param("\uff0e\uff45\uff4e\uff56", id="fullwidth-name"),
    ],
)
def test_healing_does_not_turn_a_spelling_into_a_credential_file(workspace: Path, typed: str) -> None:
    assert find_existing_unicode_path(typed, base_dir=str(workspace)) is None


@POSIX_ONLY
@pytest.mark.parametrize(
    "typed",
    [pytest.param("\uff4e\uff4f\uff54\uff45\uff53.txt", id="fullwidth"), pytest.param('"notes.txt"', id="quoted")],
)
def test_healing_does_not_turn_a_spelling_into_a_link_to_a_credential_file(workspace: Path, typed: str) -> None:
    (workspace / "notes.txt").symlink_to(".env")

    assert find_existing_unicode_path(typed, base_dir=str(workspace)) is None


def test_healing_does_not_turn_a_spelling_into_a_forbidden_directory(home_workspace: Path) -> None:
    assert find_existing_unicode_path("\uff0e\uff53\uff53\uff48/config", base_dir=str(home_workspace)) is None


def test_a_guard_the_typed_spelling_lacks_is_refused_even_when_it_has_another(home_workspace: Path) -> None:
    # ``.ｓｓｈ/.env`` is a credential name already; the forbidden directory is the guard it gains by healing.
    assert find_existing_unicode_path("\uff0e\uff53\uff53\uff48/.env", base_dir=str(home_workspace)) is None


@pytest.mark.parametrize(
    "typed",
    [".env", ".env "],
    ids=["exact", "trailing-space"],
)
def test_a_typed_spelling_that_is_guarded_itself_is_left_to_the_engine(workspace: Path, typed: str) -> None:
    assert find_existing_unicode_path(typed, base_dir=str(workspace)) == typed.strip()


@pytest.mark.parametrize(
    ("typed", "on_disk"),
    [
        pytest.param("It\u2019s plan.md", "It's plan.md", id="curly-apostrophe"),
        pytest.param('"plain.md"', "plain.md", id="ascii-quotes"),
        pytest.param("报告（终稿）.md", "报告(终稿).md", id="fullwidth-parentheses"),
    ],
)
def test_a_spelling_of_an_ordinary_file_still_heals(workspace: Path, typed: str, on_disk: str) -> None:
    (workspace / on_disk).write_text("body")

    assert find_existing_unicode_path(typed, base_dir=str(workspace)) == on_disk


def test_a_decomposed_spelling_of_an_ordinary_file_still_heals(workspace: Path) -> None:
    decomposed = unicodedata.normalize("NFD", "Résumé draft.md")
    (workspace / decomposed).write_text("body")

    healed = find_existing_unicode_path(unicodedata.normalize("NFC", "Résumé draft.md"), base_dir=str(workspace))

    assert healed is not None
    assert (workspace / healed).read_text() == "body"


@pytest.fixture
def run_in_workspace(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("WORKSPACE_ROOT", str(workspace))
    monkeypatch.setattr(WorkspacePathResolver, "_cached_workspace_root", None)
    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(workspace)))
    root_token = workspace_root_var.set(str(workspace))
    yield workspace
    workspace_root_var.reset(root_token)
    reset_executor(executor_token)


async def _read(path: str) -> str:
    try:
        return str(await create_file_read_tool().ainvoke({"paths": [path]}, config=RunnableConfig()))
    except ToolError as failure:
        return failure.format_for_llm()


async def test_the_read_tool_does_not_return_a_credential_file_through_a_respelled_path(run_in_workspace: Path) -> None:
    assert CANARY not in await _read('".env"')


async def test_the_read_tool_still_heals_a_respelled_ordinary_path(run_in_workspace: Path) -> None:
    (run_in_workspace / "It's plan.md").write_text("plan body")

    assert "plan body" in await _read("It\u2019s plan.md")
