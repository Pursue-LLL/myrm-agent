"""Tests for the lock probe and the password-typing unlock primitive.

[INPUT]
- app.services.locked_use.service.MacScreenUnlocker（POS: 锁屏探测 / 解锁 / 单次回锁原语）

[OUTPUT]
- 探测语义（仅确定 LOCKED 才算已锁；硬件输入空闲不足或探测未知即视为人在机前）、
  解锁串行化与持锁复探锁态/在场、密码仅经 stdin、唤醒键先于密码且不产生字符、阻塞子进程不卡事件循环的断言

[POS]
与 test_service_lease.py（回锁校验与租约生命周期）互补；Keychain 密码读取见
test_keychain_password.py。
"""

import asyncio
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.api.security import ScreenLockState, hid_idle_seconds

from app.services.locked_use import service
from app.services.locked_use.service import PRESENCE_IDLE_THRESHOLD_SECONDS, MacScreenUnlocker
from tests.support.curtain_watcher import set_hid_idle


@pytest.fixture(autouse=True)
def _no_unlock_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    """键入前后的真实等待与断言无关，置零避免每个用例白等 1.5 秒。"""
    monkeypatch.setattr(service, "_UNLOCK_WAKE_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(service, "_UNLOCK_SETTLE_DELAY_SECONDS", 0.0)


class TestIsLocked:
    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (ScreenLockState.LOCKED, True),
            (ScreenLockState.UNLOCKED, False),
            # 显示器休眠但会话未锁、探测失败：都不得当作「已锁」去盲打密码。
            (ScreenLockState.SLEEPING, False),
            (ScreenLockState.UNKNOWN, False),
        ],
    )
    def test_only_definite_lock_counts(self, state: ScreenLockState, expected: bool) -> None:
        detector = MagicMock()
        detector.get_state.return_value = state
        with patch("app.services.locked_use.service.get_default_screen_detector", return_value=detector):
            assert MacScreenUnlocker.is_locked() is expected
        detector.get_state.assert_called_once_with(force_refresh=True)

    @pytest.mark.skipif(sys.platform != "darwin", reason="native Quartz probe is macOS-only")
    def test_live_probe_is_native_and_fast(self) -> None:
        """真实 OS 调用（无 mock）：稳态下原生探针是亚毫秒级，而非数百毫秒的 osascript 进程。"""
        assert isinstance(MacScreenUnlocker.is_locked(), bool)  # 预热：首次调用含一次性 Quartz 导入
        rounds = 20
        started = time.perf_counter()
        for _ in range(rounds):
            MacScreenUnlocker.is_locked()
        mean_seconds = (time.perf_counter() - started) / rounds
        assert mean_seconds < 0.02


class TestUserPresence:
    @pytest.mark.parametrize(
        ("idle", "present"),
        [
            (None, True),  # 探测失败：无法证明无人，就不盲打密码
            (0.0, True),
            (PRESENCE_IDLE_THRESHOLD_SECONDS - 0.1, True),
            (PRESENCE_IDLE_THRESHOLD_SECONDS, False),  # 恰满阈值即视为已离开
            (3600.0, False),
        ],
    )
    def test_idle_threshold_decides_presence(self, monkeypatch: pytest.MonkeyPatch, idle: float | None, present: bool) -> None:
        set_hid_idle(monkeypatch, idle)
        assert MacScreenUnlocker.user_present() is present

    @pytest.mark.skipif(sys.platform != "darwin", reason="native HID probe is macOS-only")
    def test_live_probe_yields_a_definite_answer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """真实 OS 调用（无 mock）：harness 探针经 facade 可达，返回确定的布尔值而非抛错。"""
        monkeypatch.setattr(service, "hid_idle_seconds", hid_idle_seconds)  # 换回真实探针，覆盖 autouse 桩
        assert isinstance(MacScreenUnlocker.user_present(), bool)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("idle", [None, 2.0])
    @patch.object(MacScreenUnlocker, "get_password")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    async def test_unlock_types_nothing_while_a_user_is_present(
        self,
        mock_run: MagicMock,
        mock_popen: MagicMock,
        mock_is_locked: MagicMock,
        mock_get_password: MagicMock,
        idle: float | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """人在机前：不键入、不唤醒显示器，连钥匙串里的密码都不读。"""
        set_hid_idle(monkeypatch, idle)
        assert await MacScreenUnlocker.unlock() is False
        mock_get_password.assert_not_called()
        mock_popen.assert_not_called()
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "get_password", return_value="my_password")
    @patch.object(MacScreenUnlocker, "is_locked", side_effect=[True, False])
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    async def test_unlock_resumes_once_idle_threshold_is_reached(
        self,
        mock_run: MagicMock,
        mock_popen: MagicMock,
        mock_is_locked: MagicMock,
        mock_get_password: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """阳性对照：与上例同一局面，仅空闲时长满阈值即照常键入（证明上例的拒绝出自在场门禁）。"""
        mock_run.return_value = subprocess.CompletedProcess([], returncode=0)
        set_hid_idle(monkeypatch, PRESENCE_IDLE_THRESHOLD_SECONDS)
        assert await MacScreenUnlocker.unlock() is True
        mock_run.assert_called_once()


class TestMacScreenUnlocker:
    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "get_password", return_value="my_password")
    @patch.object(MacScreenUnlocker, "is_locked", side_effect=[True, False])  # 入口仍锁定 → 键入后已解锁
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    async def test_unlock_success(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_is_locked: MagicMock, mock_get_password: MagicMock
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], returncode=0)
        assert await MacScreenUnlocker.unlock() is True
        assert mock_popen.called
        assert mock_run.called

    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "get_password", return_value="my_password")
    @patch.object(MacScreenUnlocker, "is_locked", side_effect=[True, False])
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    async def test_unlock_feeds_password_over_stdin_not_argv(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_is_locked: MagicMock, mock_get_password: MagicMock
    ) -> None:
        """密码只经 stdin 进入 osascript：argv 对同机其他进程可见。"""
        mock_run.return_value = subprocess.CompletedProcess([], returncode=0)
        await MacScreenUnlocker.unlock()
        args, kwargs = mock_run.call_args
        assert args[0] == ["osascript", "-"]
        assert "my_password" in kwargs["input"]
        assert all("my_password" not in part for part in args[0])

    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "get_password", return_value="my_password")
    @patch.object(MacScreenUnlocker, "is_locked", side_effect=[True, False])
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    async def test_wake_keypress_inserts_no_character(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_is_locked: MagicMock, mock_get_password: MagicMock
    ) -> None:
        """唤醒键先于密码且不产生字符：焦点中的密码框会把可打印键当成密码的第一个字符。"""
        mock_run.return_value = subprocess.CompletedProcess([], returncode=0)
        await MacScreenUnlocker.unlock()
        script = mock_run.call_args.kwargs["input"]
        statements = [
            line.strip().split(" -- ")[0] for line in script.splitlines() if line.strip() and not line.strip().startswith("delay")
        ]
        assert statements == [
            'tell application "System Events"',
            "key code 123",  # Left Arrow：任何键盘布局下键码相同，空输入框里无副作用
            'keystroke "my_password"',
            "key code 36",  # Return
            "end tell",
        ]

    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "get_password")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=False)
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    async def test_unlock_skips_typing_when_already_unlocked(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_is_locked: MagicMock, mock_get_password: MagicMock
    ) -> None:
        """守卫内复探：屏幕已被别处解锁时绝不再键入密码（否则落进前台应用）。"""
        assert await MacScreenUnlocker.unlock() is True
        mock_get_password.assert_not_called()
        mock_popen.assert_not_called()
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_concurrent_unlocks_type_password_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """会话路径与租约 watcher 同秒触发：仅一方键入，另一方等待后见已解锁。"""
        monkeypatch.setattr(service, "_unlock_guard", asyncio.Lock())
        state = {"locked": True}
        typed: list[bool] = []

        async def _type_password() -> bool:
            typed.append(True)
            await asyncio.sleep(0)  # 让出事件循环，给另一方抢入的机会
            state["locked"] = False
            return True

        monkeypatch.setattr(MacScreenUnlocker, "is_locked", staticmethod(lambda: state["locked"]))
        monkeypatch.setattr(MacScreenUnlocker, "_type_password", staticmethod(_type_password))

        results = await asyncio.gather(MacScreenUnlocker.unlock(), MacScreenUnlocker.unlock())

        assert list(results) == [True, True]
        assert len(typed) == 1

    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "get_password", return_value="my_password")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    async def test_unlock_command_failure_reports_false(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_is_locked: MagicMock, mock_get_password: MagicMock
    ) -> None:
        """osascript 非零退出：立即判定失败，不再等二次探测。"""
        mock_run.return_value = subprocess.CompletedProcess([], returncode=1)
        assert await MacScreenUnlocker.unlock() is False

    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)
    @patch.object(MacScreenUnlocker, "get_password", return_value=None)
    async def test_unlock_no_password(self, mock_get_password: MagicMock, mock_is_locked: MagicMock) -> None:
        assert await MacScreenUnlocker.unlock() is False

    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "get_password", return_value="my_password")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)  # 键入后仍锁定（密码错误）
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    async def test_unlock_failure(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_is_locked: MagicMock, mock_get_password: MagicMock
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], returncode=0)
        assert await MacScreenUnlocker.unlock() is False

    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "get_password", return_value="my_password")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    async def test_unlock_exception(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_is_locked: MagicMock, mock_get_password: MagicMock
    ) -> None:
        mock_run.side_effect = OSError("osascript unavailable")
        assert await MacScreenUnlocker.unlock() is False

    @pytest.mark.asyncio
    async def test_blocking_subprocess_runs_off_the_event_loop(self) -> None:
        """osascript 键入约 2 秒：必须在线程里跑，事件循环不得被冻结。"""
        stamps: list[float] = []

        def _slow_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            time.sleep(0.3)
            return subprocess.CompletedProcess([], returncode=0)

        async def _ticker() -> None:
            while True:
                stamps.append(time.perf_counter())
                await asyncio.sleep(0.01)

        ticker = asyncio.create_task(_ticker())
        try:
            with (
                patch.object(MacScreenUnlocker, "get_password", return_value="pw"),
                patch.object(MacScreenUnlocker, "is_locked", side_effect=[True, False]),
                patch("subprocess.Popen"),
                patch("subprocess.run", side_effect=_slow_run),
            ):
                assert await MacScreenUnlocker.unlock() is True
        finally:
            ticker.cancel()
        # 若 subprocess.run 在循环线程里阻塞，ticker 几乎得不到调度，相邻 tick 间隔也会 ≥ 0.3 秒。
        assert len(stamps) > 5, "event loop was blocked while osascript ran"
        worst_gap = max(later - earlier for earlier, later in zip(stamps, stamps[1:], strict=False))
        assert worst_gap < 0.2

    @patch("subprocess.run")
    def test_relock(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], returncode=0)
        assert MacScreenUnlocker.relock() is True
        assert mock_run.called
