"""``git commit`` and ``git push`` through the real bash tool and a real shell.

The header the tool puts in front of every command wraps ``git`` so that a commit has an identity and a push has
credentials. A wrapper that loses the subcommand turns both into git usage errors, and one that reads an unset variable
breaks them for every script in strict mode, so these cases run the whole path: the header, the wrapper and git itself.
The remote is a bare repository inside the workspace, so no network is involved.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.agent.meta_tools.bash.real_stack import RealBashStack

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell semantics")

_TIMEOUT = 20
_FALLBACK_NAME = "myrm-agent"
_FALLBACK_EMAIL = "myrm-agent@users.noreply.github.com"
_INIT_WITH_REMOTE = "git init -q -b main && git init -q --bare remote.git && git remote add origin remote.git"
_SET_IDENTITY = "git config user.name Repo-Owner && git config user.email owner@example.com"
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


def _host_git_has_an_identity() -> bool:
    """The system-level git config is read whatever the environment says, so a host that sets an identity there hides the fallback."""
    probe = subprocess.run(["git", "config", "--system", "--get", "user.name"], capture_output=True, check=False)
    return probe.returncode == 0


async def test_a_commit_is_made_with_the_identity_the_repository_has(real_stack: RealBashStack) -> None:
    await _prepare_repository(real_stack)

    output = await real_stack.run("git add a.txt && git commit -qm first && git log -1 --format=%an", timeout=_TIMEOUT)

    assert "Repo-Owner" in output


async def test_a_commit_without_a_configured_identity_gets_the_fallback_identity(real_stack: RealBashStack) -> None:
    if _host_git_has_an_identity():
        pytest.skip("the host's system git config sets an identity")
    await _prepare_repository(real_stack, with_identity=False)

    output = await real_stack.run(
        "git add a.txt && git commit -qm first && git log -1 --format=%an && git log -1 --format=%ae", timeout=_TIMEOUT
    )

    assert _FALLBACK_NAME in output
    assert _FALLBACK_EMAIL in output


async def test_a_push_reaches_the_remote(real_stack: RealBashStack) -> None:
    await _prepare_repository(real_stack)

    await real_stack.run("git add a.txt && git commit -qm first && git push -q origin main", timeout=_TIMEOUT)

    assert "first" in await real_stack.run(_SUBJECT_ON_REMOTE, timeout=_TIMEOUT)


async def test_a_script_in_strict_mode_can_commit_and_push(real_stack: RealBashStack) -> None:
    await _prepare_repository(real_stack)

    output = await real_stack.run(
        f"set -euo pipefail\ngit add a.txt\ngit commit -qm strict\ngit push -q origin main\n{_SUBJECT_ON_REMOTE}",
        timeout=_TIMEOUT,
    )

    assert "strict" in output
