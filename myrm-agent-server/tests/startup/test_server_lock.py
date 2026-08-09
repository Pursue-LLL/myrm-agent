"""Unit tests for server OS lock — active-holder exit, zombie-lock takeover.

活跃实例 = 持锁进程 alive **且** 监听 target_port；alive 但不监听端口
（僵尸 run.py）由新实例接管（BUG-DG-2026-08-09-R014 家族修复）。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path


def _import_lock_module(tmp_path: Path):

    from app.startup import server_lock

    server_lock._state_dir = tmp_path
    return server_lock


def _bind_listener(port: int) -> socket.socket:
    """Bind a real LISTEN socket so a holder counts as an active instance."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    return sock


def test_acquire_writes_pid_when_lock_free(tmp_path: Path) -> None:
    server_lock = _import_lock_module(tmp_path)
    server_lock.acquire_server_lock(18099, "127.0.0.1")
    pid_file = tmp_path / ".server.pid"
    assert pid_file.is_file()
    assert pid_file.read_text(encoding="utf-8").strip().isdigit()


def test_second_instance_exits_when_holder_alive_and_listening(tmp_path: Path) -> None:
    server_lock = _import_lock_module(tmp_path)
    listener = _bind_listener(18099)
    try:
        server_lock.acquire_server_lock(18099, "127.0.0.1")
        holder_pid = int((tmp_path / ".server.pid").read_text(encoding="utf-8").strip())
        assert holder_pid == _current_pid()
        # 确保 pid 文件、锁文件就位后再让子进程尝试
        time.sleep(0.2)

        server_root = Path(__file__).resolve().parents[2]
        code = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(server_root)!r})
from app.startup import server_lock
server_lock._state_dir = Path({str(tmp_path)!r})
server_lock.acquire_server_lock(18099, "127.0.0.1", holder_listen_grace_sec=0.5)
print("NO_EXIT")
"""
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 1
        assert "另一 backend 实例正在运行" in result.stdout
    finally:
        listener.close()


def test_alive_holder_without_listener_is_taken_over(tmp_path: Path) -> None:
    """持锁进程 alive 但不监听端口（僵尸 run.py）→ 新实例接管而非退出。"""
    server_lock = _import_lock_module(tmp_path)
    server_lock.acquire_server_lock(18099, "127.0.0.1")
    pid_file = tmp_path / ".server.pid"
    assert pid_file.read_text(encoding="utf-8").strip() == str(_current_pid())

    # 当前进程 alive 但并未监听 18099 —— 模拟僵尸 run.py。
    # 重新 acquire 应接管（写新 pid），而不是 exit(1)。
    server_lock.acquire_server_lock(18099, "127.0.0.1", holder_listen_grace_sec=0.2)
    assert pid_file.read_text(encoding="utf-8").strip() == str(_current_pid())


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
    return os.getpid()
