"""``git`` through the real bash tool and a real shell.

The header the tool puts in front of every command wraps ``git`` so that a commit has an identity, a push has
credentials and ``status`` and ``diff`` are summarised. A wrapper that loses the subcommand turns each into a git usage
error, one that reads an unset variable breaks them for every script in strict mode, and one that leaks its own
variables or drops an argument changes what the next line of the caller's command sees, so these cases run the whole
path: the header, the wrapper and git itself.
The remote is a bare repository inside the workspace, so no network is involved.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tests.agent.meta_tools.bash.real_stack import RealBashStack, StubBin

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell semantics")

_TIMEOUT = 20
_FALLBACK_NAME = "myrm-agent"
_FALLBACK_EMAIL = "myrm-agent@users.noreply.github.com"
_INIT_WITH_REMOTE = "git init -q -b main && git init -q --bare remote.git && git remote add origin remote.git"
_SET_IDENTITY = "git config user.name Repo-Owner && git config user.email owner@example.com"
_COMMIT = "git add a.txt && git commit -qm first"
_SUBJECT_ON_REMOTE = "git --git-dir=remote.git log -1 --format=%s main"


@pytest.fixture(autouse=True)
def _no_host_git_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A developer's global identity, a GitHub token or injected git config must not decide what a case sees."""
    for name in os.environ:
        if name.startswith("GIT_CONFIG") or name == "GITHUB_TOKEN":
            monkeypatch.delenv(name)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


async def _prepare_repository(stack: RealBashStack, *, with_identity: bool = True) -> None:
    await stack.run(_INIT_WITH_REMOTE, timeout=_TIMEOUT)
    if with_identity:
        await stack.run(_SET_IDENTITY, timeout=_TIMEOUT)
    (stack.workspace / "a.txt").write_text("x\n", encoding="utf-8")


async def test_a_commit_is_made_with_the_identity_the_repository_has(real_stack: RealBashStack) -> None:
    await _prepare_repository(real_stack)

    output = await real_stack.run(f"{_COMMIT} && git log -1 --format=%an", timeout=_TIMEOUT)

    assert "Repo-Owner" in output


async def test_a_commit_without_a_configured_identity_gets_the_fallback_identity(real_stack: RealBashStack) -> None:
    await _prepare_repository(real_stack, with_identity=False)

    output = await real_stack.run(f"{_COMMIT} && git log -1 --format=%an && git log -1 --format=%ae", timeout=_TIMEOUT)

    assert _FALLBACK_NAME in output
    assert _FALLBACK_EMAIL in output


async def test_a_push_reaches_the_remote(real_stack: RealBashStack) -> None:
    await _prepare_repository(real_stack)

    await real_stack.run(f"{_COMMIT} && git push -q origin main", timeout=_TIMEOUT)

    assert "first" in await real_stack.run(_SUBJECT_ON_REMOTE, timeout=_TIMEOUT)


async def test_git_add_all_stages_none_of_the_harness_files(real_stack: RealBashStack) -> None:
    """The script a command runs from and the output log of the command before it sit in the workspace, not in a commit."""
    await real_stack.run("echo first", timeout=_TIMEOUT)

    output = await real_stack.run(
        "git init -q -b main && echo x > a.txt && git add -A && git ls-files", timeout=_TIMEOUT
    )

    staged = output.split()
    assert "a.txt" in staged
    assert not [name for name in staged if name.startswith(".myrm")]


async def test_a_script_in_strict_mode_can_commit_and_push(real_stack: RealBashStack) -> None:
    await _prepare_repository(real_stack)

    output = await real_stack.run(
        f"set -euo pipefail\ngit add a.txt\ngit commit -qm strict\ngit push -q origin main\n{_SUBJECT_ON_REMOTE}",
        timeout=_TIMEOUT,
    )

    assert "strict" in output


async def test_a_clone_runs_on_a_host_without_a_usable_timeout(real_stack: RealBashStack, stub_bin: StubBin) -> None:
    """Stock macOS has no ``timeout`` and elsewhere it cannot run a shell builtin, so a clone must not need it."""
    stub_bin.add("timeout", "echo 'timeout: command not found' >&2\nexit 127")
    await _prepare_repository(real_stack)
    await real_stack.run(f"{_COMMIT} && git push -q origin main", timeout=_TIMEOUT)

    output = await real_stack.run("git clone -q -b main remote.git copy", timeout=_TIMEOUT)

    assert (real_stack.workspace / "copy" / "a.txt").read_text(encoding="utf-8") == "x\n"
    assert "Fallback" not in output


async def test_a_clone_that_fails_reports_what_git_said(real_stack: RealBashStack) -> None:
    output = await real_stack.run("git clone missing.git copy", timeout=_TIMEOUT)

    assert "does not exist" in output
    assert "[exit_code: 128]" in output
    assert "Fallback" not in output
    assert "timed out" not in output


async def test_git_diff_of_a_path_named_diff_shows_that_path_only(real_stack: RealBashStack) -> None:
    await _prepare_repository(real_stack)
    (real_stack.workspace / "diff").write_text("d\n", encoding="utf-8")
    await real_stack.run("git add a.txt diff && git commit -qm first", timeout=_TIMEOUT)
    (real_stack.workspace / "a.txt").write_text("A-CHANGED\n", encoding="utf-8")
    (real_stack.workspace / "diff").write_text("D-CHANGED\n", encoding="utf-8")

    output = await real_stack.run("git diff -- diff", timeout=_TIMEOUT)

    assert "D-CHANGED" in output
    assert "A-CHANGED" not in output


@pytest.mark.parametrize("subcommand", ["status", "diff"])
async def test_a_git_subcommand_leaves_the_variables_of_the_caller_alone(
    real_stack: RealBashStack, subcommand: str
) -> None:
    await _prepare_repository(real_stack)

    output = await real_stack.run(f"arg=mine\ngit {subcommand} > /dev/null\necho arg=$arg", timeout=_TIMEOUT)

    assert "arg=mine" in output


async def test_git_diff_works_in_strict_mode_on_the_system_bash(real_stack: RealBashStack, stub_bin: StubBin) -> None:
    """macOS ships bash 3.2, which treats expanding an empty array under ``set -u`` as an error."""
    system_bash = Path("/bin/bash")
    if not system_bash.exists():
        pytest.skip("no system bash to stand in for the one macOS ships")
    (stub_bin.directory / "bash").symlink_to(system_bash)
    await _prepare_repository(real_stack)
    await real_stack.run(_COMMIT, timeout=_TIMEOUT)
    (real_stack.workspace / "a.txt").write_text("CHANGED\n", encoding="utf-8")

    output = await real_stack.run("set -u\ngit diff", timeout=_TIMEOUT)

    assert "CHANGED" in output
    assert "unbound variable" not in output
