"""Unit tests for server OS lock — active-holder exit, zombie-lock takeover."""

from __future__ import annotations

from pathlib import Path

import pytest


def _import_lock_module(tmp_path: Path):
    import sys

    from app.startup import server_lock

    server_lock._state_dir = tmp_path
    return server_lock


def test_acquire_writes_pid_when_lock_free(tmp_path: Path) -> None:
    server_lock = _import_lock_module(tmp_path)
    server_lock.acquire_server_lock(18099, "127.0.0.1")
    pid_file = tmp_path / ".server.pid"
    assert pid_file.is_file()
    assert pid_file.read_text(encoding="utf-8").strip().isdigit()


def test_second_instance_exits_when_holder_alive(tmp_path: Path) -> None:
    import subprocess
    import sys

    server_lock = _import_lock_module(tmp_path)
    server_lock.acquire_server_lock(18099, "127.0.0.1")
    holder_pid = int((tmp_path / ".server.pid").read_text(encoding="utf-8").strip())
    assert holder_pid == _current_pid()

    server_root = Path(__file__).resolve().parents[2]
    code = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(server_root)!r})
from app.startup import server_lock
server_lock._state_dir = Path({str(tmp_path)!r})
server_lock.acquire_server_lock(18099, "127.0.0.1")
print("NO_EXIT")
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 1
    assert "另一 backend 实例正在运行" in result.stdout


def test_zombie_lock_is_taken_over(tmp_path: Path) -> None:
    server_lock = _import_lock_module(tmp_path)
    server_lock.acquire_server_lock(18099, "127.0.0.1")
    # Simulate a stale holder: write a dead pid to the pid file and drop the
    # lock so a fresh instance can take over (zombie-lock takeover path).
    pid_file = tmp_path / ".server.pid"
    pid_file.write_text("999999", encoding="utf-8")
    lock_file = tmp_path / ".server.oslock"
    try:
        lock_file.unlink()
    except OSError:
        pass

    server_lock.acquire_server_lock(18099, "127.0.0.1")
    assert pid_file.read_text(encoding="utf-8").strip() == str(_current_pid())


def _current_pid() -> int:
    import os

    return os.getpid()
