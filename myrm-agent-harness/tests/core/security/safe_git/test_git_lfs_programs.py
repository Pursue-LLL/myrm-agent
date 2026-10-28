"""A repository's settings cannot make git-lfs run a program or receive a credential during an application git command.

[INPUT]
- core.security.safe_git (POS: hardened argv and the no-prompt environment for commands that write the tree)

[OUTPUT]
- Real ``git`` and ``git-lfs`` runs against a folder that arrived with its ``.git`` directory and an LFS file whose
  objects are missing: a credential helper, an ask-pass program, an ssh command, the ``ssh`` on PATH, a custom transfer
  agent and an LFS extension each fire on the plain command and stay silent on the hardened one; no credential reaches
  the host the repository names; a repository-local ``git lfs install`` keeps checking out and staging real content.

[POS]
Enforcement tests for the git-lfs side of ``hardened_git_argv``: git-lfs reads the repository's own settings, so the
``-c`` overrides that stop git's own programs do not reach it and each key is proven against the real program. Skipped
where ``git-lfs`` is not installed.
"""

from __future__ import annotations

import http.server
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from myrm_agent_harness.core.security.safe_git import HARDENED_GIT_ENV, hardened_git_argv
from tests.support.git_probe import clear, fired, git, plain, program

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None or shutil.which("git-lfs") is None,
    reason="needs POSIX shell scripts, git and git-lfs",
)

_COMMAND_SECONDS = 30
_CREDENTIALS = "printf 'username=u\\npassword=p\\n'"


class _LfsHost(http.server.ThreadingHTTPServer):
    """The host a repository names: it asks for credentials, then refuses, and records each request."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Challenge)
        self.carried_credentials: list[bool] = []

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class _Challenge(http.server.BaseHTTPRequestHandler):
    def _answer(self) -> None:
        host = cast("_LfsHost", self.server)
        host.carried_credentials.append("Authorization" in self.headers)
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        # Refusing for good after two challenges ends a client that keeps asking (an ask-pass that always answers).
        self.send_response(401 if len(host.carried_credentials) <= 2 else 403)
        self.send_header("WWW-Authenticate", 'Basic realm="lfs"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        self._answer()

    def do_POST(self) -> None:
        self._answer()

    def log_message(self, format: str, *args: object) -> None:
        return None


@pytest.fixture
def host() -> Iterator[_LfsHost]:
    server = _LfsHost()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def _a_user_with_git_lfs_installed(isolated_git_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A global ``git lfs install`` is what every LFS user has, and what a hostile repository relies on."""
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in ("GIT_ASKPASS", "SSH_ASKPASS", "GIT_SSH", "GIT_SSH_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    subprocess.run(["git", "lfs", "install"], cwd=tmp_path, check=True, capture_output=True)


def _lfs_repo(path: Path, *, keep_objects: bool) -> Path:
    path.mkdir()
    git(path, "init", "-q")
    git(path, "config", "user.email", "a@example.com")
    git(path, "config", "user.name", "a")
    git(path, "lfs", "track", "*.bin")
    (path / "a.bin").write_text("content\n")
    git(path, "add", ".gitattributes", "a.bin")
    git(path, "commit", "-q", "-m", "an LFS file")
    if not keep_objects:
        shutil.rmtree(path / ".git" / "lfs" / "objects")
    return path


@pytest.fixture
def arrived(tmp_path: Path) -> Path:
    """What a zip or a shared drive delivers: the pointer is committed, the object it points to never arrived."""
    return _lfs_repo(tmp_path / "arrived", keep_objects=False)


@pytest.fixture
def stocked(tmp_path: Path) -> Path:
    """The user's own clone: the object is in the local LFS store."""
    return _lfs_repo(tmp_path / "stocked", keep_objects=True)


def _copy(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination, symlinks=True)
    return destination


def _config(repo: Path, text: str) -> None:
    with (repo / ".git" / "config").open("a", encoding="utf-8") as handle:
        handle.write(text)


def _run(argv: list[str], cwd: Path, *, control: bool = False) -> subprocess.CompletedProcess[bytes] | None:
    """The plain control may loop for good once it has fired; the hardened command must end by itself."""
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            env={**os.environ, **HARDENED_GIT_ENV},
            capture_output=True,
            timeout=_COMMAND_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        if control:
            return None
        raise


def _worktree(repo: Path, tmp_path: Path, label: str, *, hardened: bool) -> subprocess.CompletedProcess[bytes] | None:
    args = ("worktree", "add", "-B", "hostile", str(tmp_path / f"{label}-wt"))
    argv = hardened_git_argv(args, repo_dir=repo) if hardened else plain(repo, *args)
    return _run(argv, repo, control=not hardened)


# name -> (what the script answers, the repository's config; ``{program}`` is that script, ``{origin}`` the host)
_VECTORS: dict[str, tuple[str, str]] = {
    "helper": (
        _CREDENTIALS,
        '[remote "origin"]\n\turl = {origin}/repo.git\n[credential]\n\thelper = !{program}\n',
    ),
    "helper-for-the-host": (
        _CREDENTIALS,
        '[remote "origin"]\n\turl = {origin}/repo.git\n[credential "{origin}"]\n\thelper = !{program}\n',
    ),
    "askpass": (
        "echo secret",
        '[remote "origin"]\n\turl = {origin}/repo.git\n[core]\n\taskPass = {program}\n',
    ),
    "ssh-command": (
        "exit 1",
        '[remote "origin"]\n\turl = ssh://git@127.0.0.1:1/repo.git\n[core]\n\tsshCommand = {program}\n',
    ),
    "custom-transfer": (
        "exit 1",
        '[remote "origin"]\n\turl = {origin}/repo.git\n[lfs]\n\tstandalonetransferagent = evil\n'
        '[lfs "customtransfer.evil"]\n\tpath = {program}\n',
    ),
}


def _plant(repo: Path, markers: Path, host: _LfsHost, name: str) -> None:
    answer, template = _VECTORS[name]
    _config(repo, template.format(origin=host.origin, program=program(markers, name, passthrough=answer)))


class TestAProgramTheRepositoryNamesDoesNotRun:
    @pytest.mark.parametrize("name", list(_VECTORS))
    def test_checking_out_a_missing_lfs_object(
        self, arrived: Path, markers: Path, host: _LfsHost, tmp_path: Path, name: str
    ) -> None:
        control = _copy(arrived, tmp_path / "control")
        _plant(control, markers, host, name)
        _worktree(control, tmp_path, "control", hardened=False)
        if name not in fired(markers):
            pytest.skip(f"git-lfs here does not run the {name} vector while checking out a worktree")
        clear(markers)
        host.carried_credentials.clear()

        victim = _copy(arrived, tmp_path / "victim")
        _plant(victim, markers, host, name)
        result = _worktree(victim, tmp_path, "victim", hardened=True)

        assert fired(markers) == set(), f"{name} still ran on the hardened command"
        assert result is not None and result.returncode != 0, "a missing object must be an error, not an empty file"

    def test_a_custom_transfer_agent_from_the_users_own_config_is_not_picked_by_the_repository(
        self, arrived: Path, markers: Path, host: _LfsHost, tmp_path: Path, isolated_git_config: Path
    ) -> None:
        """The program is the user's, so no listing of the repository's keys sees it; only the choice is the repository's."""
        agent = program(markers, "users-agent", passthrough="exit 1")
        with isolated_git_config.open("a", encoding="utf-8") as handle:
            handle.write(f'[lfs "customtransfer.mine"]\n\tpath = {agent}\n')
        choice = f'[remote "origin"]\n\turl = {host.origin}/repo.git\n[lfs]\n\tstandalonetransferagent = mine\n'
        control = _copy(arrived, tmp_path / "control")
        _config(control, choice)
        _worktree(control, tmp_path, "control", hardened=False)
        if "users-agent" not in fired(markers):
            pytest.skip("git-lfs here does not let a repository choose the transfer agent")
        clear(markers)

        victim = _copy(arrived, tmp_path / "victim")
        _config(victim, choice)
        result = _worktree(victim, tmp_path, "victim", hardened=True)

        assert fired(markers) == set()
        assert result is not None and result.returncode != 0

    def test_the_ssh_found_on_path_is_not_started(
        self, arrived: Path, markers: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        ssh = bin_dir / "ssh"
        ssh.write_text(f"#!/bin/sh\ntouch '{markers}/ssh'\nexit 1\n")
        ssh.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        remote = '[remote "origin"]\n\turl = ssh://git@127.0.0.1:1/repo.git\n'
        control = _copy(arrived, tmp_path / "control")
        _config(control, remote)
        _worktree(control, tmp_path, "control", hardened=False)
        if "ssh" not in fired(markers):
            pytest.skip("git-lfs here does not start ssh while checking out a worktree")
        clear(markers)

        victim = _copy(arrived, tmp_path / "victim")
        _config(victim, remote)
        result = _worktree(victim, tmp_path, "victim", hardened=True)

        assert fired(markers) == set()
        assert result is not None and result.returncode != 0

    def test_an_lfs_extension_while_staging_an_edited_file(self, stocked: Path, markers: Path, tmp_path: Path) -> None:
        extension = program(markers, "extension", passthrough="cat")
        hostile = f'[lfs "extension.evil"]\n\tclean = {extension} %f\n\tsmudge = {extension} %f\n\tpriority = 0\n'

        def victim(label: str) -> Path:
            repo = _copy(stocked, tmp_path / label)
            _config(repo, hostile)
            (repo / "a.bin").write_text("edited\n")
            return repo

        control = victim("control")
        _run(plain(control, "add", "-A"), control, control=True)
        if "extension" not in fired(markers):
            pytest.skip("git-lfs here does not run its extensions while staging a file")
        clear(markers)

        repo = victim("victim")
        result = _run(hardened_git_argv(("add", "-A"), repo_dir=repo), repo)

        assert fired(markers) == set()
        assert result is not None and result.returncode != 0, "a blanked extension must stop the add, not skip it"


class TestNoCredentialReachesTheHostTheRepositoryNames:
    def test_the_users_credential_store_and_the_repositorys_helper_are_not_asked(
        self, arrived: Path, markers: Path, host: _LfsHost, tmp_path: Path
    ) -> None:
        control = _copy(arrived, tmp_path / "control")
        _plant(control, markers, host, "helper")
        _worktree(control, tmp_path, "control", hardened=False)
        if not any(host.carried_credentials):
            pytest.skip("git-lfs here never answers the host's challenge with a credential")
        host.carried_credentials.clear()

        victim = _copy(arrived, tmp_path / "victim")
        _plant(victim, markers, host, "helper")
        _worktree(victim, tmp_path, "victim", hardened=True)

        assert not any(host.carried_credentials), "a request carried a credential"


class TestARepositoryLocalLfsInstallKeepsWorking:
    @pytest.fixture
    def local_install(self, stocked: Path) -> Path:
        git(stocked, "lfs", "install", "--local")
        return stocked

    def test_a_worktree_is_checked_out_with_the_real_content(self, local_install: Path, tmp_path: Path) -> None:
        result = _worktree(local_install, tmp_path, "task", hardened=True)

        assert result is not None and result.returncode == 0, result.stderr if result else b"timed out"
        assert (tmp_path / "task-wt" / "a.bin").read_text() == "content\n"

    def test_an_edited_file_is_staged_as_a_pointer(self, local_install: Path) -> None:
        (local_install / "a.bin").write_text("edited\n")

        result = _run(hardened_git_argv(("add", "-A"), repo_dir=local_install), local_install)

        assert result is not None and result.returncode == 0, result.stderr if result else b"timed out"
        staged = subprocess.run(
            plain(local_install, "cat-file", "-p", ":a.bin"), capture_output=True, check=True
        ).stdout
        assert staged.startswith(b"version https://git-lfs.github.com/spec/v1")
