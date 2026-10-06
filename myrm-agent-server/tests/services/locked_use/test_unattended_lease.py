"""无人值守帷幕租约单测 — 租约持有 / 交还 / 作废 / 接管分支。

[INPUT]
- app.services.locked_use.unattended（POS: watcher 租约编排）
- tests.support.curtain_watcher（POS: 状态快照与 tick 驱动器）

[OUTPUT]
- 回锁成功交还、回锁失败保留并冷却（冷却期内不重放、期满重试）、屏幕外部锁定作废、
  主人撤帷幕作废（不反锁）、状态桥缺失复位、遗留租约位接管/清除

[POS]
与 test_unattended_curtain_watcher.py（五条件获取分支）互补。纯 mock，不真 sleep。
"""

from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock

import pytest

from app.services.locked_use import unattended
from app.services.locked_use.curtain_bridge import (
    CurtainBridgeState,
)
from tests.support.curtain_watcher import (
    drive,
    has_session,
    make_state,
    no_session,
    record_clear,
    set_locked,
)


def test_lease_released_after_verified_relock(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """租约持有期：CU 会话结束 → 校验回锁成功后交还租约（租约位清除由 release_unlock_lease 保证）。"""
    monkeypatch.setattr(unattended, "_lease_held", True)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    monkeypatch.setattr(unattended, "_cu_session_active", no_session)
    release = AsyncMock(return_value=True)
    monkeypatch.setattr(unattended, "release_unlock_lease", release)

    with caplog.at_level(logging.INFO):
        drive(monkeypatch)

    release.assert_awaited_once()
    assert unattended._lease_held is False
    assert "lease released" in caplog.text


def test_lease_kept_when_relock_fails(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """回锁失败：保留租约（屏幕保持遮蔽，安全方向）并进入重试冷却。"""
    monkeypatch.setattr(unattended, "_lease_held", True)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    monkeypatch.setattr(unattended, "_cu_session_active", no_session)
    monkeypatch.setattr(unattended, "release_unlock_lease", AsyncMock(return_value=False))

    with caplog.at_level(logging.ERROR):
        drive(monkeypatch)

    assert unattended._lease_held is True
    assert unattended._release_retry_at > time.monotonic()
    assert "re-lock failed" in caplog.text


def test_failed_release_is_not_retried_inside_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    """持续回锁失败（如无辅助功能权限）：冷却期内不得每个 tick 重放锁屏按键。"""
    monkeypatch.setattr(unattended, "_lease_held", True)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    monkeypatch.setattr(unattended, "_cu_session_active", no_session)
    release = AsyncMock(return_value=False)
    monkeypatch.setattr(unattended, "release_unlock_lease", release)

    drive(monkeypatch, ticks=4)

    release.assert_awaited_once()


def test_release_retried_after_cooldown_elapses(monkeypatch: pytest.MonkeyPatch) -> None:
    """冷却期满后继续尝试交还（用户可能已补授权限）。"""
    monkeypatch.setattr(unattended, "_lease_held", True)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    monkeypatch.setattr(unattended, "_cu_session_active", no_session)
    release = AsyncMock(return_value=True)
    monkeypatch.setattr(unattended, "release_unlock_lease", release)
    monkeypatch.setattr(unattended, "_release_retry_at", time.monotonic() - 1.0)

    drive(monkeypatch)

    release.assert_awaited_once()
    assert unattended._lease_held is False


def test_lease_void_when_screen_locked_externally(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """屏幕被外部重新锁定：租约自然失效并交还标记（避免帷幕滞留）。"""
    monkeypatch.setattr(unattended, "_lease_held", True)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    monkeypatch.setattr(unattended, "_cu_session_active", has_session)
    set_locked(monkeypatch, True)
    cleared = record_clear(monkeypatch)

    with caplog.at_level(logging.INFO):
        drive(monkeypatch)

    assert cleared == [True]
    assert unattended._lease_held is False
    assert "screen locked externally" in caplog.text


def test_lease_dropped_without_relock_when_owner_takes_curtain_down(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """主人撤下帷幕 = 人在现场：只交还租约位，绝不把屏幕锁在主人面前。"""
    monkeypatch.setattr(unattended, "_lease_held", True)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state(active=False))
    monkeypatch.setattr(unattended, "_cu_session_active", no_session)
    release = AsyncMock()
    monkeypatch.setattr(unattended, "release_unlock_lease", release)
    cleared = record_clear(monkeypatch)

    with caplog.at_level(logging.INFO):
        drive(monkeypatch)

    release.assert_not_awaited()
    assert cleared == [True]
    assert unattended._lease_held is False
    assert "curtain taken down by the owner" in caplog.text


def test_orphaned_lease_with_curtain_up_is_adopted(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """上一进程遗留租约位且帷幕仍在：接管，由首个 tick 回锁后交还。"""
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state(pending_auto_unlock=True))
    cleared = record_clear(monkeypatch)

    with caplog.at_level(logging.WARNING):
        unattended._adopt_orphaned_lease()

    assert unattended._lease_held is True
    assert cleared == []
    assert "adopted an orphaned lease" in caplog.text


def test_orphaned_lease_without_curtain_is_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    """遗留租约位但帷幕已不在：无物可护，直接清除，避免污染下一次自动帷幕。"""
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state(active=False, pending_auto_unlock=True))
    cleared = record_clear(monkeypatch)

    unattended._adopt_orphaned_lease()

    assert unattended._lease_held is False
    assert cleared == [True]


@pytest.mark.parametrize("state", [None, make_state(pending_auto_unlock=False)])
def test_no_orphaned_lease_is_a_noop(monkeypatch: pytest.MonkeyPatch, state: CurtainBridgeState | None) -> None:
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: state)
    cleared = record_clear(monkeypatch)

    unattended._adopt_orphaned_lease()

    assert unattended._lease_held is False
    assert cleared == []


def test_lease_reset_when_bridge_file_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """状态桥缺失（非桌面端部署）：租约状态复位，零成本空转。"""
    monkeypatch.setattr(unattended, "_lease_held", True)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: None)

    drive(monkeypatch)

    assert unattended._lease_held is False
