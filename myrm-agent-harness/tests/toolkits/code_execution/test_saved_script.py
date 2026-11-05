"""Unit tests for saved-script resolution and the launcher that runs a script as ``__main__``.

[INPUT]
- myrm_agent_harness.toolkits.code_execution.saved_script (POS: ``python file.py`` -> the workspace script it runs)

[OUTPUT]
- Coverage for which commands resolve to a script (and which must never), and for the launcher keeping
  ``python file.py`` semantics: ``__main__``, ``__file__``, ``sys.argv``, ``sys.path[0]``, tracebacks, exit codes.

[POS]
Saved-script tests. Resolution is pure filesystem; the launcher is run in a real interpreter.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.saved_script import (
    MAX_SAVED_SCRIPT_BYTES,
    SavedScript,
    resolve_saved_script,
)

_SOURCE = "print('hi')\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "probe.py").write_text(_SOURCE, encoding="utf-8")
    (workspace / "sub").mkdir()
    (workspace / "sub" / "deep.py").write_text("print('deep')\n", encoding="utf-8")
    return workspace


@pytest.mark.parametrize(
    ("command", "relative_path"),
    [
        ("python probe.py", "probe.py"),
        ("python3 probe.py", "probe.py"),
        ("  python3 probe.py\n", "probe.py"),
        ("python3 ./probe.py", "probe.py"),
        ("python3 sub/deep.py", "sub/deep.py"),
        ("python3 /workspace/probe.py", "probe.py"),
        ("python3 /workspace/sub/deep.py", "sub/deep.py"),
        ("cd /workspace && python3 probe.py", "probe.py"),
        ("cd . && python3 probe.py", "probe.py"),
        ("cd /workspace&&python3 probe.py", "probe.py"),
        ("cd /workspace && python3 sub/deep.py", "sub/deep.py"),
    ],
)
def test_resolves_the_one_command_shape_whose_code_is_a_workspace_file(
    root: Path, command: str, relative_path: str
) -> None:
    script = resolve_saved_script(command, str(root))

    assert script is not None
    assert script.path == (root / relative_path).resolve()
    assert script.source == (root / relative_path).read_text(encoding="utf-8")


def test_resolves_absolute_paths_and_a_cd_to_the_workspace_root(root: Path) -> None:
    absolute = f"cd {root} && python3 {root}/probe.py"

    script = resolve_saved_script(absolute, str(root))

    assert script is not None
    assert script.path == (root / "probe.py").resolve()


def test_argv0_is_the_script_argument_as_typed(root: Path) -> None:
    script = resolve_saved_script("python3 ./sub/deep.py", str(root))

    assert script is not None
    assert script.argv0 == "./sub/deep.py"


@pytest.mark.parametrize(
    "command",
    [
        "python3 probe.py --x",
        "python3 -u probe.py",
        "python3 -m probe",
        "python3 -c 'print(1)'",
        "python3 probe.py | head",
        "python3 probe.py > out.txt",
        "python3 probe.py && echo done",
        "python3 probe.py; echo done",
        "python3 probe.py &",
        "FOO=1 python3 probe.py",
        "uv run python3 probe.py",
        "echo hi && python3 probe.py",
        "cd sub && python3 deep.py",
        "cd /tmp && python3 probe.py",
        "python3 $HOME/probe.py",
        "python3 `echo probe`.py",
        "python3 'probe.py'",
        "python3 pro be.py",
        "python3 ~/probe.py",
        "python3 probe.txt",
        "python3 sub",
        "python3 missing.py",
        "python3 /workspace2/probe.py",
        "python3 ../probe.py",
        "python3 /etc/hosts.py",
        "python3 probe.py\npython3 probe.py",
        "",
    ],
)
def test_every_other_command_is_left_to_the_shell(root: Path, command: str) -> None:
    assert resolve_saved_script(command, str(root)) is None


def test_no_workspace_root_means_no_resolution(root: Path) -> None:
    assert resolve_saved_script("python3 probe.py", None) is None
    assert resolve_saved_script("python3 probe.py", "") is None


def test_a_symlink_that_leaves_the_workspace_is_refused(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("print('outside')\n", encoding="utf-8")
    (root / "link.py").symlink_to(outside)

    assert resolve_saved_script("python3 link.py", str(root)) is None


def test_a_symlink_inside_the_workspace_resolves_to_its_target(root: Path) -> None:
    (root / "alias.py").symlink_to(root / "probe.py")

    script = resolve_saved_script("python3 alias.py", str(root))

    assert script is not None
    assert script.path == (root / "probe.py").resolve()


def test_a_symlinked_workspace_root_still_contains_its_scripts(root: Path, tmp_path: Path) -> None:
    alias_root = tmp_path / "ws-alias"
    alias_root.symlink_to(root, target_is_directory=True)

    script = resolve_saved_script("cd /workspace && python3 probe.py", str(alias_root))

    assert script is not None
    assert script.source == _SOURCE


def test_a_script_that_is_not_utf8_is_left_to_the_shell(root: Path) -> None:
    (root / "binary.py").write_bytes(b"\xff\xfe\x00print(1)\n")

    assert resolve_saved_script("python3 binary.py", str(root)) is None


def test_a_script_over_the_size_cap_is_left_to_the_shell(root: Path) -> None:
    (root / "big.py").write_text("x = 1\n" * (MAX_SAVED_SCRIPT_BYTES // 6 + 10), encoding="utf-8")

    assert resolve_saved_script("python3 big.py", str(root)) is None


def test_a_script_exactly_at_the_size_cap_is_resolved(root: Path) -> None:
    (root / "edge.py").write_text("#" * (MAX_SAVED_SCRIPT_BYTES - 1) + "\n", encoding="utf-8")

    assert resolve_saved_script("python3 edge.py", str(root)) is not None


def _run(root: Path, launcher: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", launcher],
        cwd=root,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def _run_launcher(root: Path, name: str, body: str) -> subprocess.CompletedProcess[str]:
    (root / name).write_text(textwrap.dedent(body), encoding="utf-8")
    script = resolve_saved_script(f"python3 {name}", str(root))
    assert script is not None
    return _run(root, script.launcher(script.source))


def test_launcher_runs_the_script_as_main_with_its_own_file_and_argv(root: Path) -> None:
    proc = _run_launcher(
        root,
        "who.py",
        """\
        import sys
        print(__name__, __file__, sys.argv, sys.path[0])
        """,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split(None, 1)[0] == "__main__"
    assert f"{(root / 'who.py').resolve()}" in proc.stdout
    assert "['who.py']" in proc.stdout
    assert proc.stdout.rstrip().endswith(str(root.resolve()))


def test_launcher_keeps_the_script_directory_first_on_the_path(root: Path) -> None:
    (root / "sub" / "helper.py").write_text("VALUE = 41\n", encoding="utf-8")

    proc = _run_launcher(
        root,
        "sub/user.py",
        """\
        import helper
        print(helper.VALUE + 1)
        """,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "42"


def test_launcher_lets_the_script_find_files_beside_itself(root: Path) -> None:
    (root / "data.txt").write_text("beside", encoding="utf-8")

    proc = _run_launcher(
        root,
        "reader.py",
        """\
        from pathlib import Path
        print((Path(__file__).parent / "data.txt").read_text())
        """,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "beside"


def test_launcher_honours_the_main_guard_and_future_imports(root: Path) -> None:
    proc = _run_launcher(
        root,
        "guarded.py",
        """\
        from __future__ import annotations

        def f(x: Undefined) -> Undefined:
            return x

        if __name__ == "__main__":
            print(f.__annotations__["x"])
        """,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "Undefined"


def test_launcher_does_not_leak_its_own_names_into_the_script(root: Path) -> None:
    proc = _run_launcher(
        root,
        "clean.py",
        """\
        print(sorted(n for n in globals() if not n.startswith("__")))
        """,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[]"


def test_launcher_tracebacks_name_the_script_file_and_line(root: Path) -> None:
    proc = _run_launcher(
        root,
        "boom.py",
        """\
        x = 1
        raise RuntimeError("boom")
        """,
    )

    assert proc.returncode != 0
    assert str((root / "boom.py").resolve()) in proc.stderr
    assert "line 2" in proc.stderr
    assert "RuntimeError: boom" in proc.stderr


def test_launcher_propagates_the_exit_code(root: Path) -> None:
    proc = _run_launcher(root, "bye.py", "import sys\nsys.exit(7)\n")

    assert proc.returncode == 7


def test_launcher_embeds_the_given_source_not_the_file(root: Path) -> None:
    (root / "orig.py").write_text("print('on disk')\n", encoding="utf-8")
    script = resolve_saved_script("python3 orig.py", str(root))
    assert script is not None

    proc = _run(root, script.launcher("print('rewritten')\n"))

    assert proc.stdout.strip() == "rewritten"


def test_launcher_handles_source_with_quotes_and_unicode(root: Path) -> None:
    proc = _run_launcher(
        root,
        "quoted.py",
        '''\
        print("""it's \\"fine\\" \\\\ \u4e2d\u6587""")
        ''',
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == 'it\'s "fine" \\ \u4e2d\u6587'


def test_saved_script_is_immutable(root: Path) -> None:
    script = resolve_saved_script("python3 probe.py", str(root))
    assert isinstance(script, SavedScript)

    with pytest.raises(AttributeError):
        script.source = "x"  # type: ignore[misc]
