"""A directory the user granted widens the executor's boundary; a read-only grant never lets a write through.

The shell-based base class and the real ``LocalExecutor`` must agree, so both run the same cases.
"""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from myrm_agent_harness.agent.background_worker.shadow_context import ShadowExecutorMiddleware
from myrm_agent_harness.agent.sub_agents.spawn_capability import derive_spawn_capability
from myrm_agent_harness.core.context_vars import protected_paths_var, scoped_value, session_access_roots_var
from myrm_agent_harness.core.security.ocap import CapabilityDeniedError, capability_scope
from myrm_agent_harness.core.security.types import AccessRoot
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from tests.toolkits.code_execution._executor_stub import InProcessExecutor


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    path = tmp_path / "ws"
    path.mkdir()
    return path.resolve()


@pytest.fixture
def external(tmp_path: Path) -> Path:
    path = tmp_path / "external"
    path.mkdir()
    (path / "note.txt").write_text("outside note")
    return path.resolve()


@pytest.fixture(params=["shell-default", "local"])
def executor(request: pytest.FixtureRequest, workspace: Path, monkeypatch: pytest.MonkeyPatch) -> CodeExecutor:
    monkeypatch.chdir(workspace)
    ex: CodeExecutor = InProcessExecutor() if request.param == "shell-default" else LocalExecutor(ExecutionConfig())
    ex.bind_workspace(str(workspace))
    return ex


@pytest.fixture
def grant(external: Path) -> Iterator[None]:
    with scoped_value(session_access_roots_var, (AccessRoot(path=str(external), writable=False),)):
        yield


@pytest.fixture
def grant_writable(external: Path) -> Iterator[None]:
    with scoped_value(session_access_roots_var, (AccessRoot(path=str(external), writable=True),)):
        yield


async def test_a_directory_outside_the_workspace_is_refused_without_a_grant(
    executor: CodeExecutor, external: Path
) -> None:
    with pytest.raises(ValueError, match="Path traversal"):
        await executor.read_file(str(external / "note.txt"))


@pytest.mark.usefixtures("grant")
class TestReadingAGrantedDirectory:
    async def test_a_file_in_it_is_readable(self, executor: CodeExecutor, external: Path) -> None:
        assert await executor.read_file(str(external / "note.txt")) == "outside note"

    async def test_a_sibling_directory_is_still_refused(
        self, executor: CodeExecutor, external: Path, tmp_path: Path
    ) -> None:
        (tmp_path / "sibling").mkdir()
        (tmp_path / "sibling" / "secret.txt").write_text("secret")
        with pytest.raises(ValueError, match="Path traversal"):
            await executor.read_file(str(tmp_path / "sibling" / "secret.txt"))

    async def test_dot_dot_out_of_it_is_refused(self, executor: CodeExecutor, external: Path, tmp_path: Path) -> None:
        (tmp_path / "sibling").mkdir()
        (tmp_path / "sibling" / "secret.txt").write_text("secret")
        with pytest.raises(ValueError, match="Path traversal"):
            await executor.read_file(str(external / ".." / "sibling" / "secret.txt"))

    async def test_a_symlink_out_of_it_is_refused(self, executor: CodeExecutor, external: Path, tmp_path: Path) -> None:
        (tmp_path / "sibling").mkdir()
        (tmp_path / "sibling" / "secret.txt").write_text("secret")
        (external / "link").symlink_to(tmp_path / "sibling")
        with pytest.raises(ValueError, match="Path traversal"):
            await executor.read_file(str(external / "link" / "secret.txt"))


@pytest.mark.usefixtures("grant")
class TestReadOnlyGrant:
    async def test_write_is_refused(self, executor: CodeExecutor, external: Path) -> None:
        with pytest.raises(PermissionError, match="granted read-only"):
            await executor.write_file(str(external / "new.txt"), "x")
        assert not (external / "new.txt").exists()

    async def test_append_is_refused(self, executor: CodeExecutor, external: Path) -> None:
        with pytest.raises(PermissionError, match="granted read-only"):
            await executor.append_file(str(external / "note.txt"), "x")
        assert (external / "note.txt").read_text() == "outside note"

    async def test_delete_is_refused(self, executor: CodeExecutor, external: Path) -> None:
        with pytest.raises(PermissionError, match="granted read-only"):
            await executor.delete_file(str(external / "note.txt"))
        assert (external / "note.txt").exists()

    async def test_creating_a_directory_is_refused(self, executor: CodeExecutor, external: Path) -> None:
        with pytest.raises(PermissionError, match="granted read-only"):
            await executor.mkdir(str(external / "newdir"))
        assert not (external / "newdir").exists()

    async def test_the_workspace_stays_writable_when_it_lies_inside_the_grant(
        self, executor: CodeExecutor, workspace: Path, external: Path, tmp_path: Path
    ) -> None:
        with scoped_value(session_access_roots_var, (AccessRoot(path=str(tmp_path), writable=False),)):
            await executor.write_file("a.txt", "in the workspace")
            await executor.mkdir("made")
        assert (workspace / "a.txt").read_text() == "in the workspace"
        assert (workspace / "made").is_dir()

    async def test_a_writable_grant_nested_in_it_wins_for_its_own_directory(
        self, executor: CodeExecutor, external: Path
    ) -> None:
        (external / "out").mkdir()
        roots = (AccessRoot(path=str(external), writable=False), AccessRoot(path=str(external / "out"), writable=True))
        with scoped_value(session_access_roots_var, roots):
            await executor.write_file(str(external / "out" / "ok.txt"), "x")
            with pytest.raises(PermissionError, match="granted read-only"):
                await executor.write_file(str(external / "no.txt"), "x")
        assert (external / "out" / "ok.txt").read_text() == "x"


@pytest.mark.usefixtures("grant_writable")
class TestWritableGrant:
    async def test_write_and_directory_creation_are_allowed(self, executor: CodeExecutor, external: Path) -> None:
        await executor.write_file(str(external / "new.txt"), "x")
        await executor.mkdir(str(external / "newdir"))
        assert (external / "new.txt").read_text() == "x"
        assert (external / "newdir").is_dir()


async def test_creating_a_directory_obeys_the_active_goal_protection(workspace: Path) -> None:
    ex = LocalExecutor(ExecutionConfig())
    ex.bind_workspace(str(workspace))
    with scoped_value(protected_paths_var, ("locked",)), pytest.raises(PermissionError):
        await ex.mkdir("locked")
    assert not (workspace / "locked").exists()


@pytest.mark.usefixtures("grant_writable")
async def test_a_sub_agent_scope_still_bounds_a_granted_directory(workspace: Path, external: Path) -> None:
    ex = LocalExecutor(ExecutionConfig())
    ex.bind_workspace(str(workspace))
    handle = derive_spawn_capability(
        parent_agent=SimpleNamespace(_last_context={"workspace_path": str(workspace)}),
        agent_type="explorer",
        readonly=True,
    )
    with capability_scope(handle), pytest.raises(CapabilityDeniedError):
        await ex.read_file(str(external / "note.txt"))


@pytest.mark.usefixtures("grant_writable")
async def test_a_shadow_executor_still_refuses_writes_outside_the_workspace(workspace: Path, external: Path) -> None:
    ex = LocalExecutor(ExecutionConfig())
    ex.bind_workspace(str(workspace))
    with pytest.raises(PermissionError, match="shadow context"):
        await ShadowExecutorMiddleware(ex).write_file(str(external / "new.txt"), "x")
    assert not (external / "new.txt").exists()
