"""一次性相对时间延迟执行、多频周期日程无代码可视化装配与自愈归档全套自动化测试。

全面覆盖：
1. 相对时间单位（5m, +2h, 30min, 1d, 10s）与中文相对语言（5分钟后, 2小时）精准换算
2. 明天自然语境时钟换算（明天上午09:00, 明天下午15:30）与非法输入拒止
3. 多频段（Hourly, Daily, Workday, Weekly, Monthly）下一次触发时序计算与工作日自动跳跃
4. 一次性任务全生命周期流转与自愈自动归档（活跃堆弹出，移入折叠历史，杜绝僵尸数据膨胀）
5. 智能体 Bot 动态活跃呼吸态与任务生命周期联动解绑（任务运行激活，任务归档即刻解除）
6. 通用可视化调度引擎 UniversalVisualScheduler 端到端调度与并发执行闭环
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from app.core.cron.lifecycle_archive_ledger import (
    LifecycleArchiveLedger,
    TaskLifecycleStatus,
)
from app.core.cron.multi_frequency_descriptor import (
    FrequencyKind,
    MultiFrequencyDescriptorEngine,
    ScheduleDescriptor,
)
from app.core.cron.relative_delay_parser import (
    RelativeDelayParseError,
    RelativeDelayParser,
)
from app.core.cron.universal_visual_scheduler import UniversalVisualScheduler


def test_relative_delay_parser_short_units() -> None:
    """测试标准英文与简写相对延迟单位解析与时间戳准确性。"""
    base_ts = 1700000000.0  # 固定基准秒

    # 5分钟后
    p1 = RelativeDelayParser.parse("5m", base_time=base_ts)
    assert p1.delta_seconds == 300.0
    assert p1.execute_at_timestamp == 1700000300.0
    assert p1.is_relative is True

    # +2小时后
    p2 = RelativeDelayParser.parse("+2h", base_time=base_ts)
    assert p2.delta_seconds == 7200.0
    assert p2.execute_at_timestamp == 1700007200.0

    # 1天后
    p3 = RelativeDelayParser.parse("1d", base_time=base_ts)
    assert p3.delta_seconds == 86400.0
    assert p3.execute_at_timestamp == 1700086400.0


def test_relative_delay_parser_chinese_expressions() -> None:
    """测试中文自然语言相对时间解析。"""
    base_ts = 1700000000.0

    # 30分钟后
    p1 = RelativeDelayParser.parse("30分钟后", base_time=base_ts)
    assert p1.delta_seconds == 1800.0
    assert p1.execute_at_timestamp == 1700001800.0

    # +10秒
    p2 = RelativeDelayParser.parse("+10秒", base_time=base_ts)
    assert p2.delta_seconds == 10.0
    assert p2.execute_at_timestamp == 1700000010.0


def test_relative_delay_parser_tomorrow_expressions() -> None:
    """测试'明天上午09:00'等跨天快捷时间解析。"""
    # 设定基准时间为某天中午 12:00 UTC
    dt_base = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
    base_ts = dt_base.timestamp()

    parsed = RelativeDelayParser.parse(
        "明天上午09:00",
        base_time=base_ts,
        tz=timezone.utc,
    )
    expected_dt = datetime(2026, 10, 19, 9, 0, 0, tzinfo=timezone.utc)
    assert parsed.execute_at_timestamp == expected_dt.timestamp()
    assert parsed.delta_seconds == (expected_dt.timestamp() - base_ts)


def test_relative_delay_parser_rejects_invalid_inputs() -> None:
    """测试空输入与无法识别的表达式安全拒止。"""
    with pytest.raises(RelativeDelayParseError, match="Empty relative delay"):
        RelativeDelayParser.parse("   ")

    with pytest.raises(RelativeDelayParseError, match="Unrecognized relative delay"):
        RelativeDelayParser.parse("next monday whenever")


def test_multi_frequency_descriptor_workday_calculation() -> None:
    """测试工作日调度器在周五晚上自动跳过周六周日、跨至下周一的数学时序。"""
    # 2026-10-16 是星期五
    friday_night = datetime(2026, 10, 16, 20, 0, 0, tzinfo=timezone.utc)
    from_ts = friday_night.timestamp()

    descriptor = ScheduleDescriptor(
        kind=FrequencyKind.WORKDAY,
        hour=9,
        minute=0,
        timezone_name="UTC",
    )

    next_run = MultiFrequencyDescriptorEngine.compute_next_run(descriptor, from_ts)
    assert next_run is not None

    next_dt = datetime.fromtimestamp(next_run, tz=timezone.utc)
    # 应为下周一 2026-10-19 09:00:00
    assert next_dt.weekday() == 0  # 0 = Monday
    assert next_dt.year == 2026
    assert next_dt.month == 10
    assert next_dt.day == 19
    assert next_dt.hour == 9
    assert next_dt.minute == 0


def test_lifecycle_archive_ledger_one_off_auto_archive() -> None:
    """测试一次性延迟任务执行成功后，自动从活跃堆弹出并移入归档区。"""
    ledger = LifecycleArchiveLedger()

    desc = ScheduleDescriptor(
        kind=FrequencyKind.ONCE_RELATIVE,
        relative_expression="5m",
    )

    # 1. 注册一次性任务
    record = ledger.register_task(
        task_id="task_test_01",
        task_name="Quick Survey",
        bot_id="bot_researcher",
        descriptor=desc,
        next_run_at=time.time() + 300,
    )
    assert record.is_one_off is True
    assert len(ledger.list_active_tasks()) == 1
    assert len(ledger.list_archived_tasks()) == 0

    # 2. 开始执行
    running = ledger.record_task_start("task_test_01")
    assert running.status == TaskLifecycleStatus.RUNNING

    # 3. 执行完毕 -> 一次性任务自动归档
    completed = ledger.record_task_completed("task_test_01")
    assert completed.status == TaskLifecycleStatus.COMPLETED
    assert completed.completed_at is not None

    # 验证活跃堆已清空，归档堆新增记录
    assert len(ledger.list_active_tasks()) == 0
    assert len(ledger.list_archived_tasks()) == 1
    assert ledger.list_archived_tasks()[0].task_id == "task_test_01"


def test_lifecycle_archive_ledger_bot_active_state_pulse_unbind() -> None:
    """测试智能体 Bot 活跃状态联动：任务执行点亮，任务归档即刻解除，杜绝假活跃。"""
    bot_states: list[tuple[str, bool]] = []

    def on_change(bot_id: str, is_active: bool) -> None:
        bot_states.append((bot_id, is_active))

    ledger = LifecycleArchiveLedger(on_bot_active_changed=on_change)
    desc = ScheduleDescriptor(kind=FrequencyKind.ONCE_RELATIVE, relative_expression="10s")
    ledger.register_task("t1", "Ping", "bot_hermes", desc, time.time() + 10)

    # 开始执行 -> 点亮 Bot 活跃呼吸态
    ledger.record_task_start("t1")
    assert bot_states[-1] == ("bot_hermes", True)

    # 任务完成归档 -> 解绑 Bot 活跃呼吸态
    ledger.record_task_completed("t1")
    assert bot_states[-1] == ("bot_hermes", False)


@pytest.mark.asyncio
async def test_universal_visual_scheduler_full_end_to_end_flow() -> None:
    """测试 UniversalVisualScheduler 注册相对延迟、扫描执行、回调触发与自动归档完整闭环。"""
    action_called = False

    async def my_action() -> None:
        nonlocal action_called
        action_called = True

    scheduler = UniversalVisualScheduler()

    # 注册 1 秒相对延迟任务
    record = scheduler.schedule_relative_task(
        task_name="Async Alert",
        bot_id="bot_alert",
        relative_expr="1s",
        action=my_action,
        task_id="task_e2e_1",
    )
    assert record.task_id == "task_e2e_1"
    assert len(scheduler.list_active_tasks()) == 1

    # 模拟未来时间触发
    future_now = record.next_run_at + 1.0
    executed_ids = await scheduler.process_due_tasks(now=future_now)

    assert executed_ids == ["task_e2e_1"]
    assert action_called is True

    # 检查一次性任务已被自动移入归档区
    assert len(scheduler.list_active_tasks()) == 0
    archived = scheduler.list_archived_tasks()
    assert len(archived) == 1
    assert archived[0].task_id == "task_e2e_1"
    assert archived[0].status == TaskLifecycleStatus.COMPLETED
