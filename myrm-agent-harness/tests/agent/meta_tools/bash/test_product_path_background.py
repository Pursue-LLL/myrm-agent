"""A background job starts where, and in the shell, a foreground command does: the real bash tool and a real shell.

The job starts in the directory ``/workspace`` means to the executor, which for a chat bound to a project is the
project and not the chat's own storage directory, and starting it leaves the executor bound where it was. Bash reads
it, as it reads a foreground command, whatever ``sh`` is on the host, and behind the same header.
"""

from __future__ import annotations

import os
import shutil
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


@pytest.fixture
def dash_as_sh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Put a ``sh`` that is dash first on PATH, as on Debian and Ubuntu, where bash idioms fail."""
    dash = shutil.which("dash")
    if dash is None:
        pytest.skip("dash is not installed")
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    (shim_dir / "sh").symlink_to(dash)
    monkeypatch.setenv("PATH", f"{shim_dir}{os.pathsep}{os.environ['PATH']}")


async def test_a_job_starts_in_the_project_of_a_project_bound_chat(shared_real_stack: RealBashStack) -> None:
    (shared_real_stack.workspace / "in_project.txt").write_text("x", encoding="utf-8")

    job = await shared_real_stack.run_background("ls")

    assert job.exit_code == 0
    assert "in_project.txt" in job.stdout


async def test_starting_a_job_leaves_a_later_python_run_in_the_project(shared_real_stack: RealBashStack) -> None:
    (shared_real_stack.workspace / "in_project.txt").write_text("x", encoding="utf-8")

    await shared_real_stack.run_background("true")

    assert "in_project.txt" in await shared_real_stack.run(_LIST_CWD)


async def test_a_job_reads_the_header_a_foreground_command_reads(shared_real_stack: RealBashStack) -> None:
    job = await shared_real_stack.run_background('echo "ci=$CI"; type git')

    assert job.exit_code == 0, job.stderr
    assert "git is a function" in job.stdout
    assert "ci=true" in job.stdout, "the CI value the spawn set stays"


async def test_a_job_commits_with_the_fallback_identity(
    shared_real_stack: RealBashStack, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A developer's own identity, found through the home directory, must not decide what the job sees."""
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    # A job has a terminal, so a ``git log`` that does not turn the pager off waits for a key.
    job = await shared_real_stack.run_background(
        "git init -q -b main repo && cd repo && echo x > a && git add a && git commit -qm job"
        " && git --no-pager log -1 --format='%an <%ae>'"
    )

    assert job.exit_code == 0, job.stderr
    assert "myrm-agent <myrm-agent@users.noreply.github.com>" in job.stdout


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


@pytest.mark.usefixtures("dash_as_sh")
@pytest.mark.parametrize(
    ("command", "expected"),
    [
        pytest.param(
            "echo 'export V=1' > activate.sh && source ./activate.sh && echo source-ok V=$V",
            "source-ok V=1",
            id="source",
        ),
        pytest.param("[[ -d . ]] && echo double-bracket-ok", "double-bracket-ok", id="double-bracket"),
        pytest.param("echo posix-ok && ls > /dev/null && echo done", "done", id="posix-only"),
    ],
)
async def test_bash_reads_a_job_whatever_sh_is(shared_real_stack: RealBashStack, command: str, expected: str) -> None:
    job = await shared_real_stack.run_background(command)

    assert job.exit_code == 0, job.stderr
    assert expected in job.stdout
