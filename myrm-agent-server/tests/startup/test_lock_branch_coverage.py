"""Branch coverage for the lock helpers: psutil failures, missing filelock, takeover failures."""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

import psutil
import pytest
from filelock import FileLock


def _lock_module():
    from app.startup import server_lock

    return server_lock


def _owner_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "pid": os.getpid(),
        "boot": round(psutil.boot_time(), 3),
        "started": round(psutil.Process(os.getpid()).create_time(), 3),
    }
    payload.update(overrides)
    return payload


def _listen(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    return sock


def test_state_dir_prefers_explicit_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module()
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.delenv("MYRM_DEV_STATE_DIR", raising=False)
    assert server_lock._get_state_dir() == tmp_path.resolve()

    monkeypatch.delenv("STATE_DIR")
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path))
    assert server_lock._get_state_dir() == tmp_path.resolve()


def test_read_pid_file_tolerates_unreadable_path(tmp_path: Path) -> None:
    server_lock = _lock_module()
    directory = tmp_path / "pid-dir"
    directory.mkdir()
    assert server_lock._read_pid_file(directory) is None


def test_process_alive_fails_closed_on_psutil_error(monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module()
    monkeypatch.setattr(psutil, "pid_exists", lambda _pid: True)
    monkeypatch.setattr(psutil, "Process", lambda _pid: (_ for _ in ()).throw(psutil.NoSuchProcess(1)))
    assert server_lock._process_alive(1) is False


def test_pid_listens_port_handles_missing_process(monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module()
    monkeypatch.setattr(psutil, "Process", lambda _pid: (_ for _ in ()).throw(psutil.NoSuchProcess(1)))
    assert server_lock._pid_listens_port(1, 18111) is False


def test_pid_listens_port_fails_closed_when_connections_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module()
    process = type("P", (), {"net_connections": lambda self, kind=None: (_ for _ in ()).throw(psutil.AccessDenied())})
    monkeypatch.setattr(psutil, "Process", lambda _pid: process())
    assert server_lock._pid_listens_port(1, 18111) is True


def test_port_lock_skips_when_filelock_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module()
    monkeypatch.setattr(server_lock, "_get_state_dir", lambda: tmp_path)
    monkeypatch.setitem(sys.modules, "filelock", None)
    server_lock.acquire_server_lock(18112, "127.0.0.1")
    assert not (tmp_path / ".server_18112.pid").exists()


def test_data_dir_lock_skips_when_filelock_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module()
    monkeypatch.setattr(server_lock, "_data_dir_path", lambda: tmp_path)
    monkeypatch.setitem(sys.modules, "filelock", None)
    server_lock.acquire_data_dir_lock()
    assert not (tmp_path / ".data.lock.owner").exists()


def test_zombie_takeover_warns_when_port_still_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module()
    monkeypatch.setattr(server_lock, "_get_state_dir", lambda: tmp_path)
    listener = _listen(18113)
    lock_file = tmp_path / ".server_18113.oslock"
    holder = FileLock(str(lock_file), timeout=0)
    holder.acquire()
    (tmp_path / ".server_18113.pid").write_text(str(os.getpid()), encoding="utf-8")

    # Hold the lock with a live pid but pretend it never listens: the zombie-takeover path
    # then runs while the port is still bound, which covers the TIME_WAIT warning branch.
    monkeypatch.setattr(server_lock, "_pid_listens_port", lambda _pid, _port: False)

    try:
        server_lock.acquire_server_lock(18113, "127.0.0.1", holder_listen_grace_sec=0.1)
    finally:
        try:
            holder.release()
        except Exception:
            pass
        listener.close()

    assert (tmp_path / ".server_18113.pid").read_text(encoding="utf-8").strip() == str(os.getpid())


def test_port_lock_exits_when_takeover_cannot_acquire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module()
    monkeypatch.setattr(server_lock, "_get_state_dir", lambda: tmp_path)
    lock_file = tmp_path / ".server_18114.oslock"
    holder = FileLock(str(lock_file), timeout=0)
    holder.acquire()
    (tmp_path / ".server_18114.pid").write_text(str(os.getpid()), encoding="utf-8")
    # Simulate a lock file that cannot be removed: takeover keeps hitting the holder.
    monkeypatch.setattr(server_lock.os, "remove", lambda _p: (_ for _ in ()).throw(OSError("busy")))
    monkeypatch.setattr(os, "_exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))

    try:
        with pytest.raises(SystemExit):
            server_lock.acquire_server_lock(18114, "127.0.0.1", holder_listen_grace_sec=0.1)
    finally:
        holder.release()


def test_data_dir_path_points_at_sqlite_parent() -> None:
    server_lock = _lock_module()
    from app.config.settings import settings

    expected = Path(os.path.expanduser(settings.database.sqlite_path)).resolve().parent
    assert server_lock._data_dir_path() == expected


def test_read_owner_returns_none_for_malformed_json(tmp_path: Path) -> None:
    server_lock = _lock_module()
    path = tmp_path / "owner.json"
    path.write_text("not-json", encoding="utf-8")
    assert server_lock._read_owner(path) is None
    assert server_lock._read_owner(tmp_path / "missing.json") is None


def test_owner_is_live_rejects_invalid_field_types() -> None:
    server_lock = _lock_module()
    assert server_lock._owner_is_live({"pid": "abc"}) is False
    assert server_lock._owner_is_live({"pid": 0}) is False
    assert server_lock._owner_is_live(_owner_payload(boot="bad")) is False
    assert server_lock._owner_is_live(_owner_payload(started="bad")) is False


def test_data_dir_lock_exits_when_takeover_cannot_acquire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module()
    monkeypatch.setattr(server_lock, "_data_dir_path", lambda: tmp_path)
    holder = FileLock(str(tmp_path / ".data.lock"), timeout=0)
    holder.acquire()
    (tmp_path / ".data.lock.owner").write_text(json.dumps(_owner_payload(pid=999_999)), encoding="utf-8")
    monkeypatch.setattr(Path, "unlink", lambda _self, missing_ok=False: (_ for _ in ()).throw(OSError("busy")))
    monkeypatch.setattr(os, "_exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))

    try:
        with pytest.raises(SystemExit):
            server_lock.acquire_data_dir_lock()
    finally:
        holder.release()
        from app.startup import server_lock as lock_module

        lock_module._data_dir_lock = None


def test_state_dir_falls_back_to_configured_state_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    server_lock = _lock_module()
    from app.config.settings import settings

    monkeypatch.delenv("STATE_DIR", raising=False)
    monkeypatch.delenv("MYRM_DEV_STATE_DIR", raising=False)

    assert server_lock._get_state_dir() == Path(settings.database.state_dir)
