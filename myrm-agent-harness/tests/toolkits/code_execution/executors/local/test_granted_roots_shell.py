"""A shell reaches the directories granted beside the workspace, exactly as far as the grant says.

A command may name a granted directory only when an OS sandbox holds it to the grant: a writable grant is writable
there, a read-only grant is not, the git hooks of a writable grant stay read-only, and a directory nobody granted is
still refused. These run real commands under the real sandbox, so what is under test is the enforcement.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.core.context_vars import access_grants_var, open_access_grants, scoped_value
from myrm_agent_harness.core.security.types import AccessRoot
from myrm_agent_harness.toolkits.code_execution import create_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import _bash_sessions
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext

_requires_os_sandbox = pytest.mark.skipif(
    not _bash_sessions.sandbox_enforces(), reason="the grant is only honoured under an OS sandbox"
)
# Only macOS keeps a temporary directory outside the sandbox's scratch area, so a read-only denial is only checkable there.
_requires_scratch_outside_tmp = pytest.mark.skipif(
    sys.platform != "darwin", reason="a read-only grant under the scratch area stays writable on other platforms"
)


@pytest.fixture
def places(tmp_path: Path) -> Iterator[tuple[Path, Path, Path, Path]]:
    """A workspace, a directory granted writable, one granted read-only and one nobody granted."""
    root = tmp_path.resolve()
    workspace, writable, readable, ungranted = root / "ws", root / "rw", root / "ro", root / "other"
    for place in (workspace, writable, readable, ungranted):
        place.mkdir()
    (writable / "in.txt").write_text("writable note")
    (readable / "in.txt").write_text("readable note")
    (ungranted / "in.txt").write_text("nobody granted this")
    with scoped_value(access_grants_var, None):
        grants = open_access_grants(())
        grants.session = (AccessRoot(path=str(writable), writable=True), AccessRoot(path=str(readable), writable=False))
        yield workspace, writable, readable, ungranted


@pytest.fixture
async def executor(places: tuple[Path, Path, Path, Path]) -> AsyncIterator[LocalExecutor]:
    local = create_executor()
    assert isinstance(local, LocalExecutor)
    local.bind_workspace(str(places[0]))
    yield local
    await local.close()


def _context(workspace: Path, code: str) -> ExecutionContext:
    return ExecutionContext(
        code=code, work_dir=str(workspace), workspace_root=str(workspace), session_id="chat_granted_shell", timeout=30
    )


@_requires_os_sandbox
class TestBashUnderTheSandbox:
    async def test_a_writable_grant_can_be_read_and_written(
        self, executor: LocalExecutor, places: tuple[Path, Path, Path, Path]
    ) -> None:
        workspace, writable, _, _ = places

        read = await executor.execute_bash(_context(workspace, f"cat {writable}/in.txt"))
        wrote = await executor.execute_bash(_context(workspace, f"echo made > {writable}/out.txt"))

        assert read.success and "writable note" in read.stdout
        assert wrote.success
        assert (writable / "out.txt").read_text().strip() == "made"

    async def test_a_read_only_grant_can_be_read(
        self, executor: LocalExecutor, places: tuple[Path, Path, Path, Path]
    ) -> None:
        workspace, _, readable, _ = places

        read = await executor.execute_bash(_context(workspace, f"cat {readable}/in.txt"))

        assert read.success and "readable note" in read.stdout

    @_requires_scratch_outside_tmp
    async def test_a_read_only_grant_is_not_writable_for_the_os(
        self, executor: LocalExecutor, places: tuple[Path, Path, Path, Path]
    ) -> None:
        workspace, _, readable, _ = places

        wrote = await executor.execute_bash(_context(workspace, f"echo x > {readable}/out.txt"))

        assert not wrote.success
        assert not (readable / "out.txt").exists()

    async def test_a_directory_nobody_granted_is_still_refused(
        self, executor: LocalExecutor, places: tuple[Path, Path, Path, Path]
    ) -> None:
        workspace, _, _, ungranted = places

        read = await executor.execute_bash(_context(workspace, f"cat {ungranted}/in.txt"))

        assert not read.success
        assert "blocked" in (read.error or "").lower()

    async def test_the_git_hooks_of_a_writable_grant_stay_read_only(
        self, executor: LocalExecutor, places: tuple[Path, Path, Path, Path]
    ) -> None:
        workspace, writable, _, _ = places
        (writable / "repo" / ".git" / "hooks").mkdir(parents=True)
        (writable / "repo" / ".git" / "config").write_text("[core]\n")

        hook = await executor.execute_bash(_context(workspace, f"echo x > {writable}/repo/.git/hooks/pre-commit"))
        config = await executor.execute_bash(_context(workspace, f"echo x >> {writable}/repo/.git/config"))
        ordinary = await executor.execute_bash(_context(workspace, f"echo x > {writable}/repo/file.txt"))

        assert not hook.success and not (writable / "repo" / ".git" / "hooks" / "pre-commit").exists()
        assert not config.success and (writable / "repo" / ".git" / "config").read_text() == "[core]\n"
        assert ordinary.success

    async def test_a_changed_set_of_grants_starts_a_shell_under_the_new_sandbox(
        self, executor: LocalExecutor, places: tuple[Path, Path, Path, Path]
    ) -> None:
        workspace, _, _, ungranted = places
        grants = open_access_grants(())
        await executor.execute_bash(_context(workspace, "true"))
        first_shell = set(executor._bash_sessions)

        grants.session = (AccessRoot(path=str(ungranted), writable=True),)
        wrote = await executor.execute_bash(_context(workspace, f"echo made > {ungranted}/out.txt"))

        assert wrote.success and (ungranted / "out.txt").read_text().strip() == "made"
        assert len(executor._bash_sessions) == 1, "the shell of the old grants is closed, not kept beside the new one"
        assert not first_shell & set(executor._bash_sessions)


async def test_without_a_sandbox_a_command_still_cannot_name_a_granted_directory(
    executor: LocalExecutor, places: tuple[Path, Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, writable, _, _ = places
    monkeypatch.setattr(_bash_sessions, "sandbox_enforces", lambda: False)

    read = await executor.execute_bash(_context(workspace, f"cat {writable}/in.txt"))

    assert not read.success
    assert "blocked" in (read.error or "").lower()
