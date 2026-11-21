"""``git`` through the real bash tool and a real shell.

The header the tool puts in front of every command gives a commit an identity when the sandbox has none, and gives
every git the command starts, through git's environment configuration, a credential helper for GitHub over HTTPS. A
wrapper that loses the subcommand turns each into a git usage error, one that reads an unset variable breaks them for
every script in strict mode, and one that leaks its own variables or drops an argument changes what the next line of
the caller's command sees, so these cases run the whole path: the header, the wrapper and git itself.
The environment the shell inherits decides what git reads, so the last cases set git's configuration variables on the host.
The remote is a bare repository inside the workspace and the credential cases ask git for a credential without
contacting anyone, so no network is involved.
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
_INIT_WITH_REMOTE = "git init -q -b main && git init -q --bare -b main remote.git && git remote add origin remote.git"
_SET_IDENTITY = "git config user.name Repo-Owner && git config user.email owner@example.com"
_COMMIT = "git add a.txt && git commit -qm first"
_SUBJECT_ON_REMOTE = "git --git-dir=remote.git log -1 --format=%s main"
_BASE_COMMIT = "git init -q -b main && echo 1 > a && git add a && git commit -qm base"
_SIDE_COMMIT = "git switch -qc side && echo s > s && git add s && git commit -qm side && git switch -q main"
_DIVERGE_MAIN = "echo m > m && git add m && git commit -qm main2"
_COMMITTER = "git log -1 --format=%cn"
# The count, not the value: the tool masks what looks like a credential in the text it returns.
_HANDED_OUT = "grep -c '^password=' || true"


def _printed_number(output: str) -> int:
    """The number a command printed; the tool wraps its output in a notice and markers of its own."""
    return int(next(line for line in output.splitlines() if line.strip().isdigit()))


@pytest.fixture(autouse=True)
def _no_host_git_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A developer's global identity, a GitHub token or injected git config must not decide what a case sees."""
    for name in os.environ:
        if name.startswith("GIT_CONFIG") or name == "GITHUB_TOKEN":
            monkeypatch.delenv(name)
    (tmp_path / "home").mkdir()
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


@pytest.mark.parametrize(
    "script",
    [
        pytest.param(
            f"{_BASE_COMMIT} && {_SIDE_COMMIT} && {_DIVERGE_MAIN} && git merge --no-ff -qm merged side", id="merge"
        ),
        pytest.param(f"{_BASE_COMMIT} && {_SIDE_COMMIT} && git cherry-pick side > /dev/null", id="cherry-pick"),
        pytest.param(
            f"{_BASE_COMMIT} && echo 2 >> a && git commit -qam second && git revert --no-edit HEAD > /dev/null",
            id="revert",
        ),
        pytest.param(
            f"{_BASE_COMMIT} && {_SIDE_COMMIT} && {_DIVERGE_MAIN} && git switch -q side && git rebase -q main",
            id="rebase",
        ),
        pytest.param(
            f"{_BASE_COMMIT} && {_SIDE_COMMIT} && git format-patch -1 side --stdout > p.mbox && git am -q p.mbox",
            id="am",
        ),
        pytest.param(
            f"{_INIT_WITH_REMOTE} && echo 1 > a && git add a && git commit -qm base && git push -q origin main"
            " && git clone -q remote.git copy"
            " && (cd copy && echo c > c && git add c && git commit -qm theirs && git push -q origin main)"
            " && echo l > l && git add l && git commit -qm mine && git pull -q --no-rebase --no-edit origin main",
            id="pull",
        ),
    ],
)
async def test_every_subcommand_that_writes_a_commit_gets_the_fallback_identity(
    real_stack: RealBashStack, script: str
) -> None:
    output = await real_stack.run(f"{script} && {_COMMITTER}", timeout=_TIMEOUT)

    assert _FALLBACK_NAME in output
    assert "identity unknown" not in output


@pytest.mark.parametrize(
    ("script", "probe"),
    [
        pytest.param(
            f"{_BASE_COMMIT} && git tag -a v1 -m release",
            "git for-each-ref --format='%(taggername)' refs/tags/v1",
            id="tag",
        ),
        pytest.param(
            f"{_BASE_COMMIT} && git notes add -m note", "git log -1 --format=%cn refs/notes/commits", id="notes"
        ),
    ],
)
async def test_a_tag_or_note_gets_the_fallback_identity(real_stack: RealBashStack, script: str, probe: str) -> None:
    output = await real_stack.run(f"{script} && {probe}", timeout=_TIMEOUT)

    assert _FALLBACK_NAME in output
    assert "identity unknown" not in output


@pytest.mark.parametrize(
    ("configure", "author"),
    [
        pytest.param("git config --global user.name Alice", f"Alice <{_FALLBACK_EMAIL}>", id="name-only"),
        pytest.param(
            "git config --global user.email alice@example.com", f"{_FALLBACK_NAME} <alice@example.com>", id="email-only"
        ),
    ],
)
async def test_only_the_missing_half_of_an_identity_is_filled_in(
    real_stack: RealBashStack, configure: str, author: str
) -> None:
    await _prepare_repository(real_stack, with_identity=False)

    output = await real_stack.run(f"{configure} && {_COMMIT} && git log -1 --format='%an <%ae>'", timeout=_TIMEOUT)

    assert author in output


async def test_a_commit_made_with_the_callers_own_identity_keeps_it(real_stack: RealBashStack) -> None:
    await _prepare_repository(real_stack, with_identity=False)

    output = await real_stack.run(
        "git add a.txt && git -c user.name=Zed -c user.email=zed@example.com commit -qm first && git log -1 --format=%an",
        timeout=_TIMEOUT,
    )

    assert "Zed" in output
    assert _FALLBACK_NAME not in output


async def test_git_dash_c_reads_the_identity_of_the_repository_it_names(real_stack: RealBashStack) -> None:
    output = await real_stack.run(
        "git init -q -b main with && git -C with config user.name Local && git -C with config user.email local@example.com"
        " && git init -q -b main without && echo x > with/a && echo y > without/b"
        " && git -C with add a && git -C without add b && git -C with commit -qm one && git -C without commit -qm two"
        " && git -C with log -1 --format='with=%an' && git -C without log -1 --format='without=%an'",
        timeout=_TIMEOUT,
    )

    assert "with=Local" in output
    assert f"without={_FALLBACK_NAME}" in output


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


@pytest.mark.parametrize("subcommand", ["status", "diff"])
async def test_git_status_and_diff_print_what_git_prints(real_stack: RealBashStack, subcommand: str) -> None:
    """The output reaches the compressors the way git wrote it: no ``--porcelain`` rewrite, no summary in front."""
    await _prepare_repository(real_stack)
    await real_stack.run(_COMMIT, timeout=_TIMEOUT)
    (real_stack.workspace / "a.txt").write_text("CHANGED\n", encoding="utf-8")
    (real_stack.workspace / "b.txt").write_text("new\n", encoding="utf-8")

    output = await real_stack.run(f"git {subcommand}", timeout=_TIMEOUT)

    assert "System Note" not in output
    assert "## " not in output
    assert "--- Changes ---" not in output
    assert ("CHANGED" if subcommand == "diff" else "a.txt") in output


@pytest.mark.parametrize("command", ["status", "diff", "commit -qm again --allow-empty"])
async def test_a_git_subcommand_leaves_the_variables_of_the_caller_alone(
    real_stack: RealBashStack, command: str
) -> None:
    await _prepare_repository(real_stack)

    output = await real_stack.run(
        f"arg=mine\ngit {command} > /dev/null\necho arg=$arg\ncompgen -v | grep -cx -e global -e identity || true",
        timeout=_TIMEOUT,
    )

    assert "arg=mine" in output
    assert _printed_number(output) == 0, "the wrapper's own variables stay out of the caller's shell"


@pytest.mark.parametrize("command", ["diff", "commit -qam again"])
async def test_git_works_in_strict_mode_on_the_system_bash(
    real_stack: RealBashStack, stub_bin: StubBin, command: str
) -> None:
    """macOS ships bash 3.2, which treats expanding an empty array under ``set -u`` as an error."""
    system_bash = Path("/bin/bash")
    if not system_bash.exists():
        pytest.skip("no system bash to stand in for the one macOS ships")
    (stub_bin.directory / "bash").symlink_to(system_bash)
    await _prepare_repository(real_stack)
    await real_stack.run(_COMMIT, timeout=_TIMEOUT)
    (real_stack.workspace / "a.txt").write_text("CHANGED\n", encoding="utf-8")

    output = await real_stack.run(f"set -u\ngit {command}\ngit log -1 --format=%s", timeout=_TIMEOUT)

    assert "unbound variable" not in output
    assert ("CHANGED" if command == "diff" else "again") in output


async def test_git_without_arguments_in_strict_mode_prints_the_usage_of_git(real_stack: RealBashStack) -> None:
    output = await real_stack.run("set -u\ngit", timeout=_TIMEOUT)

    assert "usage: git" in output
    assert "unbound variable" not in output


def _fill(lines: str, *, token: str | None = "probe-token", where: str = "") -> str:
    """The command that asks git for the credential of the URL *lines* describe and prints how many it was given."""
    assignment = f"GITHUB_TOKEN={token} " if token else ""
    return f"{where}printf '{lines}\\n\\n' | {assignment}GIT_TERMINAL_PROMPT=0 git credential fill 2>/dev/null | {_HANDED_OUT}"


@pytest.mark.parametrize(
    ("lines", "handed_out"),
    [
        pytest.param("protocol=https\\nhost=github.com", True, id="github"),
        pytest.param("protocol=https\\nhost=github.com\\npath=owner/repo.git", True, id="github-with-a-path"),
        pytest.param("protocol=https\\nhost=github.com\\nusername=someone", True, id="github-with-a-user"),
        pytest.param("protocol=https\\nhost=www.github.com", False, id="www-github"),
        pytest.param("protocol=https\\nhost=github.com.evil.example", False, id="a-host-that-only-starts-like-github"),
        pytest.param("protocol=https\\nhost=gitlab.com", False, id="another-host"),
        pytest.param("protocol=http\\nhost=github.com", False, id="plain-http"),
        pytest.param("protocol=https\\nhost=github.com:8443", False, id="another-port"),
    ],
)
async def test_the_token_goes_to_github_over_https_and_to_nothing_else(
    real_stack: RealBashStack, lines: str, handed_out: bool
) -> None:
    output = await real_stack.run(_fill(lines), timeout=_TIMEOUT)

    assert _printed_number(output) == (1 if handed_out else 0)


async def test_no_token_means_no_credential(real_stack: RealBashStack) -> None:
    output = await real_stack.run(_fill("protocol=https\\nhost=github.com", token=None), timeout=_TIMEOUT)

    assert _printed_number(output) == 0


@pytest.mark.parametrize(
    ("where", "handed_out"),
    [
        pytest.param("git config --global credential.helper '!true' && ", False, id="helper-for-every-host"),
        pytest.param(
            "git config --global credential.https://github.com.helper '!true' && ", False, id="helper-for-github"
        ),
        pytest.param(
            "git config --global credential.https://gitlab.com.helper '!true' && ", True, id="helper-for-another-host"
        ),
        pytest.param("git init -q && git config credential.helper '!true' && ", False, id="helper-of-the-repository"),
    ],
)
async def test_the_token_is_withheld_while_another_credential_helper_applies(
    real_stack: RealBashStack, where: str, handed_out: bool
) -> None:
    """git tells every helper to store what it was given: a keychain must not keep the token of a command."""
    output = await real_stack.run(_fill("protocol=https\\nhost=github.com", where=where), timeout=_TIMEOUT)

    assert _printed_number(output) == (1 if handed_out else 0)


async def test_a_program_the_command_starts_gets_the_token_too(real_stack: RealBashStack) -> None:
    """The credential helper is in git's environment, not in a wrapper: a script or a package manager uses it."""
    script = "printf 'protocol=https\\nhost=github.com\\n\\n' | git credential fill 2>/dev/null | " + _HANDED_OUT
    (real_stack.workspace / "probe.sh").write_text(script + "\n", encoding="utf-8")

    output = await real_stack.run("GITHUB_TOKEN=probe-token GIT_TERMINAL_PROMPT=0 bash probe.sh", timeout=_TIMEOUT)

    assert _printed_number(output) == 1


async def test_git_runs_when_the_host_sets_a_group_of_git_config_variables_with_a_name_missing(
    real_stack: RealBashStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A count and a value without their key leave git failing on every command if the shell inherits them."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "x")

    output = await real_stack.run("git init -q -b main && git status --short && echo git-ok", timeout=_TIMEOUT)

    assert "git-ok" in output
    assert "missing config key" not in output


async def test_git_config_parameters_of_the_host_cannot_make_the_shell_run_a_program(
    real_stack: RealBashStack, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / "ran"
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", f"'alias.probe=!touch {marker}'")

    await real_stack.run("git probe", timeout=_TIMEOUT)

    assert not marker.exists()
