"""The read-only git probes the application runs without the hardened argv run no program the repository names.

[INPUT]
- git (POS: the real binary under test, never mocked)

[OUTPUT]
- Real ``git`` runs of every probe shape the application spawns bare (``rev-parse``, ``show-ref``, ``config --get``)
  against a repository whose config, attributes and hooks name marker-writing programs: none of them leaves a marker.

[POS]
Observation behind ``test_spawn_sites.py``, which lets these subcommands through unlisted because they touch neither
the index nor the work tree. The control run shows the repository's programs are live on this git build, so a silent
probe is not a vacuous result.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.git_probe import clear, fired, git, plain, program, run

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX shell scripts and git"
)

_PROBES: list[tuple[str, ...]] = [
    ("rev-parse", "--is-inside-work-tree"),
    ("rev-parse", "HEAD"),
    ("rev-parse", "--abbrev-ref", "HEAD"),
    ("rev-parse", "--show-toplevel"),
    ("rev-parse", "--path-format=absolute", "--git-common-dir"),
    ("rev-parse", "--is-bare-repository", "--absolute-git-dir", "--git-common-dir", "--show-toplevel"),
    ("show-ref", "--verify", "--quiet", "refs/heads/{branch}"),
    ("config", "--get", "user.name"),
    ("config", "--get", "user.email"),
]
_HOOKS = ("reference-transaction", "post-index-change", "fsmonitor-watchman", "pre-auto-gc", "post-checkout")
_PROGRAM_KEYS = (
    "core.pager",
    "core.editor",
    "core.askPass",
    "core.sshCommand",
    "core.gitProxy",
    "sequence.editor",
    "gpg.program",
    "gpg.ssh.program",
)


@pytest.fixture(autouse=True)
def _isolated_user_config(isolated_git_config: Path) -> Path:
    return isolated_git_config


@pytest.fixture(params=[False, True], ids=["hooks-dir", "hooks-path"])
def hostile(repo: Path, markers: Path, request: pytest.FixtureRequest) -> Path:
    """*repo* with a program named at every place git consults one, shown live by the plain ``status`` and ``diff``.

    The hooks sit in the repository's own hooks directory, or in the directory ``core.hooksPath`` points at.
    """
    git(repo, "config", "core.fsmonitor", program(markers, "fsmonitor"))
    git(repo, "config", "diff.external", program(markers, "external"))
    git(repo, "config", "diff.evil.textconv", program(markers, "textconv", passthrough='cat "$1"'))
    git(repo, "config", "filter.evil.clean", program(markers, "clean", passthrough="cat"))
    git(repo, "config", "filter.evil.process", program(markers, "process"))
    (repo / ".gitattributes").write_text("*.txt diff=evil filter=evil\n")
    for key in _PROGRAM_KEYS:
        git(repo, "config", key, program(markers, key.replace(".", "-")))
    git(repo, "config", "credential.helper", "!" + program(markers, "credential"))

    hooks = repo / "chosen-hooks"
    hooks.mkdir()
    for directory in (repo / ".git" / "hooks", hooks):
        for name in _HOOKS:
            hook = directory / name
            hook.write_text(f"#!/bin/sh\ntouch '{markers}/hook-{name}'\n")
            hook.chmod(0o755)
    if request.param:
        git(repo, "config", "core.hooksPath", str(hooks))

    run(plain(repo, "status", "--porcelain"), repo)
    run(plain(repo, "diff"), repo)
    if not fired(markers):
        pytest.skip("this git build runs no repository-named program for status or diff")
    clear(markers)
    return repo


@pytest.mark.parametrize("probe", _PROBES, ids=[" ".join(probe) for probe in _PROBES])
def test_a_read_only_probe_runs_no_program_the_repository_names(
    hostile: Path, markers: Path, probe: tuple[str, ...]
) -> None:
    branch = subprocess.run(
        ["git", "-C", str(hostile), "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    args = tuple(argument.format(branch=branch) for argument in probe)

    with_dash_c = run(plain(hostile, *args), hostile)
    from_inside = run(["git", *args], hostile)

    assert fired(markers) == set()
    assert with_dash_c.returncode in (0, 1) and from_inside.returncode in (0, 1), (
        with_dash_c.stderr,
        from_inside.stderr,
    )
