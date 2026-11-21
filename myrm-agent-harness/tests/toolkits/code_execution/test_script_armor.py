"""Tests for the script armor: every command of a POSIX shell session runs from a script file.

Validates:
1. A command is written to an owner-only script in the workspace's ``.myrm/exec`` directory and run as ``bash <script>``
2. The script is removed when the block ends, and a script that cannot be written fails the command instead of
   running it unarmored
3. Windows shells take the command as it is
4. PersistentSession: exit/exec statements and heredocs cannot break the shell, and the stale scripts of a killed shell
   are swept
"""

from __future__ import annotations

import gc
import os
import shlex
import stat
import subprocess
import time
import uuid
from pathlib import Path
from typing import NoReturn

import pytest

from myrm_agent_harness.core.security.detection.leak_detector import redact_leaks, scan_for_leaks
from myrm_agent_harness.toolkits.code_execution.security.script_armor import (
    prepare_armored_command,
    sweep_stale_materialized_scripts,
)
from myrm_agent_harness.toolkits.code_execution.session import (
    LocalPersistentSession,
    SessionConfig,
)
from myrm_agent_harness.toolkits.code_execution.utils.scratch_dir import scratch_dir


def _make_config(work_dir: Path, timeout: int = 10) -> SessionConfig:
    return SessionConfig(session_id="test_armor", work_dir=str(work_dir), timeout=timeout, sandbox_mode="disable")


def _script_dir(work_dir: Path) -> Path:
    """Where the armor keeps the scripts of the workspace ``work_dir`` (the layout the docs promise)."""
    return scratch_dir(work_dir, "exec")


def _script_of(shell_line: str) -> Path:
    """The script a shell line runs: the line is ``bash <script>``."""
    words = shlex.split(shell_line)
    assert len(words) == 2
    assert words[0] == "bash"
    return Path(words[1])


def _write_script(work_dir: Path, name: str, age_seconds: float) -> Path:
    """Put a script file, last touched ``age_seconds`` ago, into the script directory of ``work_dir``."""
    script_dir = _script_dir(work_dir)
    script_dir.mkdir(parents=True, exist_ok=True)
    path = script_dir / name
    path.write_text("echo script\n", encoding="utf-8")
    mtime = time.time() - age_seconds
    os.utime(path, (mtime, mtime))
    return path


class TestPrepareArmoredCommand:
    """The script a command runs from: content, permissions, location, lifetime, failure."""

    def test_script_holds_the_command_and_belongs_to_its_owner_alone(self, tmp_path: Path) -> None:
        with prepare_armored_command("echo 'armor test'\nexit 0", tmp_path) as shell_line:
            script = _script_of(shell_line)
            assert stat.S_IMODE(script.stat().st_mode) == 0o700
            assert script.read_text(encoding="utf-8") == "echo 'armor test'\nexit 0\n"

    def test_a_single_line_command_runs_from_a_script_too(self, tmp_path: Path) -> None:
        with prepare_armored_command("git status", tmp_path) as shell_line:
            assert _script_of(shell_line).read_text(encoding="utf-8") == "git status\n"

    def test_script_sits_in_the_workspace_and_stays_out_of_git(self, tmp_path: Path) -> None:
        with prepare_armored_command("echo 1\necho 2\necho 3\n", tmp_path) as shell_line:
            script = _script_of(shell_line)
            assert script.parent == _script_dir(tmp_path).resolve()
            assert (script.parent / ".gitignore").read_text(encoding="utf-8") == "*\n"

    def test_script_is_removed_when_the_block_ends(self, tmp_path: Path) -> None:
        with prepare_armored_command("echo hi", tmp_path) as shell_line:
            script = _script_of(shell_line)
            assert script.exists()

        assert not script.exists()

    def test_script_is_removed_when_the_block_raises(self, tmp_path: Path) -> None:
        script: Path | None = None
        with (
            pytest.raises(RuntimeError, match="simulated pipeline error"),
            prepare_armored_command("exit 1", tmp_path) as shell_line,
        ):
            script = _script_of(shell_line)
            assert script.exists()
            raise RuntimeError("simulated pipeline error")

        assert script is not None
        assert not script.exists()

    def test_a_script_the_command_removed_itself_is_no_error(self, tmp_path: Path) -> None:
        with prepare_armored_command("echo hi", tmp_path) as shell_line:
            _script_of(shell_line).unlink()

    def test_workspace_path_with_shell_metacharacters_still_runs_the_script(self, tmp_path: Path) -> None:
        workspace = tmp_path / 'my "proj" $HOME `id`'
        workspace.mkdir()

        with prepare_armored_command("echo armored", workspace) as shell_line:
            completed = subprocess.run(
                ["/bin/sh", "-c", shell_line], capture_output=True, text=True, timeout=30, check=False
            )

        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == "armored"

    def test_windows_shells_take_the_command_as_it_is(self, tmp_path: Path) -> None:
        with prepare_armored_command("dir", tmp_path, is_windows=True) as shell_line:
            assert shell_line == "dir"

        assert not (tmp_path / ".myrm").exists()

    def test_a_script_that_cannot_be_written_raises_before_the_block_runs(self, tmp_path: Path) -> None:
        not_a_directory = tmp_path / "plain_file"
        not_a_directory.write_text("occupied", encoding="utf-8")

        block_ran = False
        with pytest.raises(OSError), prepare_armored_command("echo hi", not_a_directory):
            block_ran = True

        assert not block_ran

    @pytest.mark.skipif(not os.path.isdir("/dev/fd"), reason="counting open descriptors needs /dev/fd")
    def test_a_failed_write_leaves_neither_a_script_nor_an_open_descriptor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _failing_open(*args: object, **kwargs: object) -> NoReturn:
            raise OSError("simulated disk write error")

        with prepare_armored_command("echo warm up", tmp_path):
            pass
        # Collect first, so that no unrelated file object is closed by the garbage collector between the two counts.
        gc.collect()
        descriptors_before = len(os.listdir("/dev/fd"))

        with monkeypatch.context() as patch:
            patch.setattr("builtins.open", _failing_open)
            with (
                pytest.raises(OSError, match="simulated disk write error"),
                prepare_armored_command("echo hi", tmp_path),
            ):
                pass

        gc.collect()
        assert len(os.listdir("/dev/fd")) == descriptors_before
        assert not list(_script_dir(tmp_path).glob(".myrm_exec_*.sh"))


class TestPersistentSessionIntegration:
    """End-to-end integration with LocalPersistentSession."""

    @pytest.mark.asyncio
    async def test_exit_statement_does_not_kill_persistent_shell(self, tmp_path: Path) -> None:
        """A command with 'exit 42' must return exit code 42 without killing the persistent shell."""
        session = LocalPersistentSession(_make_config(tmp_path))
        await session.start()
        try:
            res1 = await session.execute("if [ -d /tmp ]; then exit 42; fi")
            assert not res1.success
            assert res1.exit_code == 42

            res2 = await session.execute("echo shell_alive")
            assert res2.success
            assert "shell_alive" in res2.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_exec_statement_does_not_replace_the_persistent_shell(self, tmp_path: Path) -> None:
        """'exec' replaces the process that runs it: that must be the command's own shell, not the session's."""
        session = LocalPersistentSession(_make_config(tmp_path))
        await session.start()
        try:
            res1 = await session.execute("exec true")
            assert res1.success

            res2 = await session.execute("echo shell_alive")
            assert res2.success
            assert "shell_alive" in res2.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_a_command_cannot_change_the_state_of_the_shell(self, tmp_path: Path) -> None:
        """What a command exports or changes directory to dies with its own shell."""
        session = LocalPersistentSession(_make_config(tmp_path))
        await session.start()
        try:
            await session.execute("export ARMOR_PROBE=leaked; cd /")

            result = await session.execute('echo "${ARMOR_PROBE:-unset}"; pwd -P')
            assert result.success
            exported, directory = result.stdout.split()
            assert exported == "unset"
            assert Path(directory).resolve() == tmp_path.resolve()
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_a_short_command_runs_from_a_script_in_the_workspace(self, tmp_path: Path) -> None:
        """``$0`` of a command is its script: in the workspace's script directory, and gone once the command ended."""
        session = LocalPersistentSession(_make_config(tmp_path))
        await session.start()
        try:
            result = await session.execute('echo "$0"')
            assert result.success
            assert Path(result.stdout.strip()).parent == _script_dir(tmp_path).resolve()
            assert not list(_script_dir(tmp_path).glob(".myrm_exec_*.sh"))
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_command_is_not_run_when_its_script_cannot_be_written(self, tmp_path: Path) -> None:
        """No script, no command: it never reaches the shell unarmored, and the session carries on afterwards."""
        session = LocalPersistentSession(_make_config(tmp_path))
        await session.start()
        try:
            blocker = tmp_path / ".myrm"
            blocker.write_text("occupied", encoding="utf-8")

            result = await session.execute("touch ran.txt")
            assert not result.success
            assert result.error is not None
            assert "was not run" in result.error
            assert not (tmp_path / "ran.txt").exists()

            blocker.unlink()
            recovered = await session.execute("echo recovered")
            assert recovered.success
            assert "recovered" in recovered.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_heredoc_script_executes_without_beacon_swallowing(self, tmp_path: Path) -> None:
        """Heredoc script must execute cleanly without consuming trailing markers."""
        target_file = tmp_path / "heredoc_output.txt"
        heredoc_cmd = f"""cat << 'EOF' > "{target_file}"
def hello():
    return "world"
EOF
"""
        session = LocalPersistentSession(_make_config(tmp_path))
        await session.start()
        try:
            result = await session.execute(heredoc_cmd)
            assert result.success
            assert target_file.exists()
            content = target_file.read_text(encoding="utf-8")
            assert "def hello():" in content
            assert "__myrm_rc__" not in content
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_trailing_comment_without_newline(self, tmp_path: Path) -> None:
        """A command ending with a single-line comment must not swallow exit markers."""
        cmd = "echo 'comment_test' # trailing comment without newline"
        session = LocalPersistentSession(_make_config(tmp_path))
        await session.start()
        try:
            result = await session.execute(cmd)
            assert result.success
            assert "comment_test" in result.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_session_start_clears_the_stale_scripts_of_its_workspace(self, tmp_path: Path) -> None:
        """A script a killed shell left in the workspace is gone once a session starts there."""
        _write_script(tmp_path, ".myrm_exec_left_behind.sh", age_seconds=7200)
        session = LocalPersistentSession(_make_config(tmp_path))
        await session.start()
        try:
            assert not list(_script_dir(tmp_path).glob(".myrm_exec_*.sh"))
        finally:
            await session.close()


class TestSweepStaleMaterializedScripts:
    """Test orphan script cleanup mechanism."""

    def test_sweep_cleans_stale_files_and_keeps_fresh_ones(self, tmp_path: Path) -> None:
        stale_file = _write_script(tmp_path, ".myrm_exec_stale123.sh", age_seconds=7200)
        fresh_file = _write_script(tmp_path, ".myrm_exec_fresh456.sh", age_seconds=0)
        other_file = _write_script(tmp_path, "regular_file.sh", age_seconds=7200)

        cleaned = sweep_stale_materialized_scripts(tmp_path, max_age_seconds=3600.0)
        assert cleaned == 1
        assert not stale_file.exists()
        assert fresh_file.exists()
        assert other_file.exists()

    def test_sweep_only_looks_in_the_script_directory(self, tmp_path: Path) -> None:
        elsewhere = tmp_path / ".myrm_exec_stale789.sh"
        elsewhere.write_text("echo mine\n", encoding="utf-8")
        os.utime(elsewhere, (time.time() - 7200, time.time() - 7200))

        assert sweep_stale_materialized_scripts(tmp_path, max_age_seconds=3600.0) == 0
        assert elsewhere.exists()

    def test_sweep_nonexistent_directory(self) -> None:
        assert sweep_stale_materialized_scripts("/nonexistent/dir/xyz_404") == 0

    def test_sweep_handles_os_error_gracefully(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        stale_file = _write_script(tmp_path, ".myrm_exec_stale_err.sh", age_seconds=7200)

        real_stat = Path.stat

        def _selective_stat(self, *args, **kwargs):
            if str(self).endswith(".sh"):
                raise OSError("Permission denied on file")
            return real_stat(self, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", _selective_stat)
        assert sweep_stale_materialized_scripts(tmp_path, max_age_seconds=10.0) == 0
        monkeypatch.undo()
        assert stale_file.exists()

    def test_sweep_handles_unlistable_directory_gracefully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stale_file = _write_script(tmp_path, ".myrm_exec_stale_dir.sh", age_seconds=7200)

        def _unlistable(self, *args, **kwargs):
            raise OSError("Permission denied on directory")

        monkeypatch.setattr(Path, "glob", _unlistable)
        assert sweep_stale_materialized_scripts(tmp_path, max_age_seconds=10.0) == 0
        monkeypatch.undo()
        assert stale_file.exists()


class TestScriptNameInAListing:
    """The script is listed by any ``ls -a`` of the workspace while a command runs, and the model reads the listing."""

    def test_the_name_of_an_armored_script_is_no_credential_to_the_leak_detector(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An id whose hex digits read as random to the entropy scan (a few ids do not, so a fresh one would not pin it).
        monkeypatch.setattr("uuid.uuid4", lambda: uuid.UUID("6bd1b0fd-7950-43be-89d3-74bedb731800"))
        with prepare_armored_command("echo hi", tmp_path) as shell_line:
            listing = f"-rwx------@ 1 user staff 11559 Nov 18 18:52 {_script_of(shell_line).name}"

            assert scan_for_leaks(listing) == []
            assert redact_leaks(listing) == listing
