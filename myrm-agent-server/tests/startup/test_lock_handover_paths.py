"""In-process coverage for the port lock and the data-directory handover window.

The existing suites spawn subprocesses for the "another instance is alive" cases, which the
coverage tracer cannot see. These tests exercise the same branches in-process with a real
``filelock`` holder, so the handover/takeover logic in ``server_lock`` is actually measured.
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

import psutil
import pytest
from filelock import FileLock


def _lock_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.startup import server_lock

    monkeypatch.setattr(server_lock, "_get_state_dir", lambda: tmp_path)
    return server_lock


def _owner_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "pid": os.getpid(),
        "boot": round(psutil.boot_time(), 3),
        "started": round(psutil.Process(os.getpid()).create_time(), 3),
    }
    payload.update(overrides)
    return payload


def _write_owner(path: Path, payload: dict[str, object] | str) -> None:
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")


def _listen(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    return sock


@pytest.fixture
def port_lock_released(tmp_path: Path):
    from app.startup import server_lock

    yield
    lock = server_lock._server_lock
    if lock is not None:
        try:
            lock.release()
        except Exception:
            pass
        server_lock._server_lock = None
    for leftover in tmp_path.glob(".server_*.oslock"):
        leftover.unlink(missing_ok=True)


@pytest.fixture
def data_lock_released():
    from app.startup import server_lock

    yield
    lock = server_lock._data_dir_lock
    if lock is not None:
        try:
            lock.release()
        except Exception:
            pass
        server_lock._data_dir_lock = None


def test_port_lock_free_path_writes_pid(tmp_path: Path, port_lock_released, monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module(tmp_path, monkeypatch)
    server_lock.acquire_server_lock(18101, "127.0.0.1")

    pid_file = tmp_path / ".server_18101.pid"
    assert pid_file.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_port_lock_exits_when_holder_listens(tmp_path: Path, port_lock_released, monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module(tmp_path, monkeypatch)
    lock_file = tmp_path / ".server_18102.oslock"
    listener = _listen(18102)
    holder = FileLock(str(lock_file), timeout=0)
    holder.acquire()
    _write_owner(tmp_path / ".server_18102.pid", str(os.getpid()))
    monkeypatch.setattr(os, "_exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))

    try:
        with pytest.raises(SystemExit):
            server_lock.acquire_server_lock(18102, "127.0.0.1", holder_listen_grace_sec=0.2)
    finally:
        holder.release()
        listener.close()


def test_port_lock_takes_over_zombie_holder(tmp_path: Path, port_lock_released, monkeypatch: pytest.MonkeyPatch) -> None:
    """Alive holder that never listens (zombie run.py) must be taken over, not honoured."""
    server_lock = _lock_module(tmp_path, monkeypatch)
    lock_file = tmp_path / ".server_18103.oslock"
    holder = FileLock(str(lock_file), timeout=0)
    holder.acquire()
    _write_owner(tmp_path / ".server_18103.pid", str(os.getpid()))

    try:
        server_lock.acquire_server_lock(18103, "127.0.0.1", holder_listen_grace_sec=0.2)
    finally:
        try:
            holder.release()
        except Exception:
            pass

    assert (tmp_path / ".server_18103.pid").read_text(encoding="utf-8").strip() == str(os.getpid())


def test_port_lock_ignores_garbage_pid_file(tmp_path: Path, port_lock_released, monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module(tmp_path, monkeypatch)
    lock_file = tmp_path / ".server_18104.oslock"
    holder = FileLock(str(lock_file), timeout=0)
    holder.acquire()
    _write_owner(tmp_path / ".server_18104.pid", "not-a-pid")

    try:
        server_lock.acquire_server_lock(18104, "127.0.0.1", holder_listen_grace_sec=0.1)
    finally:
        try:
            holder.release()
        except Exception:
            pass

    assert (tmp_path / ".server_18104.pid").is_file()


def test_data_dir_lock_free_path_writes_owner(tmp_path: Path, data_lock_released, monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module(tmp_path, monkeypatch)
    monkeypatch.setattr(server_lock, "_data_dir_path", lambda: tmp_path)

    server_lock.acquire_data_dir_lock()

    owner = json.loads((tmp_path / ".data.lock.owner").read_text(encoding="utf-8"))
    assert owner["pid"] == os.getpid()
    assert owner["boot"] == pytest.approx(psutil.boot_time(), abs=2.0)


def test_data_dir_lock_takes_over_stale_owner(tmp_path: Path, data_lock_released, monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module(tmp_path, monkeypatch)
    monkeypatch.setattr(server_lock, "_data_dir_path", lambda: tmp_path)
    holder = FileLock(str(tmp_path / ".data.lock"), timeout=0)
    holder.acquire()
    _write_owner(tmp_path / ".data.lock.owner", _owner_payload(pid=999_999))

    try:
        server_lock.acquire_data_dir_lock()
    finally:
        try:
            holder.release()
        except Exception:
            pass

    owner = json.loads((tmp_path / ".data.lock.owner").read_text(encoding="utf-8"))
    assert owner["pid"] == os.getpid()


def test_data_dir_lock_exits_after_handover_window_when_holder_lives(
    tmp_path: Path, data_lock_released, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_lock = _lock_module(tmp_path, monkeypatch)
    monkeypatch.setattr(server_lock, "_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(server_lock, "_DATA_DIR_HANDOVER_SECONDS", 0.35)
    monkeypatch.setattr(os, "_exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    holder = FileLock(str(tmp_path / ".data.lock"), timeout=0)
    holder.acquire()
    _write_owner(tmp_path / ".data.lock.owner", _owner_payload())

    started = time.monotonic()
    try:
        with pytest.raises(SystemExit):
            server_lock.acquire_data_dir_lock()
    finally:
        holder.release()

    assert time.monotonic() - started >= 0.3


def test_data_dir_lock_waits_for_holder_to_finish_then_acquires(
    tmp_path: Path, data_lock_released, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A holder that finishes draining inside the window releases the lock; the new instance wins.

    filelock is thread-local, so the release happens inside the monkeypatched sleep on the same
    thread — this models "old instance finished draining while the new one is still waiting".
    """
    server_lock = _lock_module(tmp_path, monkeypatch)
    monkeypatch.setattr(server_lock, "_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(server_lock, "_DATA_DIR_HANDOVER_SECONDS", 2.0)
    holder = FileLock(str(tmp_path / ".data.lock"), timeout=0)
    holder.acquire()
    _write_owner(tmp_path / ".data.lock.owner", _owner_payload())

    released = {"done": False}

    def fake_sleep(_seconds: float) -> None:
        if not released["done"]:
            holder.release()
            released["done"] = True

    monkeypatch.setattr(server_lock.time, "sleep", fake_sleep)

    server_lock.acquire_data_dir_lock()

    owner = json.loads((tmp_path / ".data.lock.owner").read_text(encoding="utf-8"))
    assert owner["pid"] == os.getpid()
    assert released["done"] is True
