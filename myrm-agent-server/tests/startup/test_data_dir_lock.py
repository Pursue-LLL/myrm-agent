"""Data-directory lock: live vs stale owner detection.

端口锁只保护端口；数据目录锁保护 data.db/qdrant/checkpoints。这里只测纯判定函数，
避免在单元测试里触发 ``os._exit``。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import psutil


def _owner(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "pid": os.getpid(),
        "boot": round(psutil.boot_time(), 3),
        "started": round(psutil.Process(os.getpid()).create_time(), 3),
    }
    base.update(overrides)
    return base


def test_live_owner_is_live() -> None:
    from app.startup.server_lock import _owner_is_live

    assert _owner_is_live(_owner()) is True


def test_missing_owner_is_not_live() -> None:
    from app.startup.server_lock import _owner_is_live

    assert _owner_is_live(None) is False
    assert _owner_is_live({}) is False


def test_dead_pid_is_not_live() -> None:
    from app.startup.server_lock import _owner_is_live

    assert _owner_is_live(_owner(pid=999_999)) is False


def test_wrong_boot_id_is_not_live() -> None:
    from app.startup.server_lock import _owner_is_live

    assert _owner_is_live(_owner(boot=psutil.boot_time() - 10_000)) is False


def test_reused_pid_is_not_live() -> None:
    """A recycled pid has a different process start time and must not block startup."""
    from app.startup.server_lock import _owner_is_live

    assert _owner_is_live(_owner(started=time.time() - 10_000)) is False


def test_pytest_never_points_at_real_data_dir() -> None:
    """conftest must redirect MYRM_DATA_DIR away from the developer's ~/.myrm."""
    from app.config.settings import settings

    sqlite_path = Path(os.path.expanduser(settings.database.sqlite_path)).resolve()
    assert (Path.home() / ".myrm").resolve() not in sqlite_path.parents
