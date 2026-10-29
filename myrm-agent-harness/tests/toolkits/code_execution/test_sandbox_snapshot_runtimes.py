"""Enforcement tests for the ``Available Runtimes`` line of the sandbox bootstrap snapshot: a runtime is listed only when its binary ran and said which version it is.

[INPUT]
- toolkits.code_execution.sandbox_snapshot::generate_sandbox_bootstrap_snapshot / format_bootstrap_snapshot_xml (POS: sandbox bootstrap snapshot generator)
- executables in a temp directory that is the whole PATH (POS: real child processes, never mocked: a proxy without a toolchain, a version printed on stderr, a launcher that answers)

[OUTPUT]
- Fails when a binary on PATH that does not run (a toolchain proxy with nothing installed, a stub) is listed as an installed runtime, when ``python`` is not tried after a ``python3`` that does not
  run, or when Java, which reports its version on stderr, is listed without it or not at all.

[POS]
A runtime line is a statement of fact in the system message, so a binary that cannot answer is left out instead of being claimed. A working ``node`` runs beside the broken ones so a green run
cannot be an empty PATH.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.sandbox_snapshot import (
    format_bootstrap_snapshot_xml,
    generate_sandbox_bootstrap_snapshot,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stubs are POSIX shell scripts")

_RUSTUP_WITHOUT_TOOLCHAIN = 'echo "error: rustup could not choose a version of rustc to run" >&2\nexit 1'
_NODE = "echo v20.1.0"


@pytest.fixture
def bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty directory that is the whole PATH, with a workspace to probe next to it."""
    directory = tmp_path / "bin"
    directory.mkdir()
    monkeypatch.setenv("PATH", str(directory))
    return directory


def _install(directory: Path, name: str, body: str) -> None:
    script = directory / name
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(0o755)


def _says_on_stderr(banner: str) -> str:
    """Shell built-ins only: the stub's PATH holds nothing but the stubs."""
    return "\n".join(f"echo '{line}' >&2" for line in banner.splitlines())


def _runtimes(tmp_path: Path) -> tuple[str, ...]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return generate_sandbox_bootstrap_snapshot(workspace).runtimes


class TestOnlyARuntimeThatAnsweredIsListed:
    def test_binaries_that_do_not_run_are_left_out_next_to_one_that_does(self, bin_dir: Path, tmp_path: Path) -> None:
        _install(bin_dir, "node", _NODE)
        _install(bin_dir, "rustc", _RUSTUP_WITHOUT_TOOLCHAIN)
        _install(bin_dir, "python3", "exit 1")
        _install(bin_dir, "java", "exit 1")

        snapshot = generate_sandbox_bootstrap_snapshot(tmp_path)
        xml = format_bootstrap_snapshot_xml(snapshot)

        assert snapshot.runtimes == ("Node.js 20.1.0",)
        assert "Available Runtimes: Node.js 20.1.0\n" in xml

    def test_a_binary_that_answers_with_nothing_is_not_claimed_either(self, bin_dir: Path, tmp_path: Path) -> None:
        _install(bin_dir, "node", "exit 0")

        assert _runtimes(tmp_path) == ()

    def test_python_is_tried_when_python3_does_not_run(self, bin_dir: Path, tmp_path: Path) -> None:
        _install(bin_dir, "python3", "exit 1")
        _install(bin_dir, "python", "echo 3.11.4")

        assert _runtimes(tmp_path) == ("Python 3.11.4",)


class TestJavaReportsItsVersionOnStderr:
    @pytest.mark.parametrize(
        ("banner", "listed"),
        [
            ('openjdk version "21.0.4" 2024-07-16', "Java 21.0.4"),
            ('java version "1.8.0_391"', "Java 1.8.0_391"),
            ('openjdk version "22.0.2" 2024-07-16\nOpenJDK Runtime Environment (build 22.0.2+9-70)', "Java 22.0.2"),
        ],
    )
    def test_the_version_is_read_from_the_banner(self, bin_dir: Path, tmp_path: Path, banner: str, listed: str) -> None:
        _install(bin_dir, "java", _says_on_stderr(banner))

        assert _runtimes(tmp_path) == (listed,)

    def test_a_launcher_that_finds_no_java_is_not_listed(self, bin_dir: Path, tmp_path: Path) -> None:
        _install(bin_dir, "java", _says_on_stderr("Unable to locate a Java Runtime.") + "\nexit 1")

        assert _runtimes(tmp_path) == ()
