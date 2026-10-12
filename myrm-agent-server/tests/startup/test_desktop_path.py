"""Tests for desktop sidecar PATH hydration (login-shell probe, merge order, gating, failure modes).

A fake login shell stands in for the user's zsh: it evaluates the real ``-c`` probe script against a chosen
PATH, so the marker protocol and the subprocess plumbing are exercised for real.
"""

from __future__ import annotations

import os
import pwd
import signal
import stat
import time
import types
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.startup import desktop_path

_FAKE_SHELL = """#!/bin/sh
printf '%s\\n' "$@" > "$RECORD_DIR/args"
printf '%s|%s' "${ZDOTDIR-unset}" "$HOME" > "$RECORD_DIR/env"
printf 'rc noise before\\n'
PATH="$FAKE_PROBE_PATH"
eval "$4"
printf '\\nrc noise after\\n'
case "$FAKE_MODE" in
  hang)
    /bin/sleep 30 &
    echo $! > "$RECORD_DIR/child"
    wait
    ;;
  daemon)
    ( /bin/sleep 30 & echo $! > "$RECORD_DIR/child" )
    ;;
esac
"""


@pytest.fixture
def record_dir(tmp_path: Path) -> Path:
    path = tmp_path / "record"
    path.mkdir()
    return path


@pytest.fixture
def fake_shell(tmp_path: Path, record_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    script = tmp_path / "fake-shell"
    script.write_text(_FAKE_SHELL, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("SHELL", str(script))
    monkeypatch.setenv("MYRM_SHELL_PID", "1")
    monkeypatch.setenv("RECORD_DIR", str(record_dir))
    monkeypatch.setenv("FAKE_PROBE_PATH", "/opt/fake/bin:/usr/bin")
    monkeypatch.setenv("FAKE_MODE", "plain")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(desktop_path, "_SEED_DIRS", ())
    yield script
    child = record_dir / "child"
    if child.exists():
        try:
            os.kill(int(child.read_text().strip()), signal.SIGKILL)
        except ProcessLookupError:
            pass


class TestGating:
    def test_noop_without_shell_pid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MYRM_SHELL_PID", raising=False)
        monkeypatch.setenv("PATH", "/usr/bin:/bin")

        def _fail() -> list[str]:
            raise AssertionError("must not probe outside the desktop shell")

        monkeypatch.setattr(desktop_path, "_probe_login_shell_path", _fail)

        assert desktop_path.hydrate_desktop_path() == []
        assert os.environ["PATH"] == "/usr/bin:/bin"

    def test_blank_shell_pid_counts_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_SHELL_PID", "")

        assert desktop_path._spawned_by_desktop_shell() is False

    def test_never_runs_on_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_SHELL_PID", "1")
        monkeypatch.setattr(desktop_path, "sys", types.SimpleNamespace(platform="win32"))

        assert desktop_path._spawned_by_desktop_shell() is False


class TestProbe:
    def test_returns_login_shell_path_and_ignores_rc_noise(self, fake_shell: Path) -> None:
        assert desktop_path._probe_login_shell_path() == ["/opt/fake/bin", "/usr/bin"]

    def test_runs_interactive_login_shell_with_clean_zdotdir_and_account_home(
        self, fake_shell: Path, record_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ZDOTDIR", "/should/not/leak")
        monkeypatch.setenv("HOME", "/tmp/not-the-real-home")

        desktop_path._probe_login_shell_path()

        assert (record_dir / "args").read_text().splitlines()[:3] == ["-i", "-l", "-c"]
        zdotdir, home = (record_dir / "env").read_text().split("|")
        assert zdotdir == "unset"
        assert home == pwd.getpwuid(os.getuid()).pw_dir

    def test_drops_relative_and_empty_entries(self, fake_shell: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FAKE_PROBE_PATH", "/opt/a:.:rel/bin::/opt/b")

        assert desktop_path._probe_login_shell_path() == ["/opt/a", "/opt/b"]

    def test_missing_markers_yield_nothing(self) -> None:
        assert desktop_path._parse_probe_output(b"/usr/bin:/bin") == []
        assert desktop_path._parse_probe_output(b"__MYRM_PATH_START__/usr/bin") == []

    def test_timeout_kills_process_group_but_keeps_printed_path(
        self, fake_shell: Path, record_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAKE_MODE", "hang")
        monkeypatch.setattr(desktop_path, "_PROBE_TIMEOUT_SECONDS", 0.5)

        started = time.monotonic()
        entries = desktop_path._probe_login_shell_path()

        assert time.monotonic() - started < 5
        assert entries == ["/opt/fake/bin", "/usr/bin"]
        child_pid = int((record_dir / "child").read_text().strip())
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        pytest.fail("background child survived the process-group kill")

    def test_daemon_inheriting_stdout_does_not_stall_the_probe(self, fake_shell: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FAKE_MODE", "daemon")
        monkeypatch.setattr(desktop_path, "_PROBE_TIMEOUT_SECONDS", 10.0)

        started = time.monotonic()
        entries = desktop_path._probe_login_shell_path()

        assert time.monotonic() - started < 5
        assert entries == ["/opt/fake/bin", "/usr/bin"]


class TestResolveLoginShell:
    def test_prefers_shell_env(self, fake_shell: Path) -> None:
        assert desktop_path._resolve_login_shell("/bin/sh") == str(fake_shell)

    def test_falls_back_to_account_shell(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHELL", "/definitely/not/installed")

        assert desktop_path._resolve_login_shell("/bin/sh") == "/bin/sh"

    def test_rejects_relative_and_missing_shells(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHELL", "zsh")

        assert desktop_path._resolve_login_shell("") is None
        assert desktop_path._resolve_login_shell("/definitely/not/installed") is None


class TestMergeAndSeeds:
    def test_merge_orders_groups_dedupes_and_drops_empty_entries(self) -> None:
        merged = desktop_path._merge_entries(["/a", "/b"], ["/b", "", "/c"], ["/a", "/d"])

        assert merged == ["/a", "/b", "/c", "/d"]

    def test_seed_dirs_expand_home_and_skip_missing_dirs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / ".cargo" / "bin").mkdir(parents=True)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(desktop_path, "_SEED_DIRS", ("~/.cargo/bin", "~/.local/bin"))

        assert desktop_path._existing_seed_dirs() == [str(tmp_path / ".cargo" / "bin")]


class TestHydrate:
    def test_login_shell_entries_lead_and_seeds_trail(
        self, fake_shell: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seed = tmp_path / "seed"
        seed.mkdir()
        monkeypatch.setattr(desktop_path, "_SEED_DIRS", (str(seed), str(tmp_path / "missing")))

        added = desktop_path.hydrate_desktop_path()

        assert os.environ["PATH"] == f"/opt/fake/bin:/usr/bin:/bin:{seed}"
        assert added == ["/opt/fake/bin", str(seed)]

    def test_is_idempotent(self, fake_shell: Path) -> None:
        desktop_path.hydrate_desktop_path()
        first = os.environ["PATH"]

        assert desktop_path.hydrate_desktop_path() == []
        assert os.environ["PATH"] == first

    def test_failed_probe_still_adds_seeds(self, fake_shell: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        seed = tmp_path / "seed"
        seed.mkdir()
        monkeypatch.setattr(desktop_path, "_SEED_DIRS", (str(seed),))
        monkeypatch.setattr(desktop_path, "_probe_login_shell_path", lambda: [])

        assert desktop_path.hydrate_desktop_path() == [str(seed)]
        assert os.environ["PATH"] == f"/usr/bin:/bin:{seed}"

    def test_no_resolvable_shell_degrades_to_seeds(
        self, fake_shell: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seed = tmp_path / "seed"
        seed.mkdir()
        monkeypatch.setattr(desktop_path, "_SEED_DIRS", (str(seed),))
        monkeypatch.setattr(desktop_path, "_resolve_login_shell", lambda _account_shell: None)

        assert desktop_path.hydrate_desktop_path() == [str(seed)]
