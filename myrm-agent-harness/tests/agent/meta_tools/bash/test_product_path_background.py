"""A background job starts where a foreground command does, through the real bash tool and a real shell.

The job starts in the directory ``/workspace`` means to the executor, which for a chat bound to a project is the
project and not the chat's own storage directory, and starting it leaves the executor bound where it was.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution import create_workspace_service
from tests.agent.meta_tools.bash.real_stack import SESSION_ID, RealBashStack, real_bash_stack

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell semantics")

_LIST_CWD = "import os\nprint(sorted(os.listdir('.')))"


@pytest.fixture(autouse=True)
def _fake_pids_have_no_process_group() -> None:
    """The jobs here are real processes, so the real process-group lookup applies."""


async def test_a_job_starts_in_the_project_of_a_project_bound_chat(shared_real_stack: RealBashStack) -> None:
    (shared_real_stack.workspace / "in_project.txt").write_text("x", encoding="utf-8")

    job = await shared_real_stack.run_background("ls")

    assert job.exit_code == 0
    assert "in_project.txt" in job.stdout


async def test_starting_a_job_leaves_a_later_python_run_in_the_project(shared_real_stack: RealBashStack) -> None:
    (shared_real_stack.workspace / "in_project.txt").write_text("x", encoding="utf-8")

    await shared_real_stack.run_background("true")

    assert "in_project.txt" in await shared_real_stack.run(_LIST_CWD)


async def test_a_job_of_a_chat_with_its_own_workspace_starts_there(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    service = create_workspace_service(root_dir=storage)
    own_workspace = Path(service.get_workspace_absolute_path(await service.get_or_create(session_id=SESSION_ID)))
    (own_workspace / "in_chat_workspace.txt").write_text("x", encoding="utf-8")

    async with real_bash_stack(own_workspace, storage_root=storage) as stack:
        foreground = await stack.run("ls")
        job = await stack.run_background("ls")

    assert "in_chat_workspace.txt" in foreground
    assert "in_chat_workspace.txt" in job.stdout
