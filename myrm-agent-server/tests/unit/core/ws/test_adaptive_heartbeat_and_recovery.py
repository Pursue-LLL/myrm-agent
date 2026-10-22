"""WebSocket 极速心跳探测、死线截断与带抖动指数退避连接恢复全套自动化测试套件。

全面覆盖：
1. 正常 Ping/Pong 往返结算与 RTT 计算；
2. 2s 心跳死线超时，毫秒级强制切断并关闭 socket (code=1008)；
3. 会话负载自适应升降档（活跃态 2s vs 空闲态 15s）；
4. 带抖动指数退避阶梯翻倍与 10s 封顶验证 (0.5s -> 1s -> 2s -> 4s -> 8s -> 10s)；
5. 随机抖动因子严格限制在 [50%, 100%] 之间，杜绝惊群雪崩；
6. 10s 档重试耗尽后优雅停机转入 disconnected，避免无意义死循环；
7. 浏览器 offline 立即挂起与 online 立即重置自愈；
8. 用户态“立即重连” 500ms CAS 防抖锁与等待打断机制；
9. 状态机发布-订阅通知与注销隔离机制。
"""

from __future__ import annotations

import pytest

from app.api.ws.connection_controller import (
    BackoffConfig,
    ConnectionController,
    ConnectionState,
    JitteredBackoffScheduler,
)
from app.api.ws.heartbeat import (
    AdaptiveHeartbeatController,
    HeartbeatConfig,
)


@pytest.mark.asyncio
async def test_adaptive_heartbeat_healthy_cycle() -> None:
    """测试正常心跳周期：发送 Ping 并在死线内收到 Pong，RTT 计算准确且连接保持。"""
    ping_count = 0
    close_called = False

    async def mock_ping() -> None:
        nonlocal ping_count
        ping_count += 1

    async def mock_close(code: int, reason: str) -> None:
        nonlocal close_called
        close_called = True

    config = HeartbeatConfig(
        active_interval_seconds=2.0,
        pong_deadline_seconds=2.0,
    )
    controller = AdaptiveHeartbeatController(
        config=config,
        ping_sender=mock_ping,
        socket_closer=mock_close,
    )

    # 1. 触发第一次心跳 tick（此时尚未等待 Pong）
    now_t0 = 100.0
    healthy = await controller.execute_heartbeat_tick(now=now_t0)
    assert healthy is True
    assert ping_count == 1
    assert controller.is_waiting_for_pong is True
    assert controller.stats.total_pings_sent == 1

    # 2. 模拟客户端在 50ms 后返回 Pong
    rtt = controller.record_pong_received(receive_timestamp=now_t0 + 0.05)
    assert rtt == pytest.approx(50.0, rel=1e-2)
    assert controller.is_waiting_for_pong is False
    assert controller.stats.total_pongs_received == 1
    assert close_called is False


@pytest.mark.asyncio
async def test_adaptive_heartbeat_deadline_timeout_terminates_socket() -> None:
    """测试死线超时：超过 2s 未收到 Pong，控制器在下一轮 tick 毫秒级强行关闭 socket。"""
    closed_codes: list[int] = []
    closed_reasons: list[str] = []

    async def mock_close(code: int, reason: str) -> None:
        closed_codes.append(code)
        closed_reasons.append(reason)

    config = HeartbeatConfig(
        active_interval_seconds=2.0,
        pong_deadline_seconds=2.0,
        max_missed_pongs=1,
    )
    controller = AdaptiveHeartbeatController(
        config=config,
        socket_closer=mock_close,
    )

    now_t0 = 200.0
    await controller.execute_heartbeat_tick(now=now_t0)
    assert controller.is_waiting_for_pong is True

    # 模拟经过 2.1s（超过 2s 死线）触发下一轮 tick，客户端未响应 Pong
    now_t1 = now_t0 + 2.1
    healthy = await controller.execute_heartbeat_tick(now=now_t1)

    assert healthy is False
    assert len(closed_codes) == 1
    assert closed_codes[0] == 1008
    assert "Heartbeat deadline exceeded" in closed_reasons[0]
    assert controller.stats.dead_links_terminated == 1


def test_adaptive_heartbeat_workload_state_adaptation() -> None:
    """测试会话负载自适应：活跃任务保持 2s 高频，长时间空闲升档为 15s 省电。"""
    config = HeartbeatConfig(
        active_interval_seconds=2.0,
        idle_interval_seconds=15.0,
    )
    controller = AdaptiveHeartbeatController(config=config)

    assert controller.stats.current_interval_seconds == 2.0

    # 切换为空闲
    controller.mark_workload_state(is_active=False)
    assert controller.stats.current_interval_seconds == 15.0

    # 恢复活跃
    controller.mark_workload_state(is_active=True)
    assert controller.stats.current_interval_seconds == 2.0


def test_jittered_backoff_tiers_and_ceiling() -> None:
    """测试指数退避阶梯：500ms ➔ 1s ➔ 2s ➔ 4s ➔ 8s ➔ 10s 封顶。"""
    scheduler = JitteredBackoffScheduler()

    # 使用 seed=1.0（取上限 100%），依次验证严格的阶梯上限
    delays = [scheduler.next_backoff_delay(random_seed=1.0) for _ in range(6)]
    expected_tiers = [0.5, 1.0, 2.0, 4.0, 8.0, 10.0]

    assert delays == expected_tiers


def test_jittered_backoff_random_range_clamp() -> None:
    """测试抖动区间：实际延迟严格约束在 [50%, 100%] 之间。"""
    scheduler = JitteredBackoffScheduler(
        config=BackoffConfig(jitter_min_ratio=0.5, jitter_max_ratio=1.0)
    )

    # 种子 0.0 -> 取 50% 下限 (0.5 * 0.5 = 0.25s)
    delay_min = scheduler.next_backoff_delay(random_seed=0.0)
    assert delay_min == pytest.approx(0.25, abs=0.01)

    # 种子 1.0 -> 取 100% 上限 (1.0 * 1.0 = 1.0s)
    delay_max = scheduler.next_backoff_delay(random_seed=1.0)
    assert delay_max == pytest.approx(1.0, abs=0.01)


def test_jittered_backoff_exhaustion_stops_retries() -> None:
    """测试重试耗尽：10s 档重试失败后停止盲目重试，is_exhausted 为 True。"""
    scheduler = JitteredBackoffScheduler()

    # 连续消耗完 6 档重试
    for _ in range(6):
        d = scheduler.next_backoff_delay(random_seed=0.8)
        assert d > 0.0

    # 第 7 次触发 -> 耗尽
    next_delay = scheduler.next_backoff_delay(random_seed=0.8)
    assert next_delay == 0.0
    assert scheduler.is_exhausted is True

    # reset 后恢复
    scheduler.reset()
    assert scheduler.is_exhausted is False
    assert scheduler.current_attempt == 0


def test_connection_controller_offline_online_transitions() -> None:
    """测试网络在线/离线感知事件联动。"""
    controller = ConnectionController()
    controller.mark_connected()
    assert controller.state == ConnectionState.CONNECTED

    # 网络断开 (offline)
    controller.on_browser_offline()
    assert controller.is_online is False
    offline_state: ConnectionState = controller.state
    assert offline_state == ConnectionState.DISCONNECTED

    # 离线状态下调用 mark_disconnected，绝不进入 connecting
    delay = controller.mark_disconnected()
    assert delay == 0.0
    disconnected_state: ConnectionState = controller.state
    assert disconnected_state == ConnectionState.DISCONNECTED

    # 网络恢复 (online) -> 立即转入 CONNECTING 并重置阶梯
    first_delay = controller.on_browser_online()
    assert controller.is_online is True
    assert controller.state == ConnectionState.CONNECTING
    assert 0.25 <= first_delay <= 0.5


def test_connection_controller_reconnect_now_cas_debounce() -> None:
    """测试用户点击立即重连：500ms CAS 防抖与打断重置。"""
    controller = ConnectionController()
    controller.mark_disconnected()

    # 首次点击 -> 成功触发立即重连
    ok1 = controller.reconnect_now()
    assert ok1 is True
    assert controller.state == ConnectionState.CONNECTING
    assert controller.scheduler.current_attempt == 0

    # 50ms 再次狂点 -> 触发防抖锁定
    ok2 = controller.reconnect_now()
    assert ok2 is False


def test_connection_controller_subscriber_notification() -> None:
    """测试状态机观察者发布订阅与注销清理。"""
    controller = ConnectionController()
    recorded_states: list[ConnectionState] = []

    unsubscribe = controller.subscribe(lambda st: recorded_states.append(st))

    controller.mark_connected()
    controller.mark_disconnected()

    assert ConnectionState.CONNECTED in recorded_states
    assert ConnectionState.CONNECTING in recorded_states

    # 注销后不再接收通知
    recorded_states.clear()
    unsubscribe()
    controller.mark_connected()
    assert len(recorded_states) == 0
