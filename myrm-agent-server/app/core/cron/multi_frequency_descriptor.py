"""多频段周期日程无代码装配描述符与时序计算引擎。

支持 One-off 相对/绝对延迟、每小时、每天、工作日、每周、每月等高频生活/工作周期，
提供无代码表单描述符与下一次执行时刻的精确数学推演，彻底免除手写 Linux Cron 的心智负担。
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.core.cron.relative_delay_parser import RelativeDelayParser


class FrequencyKind(StrEnum):
    """任务运行频度枚举。"""

    ONCE_RELATIVE = "once_relative"
    ONCE_ABSOLUTE = "once_absolute"
    HOURLY = "hourly"
    DAILY = "daily"
    WORKDAY = "workday"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass(frozen=True, slots=True)
class ScheduleDescriptor:
    """多频段调度配置结构化描述符实体。"""

    kind: FrequencyKind
    minute: int = 0
    hour: int = 0
    days_of_week: tuple[int, ...] = ()  # 0=周一, 6=周日
    days_of_month: tuple[int, ...] = ()  # 1..31
    relative_expression: str | None = None
    absolute_timestamp: float | None = None
    timezone_name: str = "UTC"


class ScheduleCalculationError(ValueError):
    """时序推算错误。"""


class MultiFrequencyDescriptorEngine:
    """多频段调度时序计算与摘要引擎。"""

    @classmethod
    def resolve_zone(cls, tz_name: str) -> timezone | ZoneInfo:
        """安全解析时区。"""
        if tz_name.upper() in ("UTC", "Z"):
            return timezone.utc
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return timezone.utc

    @classmethod
    def compute_next_run(
        cls,
        descriptor: ScheduleDescriptor,
        from_timestamp: float,
    ) -> float | None:
        """计算给定基准时间戳之后的下一次精确触发时刻（秒）。

        若为一次性任务且已过期，返回 None。
        """
        tz = cls.resolve_zone(descriptor.timezone_name)
        now_dt = datetime.fromtimestamp(from_timestamp, tz=tz)

        # 1. 一次性相对时间任务
        if descriptor.kind == FrequencyKind.ONCE_RELATIVE:
            if not descriptor.relative_expression:
                raise ScheduleCalculationError("relative_expression is required for ONCE_RELATIVE")
            parsed = RelativeDelayParser.parse(
                descriptor.relative_expression,
                base_time=from_timestamp,
                tz=timezone.utc if tz == timezone.utc else None,
            )
            return parsed.execute_at_timestamp if parsed.execute_at_timestamp > from_timestamp else None

        # 2. 一次性绝对时间任务
        if descriptor.kind == FrequencyKind.ONCE_ABSOLUTE:
            if descriptor.absolute_timestamp is None:
                raise ScheduleCalculationError("absolute_timestamp is required for ONCE_ABSOLUTE")
            return descriptor.absolute_timestamp if descriptor.absolute_timestamp > from_timestamp else None

        # 3. 每小时固定分钟 (Hourly)
        if descriptor.kind == FrequencyKind.HOURLY:
            candidate = now_dt.replace(minute=descriptor.minute, second=0, microsecond=0)
            if candidate.timestamp() <= from_timestamp:
                candidate += timedelta(hours=1)
            return candidate.timestamp()

        # 4. 每天固定时间 (Daily)
        if descriptor.kind == FrequencyKind.DAILY:
            candidate = now_dt.replace(
                hour=descriptor.hour,
                minute=descriptor.minute,
                second=0,
                microsecond=0,
            )
            if candidate.timestamp() <= from_timestamp:
                candidate += timedelta(days=1)
            return candidate.timestamp()

        # 5. 每个工作日（周一至周五）(Workday)
        if descriptor.kind == FrequencyKind.WORKDAY:
            candidate = now_dt.replace(
                hour=descriptor.hour,
                minute=descriptor.minute,
                second=0,
                microsecond=0,
            )
            # 若今日时间已过，从明日算起
            if candidate.timestamp() <= from_timestamp:
                candidate += timedelta(days=1)
            # 循环跳过周六(5)与周日(6)
            while candidate.weekday() in (5, 6):
                candidate += timedelta(days=1)
            return candidate.timestamp()

        # 6. 每周指定周几 (Weekly)
        if descriptor.kind == FrequencyKind.WEEKLY:
            target_weekdays = descriptor.days_of_week or (0,)  # 默认周一
            candidate = now_dt.replace(
                hour=descriptor.hour,
                minute=descriptor.minute,
                second=0,
                microsecond=0,
            )
            if candidate.timestamp() <= from_timestamp:
                candidate += timedelta(days=1)
            for _ in range(14):  # 最多两周内必命中
                if candidate.weekday() in target_weekdays:
                    return candidate.timestamp()
                candidate += timedelta(days=1)
            return candidate.timestamp()

        # 7. 每月指定几号 (Monthly)
        if descriptor.kind == FrequencyKind.MONTHLY:
            target_days = descriptor.days_of_month or (1,)
            target_day = target_days[0]
            # 寻找当前月或下月的该日
            year = now_dt.year
            month = now_dt.month

            for _ in range(24):  # 跨月搜索
                max_days = calendar.monthrange(year, month)[1]
                effective_day = min(target_day, max_days)
                candidate_date = datetime(
                    year,
                    month,
                    effective_day,
                    descriptor.hour,
                    descriptor.minute,
                    0,
                    tzinfo=tz,
                )
                if candidate_date.timestamp() > from_timestamp:
                    return candidate_date.timestamp()
                # 递增一个月
                if month == 12:
                    year += 1
                    month = 1
                else:
                    month += 1

            return None

        raise ScheduleCalculationError(f"Unsupported frequency kind: {descriptor.kind}")

    @classmethod
    def format_summary(cls, descriptor: ScheduleDescriptor) -> str:
        """生成人类友好的调度计划中文摘要。"""
        time_str = f"{descriptor.hour:02d}:{descriptor.minute:02d}"
        match descriptor.kind:
            case FrequencyKind.ONCE_RELATIVE:
                return f"一次性任务（相对延迟: {descriptor.relative_expression}）"
            case FrequencyKind.ONCE_ABSOLUTE:
                dt_str = (
                    datetime.fromtimestamp(descriptor.absolute_timestamp, tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M:%S UTC"
                    )
                    if descriptor.absolute_timestamp
                    else "未设置"
                )
                return f"一次性任务（时间: {dt_str}）"
            case FrequencyKind.HOURLY:
                return f"每小时第 {descriptor.minute} 分钟执行"
            case FrequencyKind.DAILY:
                return f"每天 {time_str} 执行"
            case FrequencyKind.WORKDAY:
                return f"每个工作日 {time_str} 执行"
            case FrequencyKind.WEEKLY:
                week_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                days = ", ".join(week_names[d] for d in descriptor.days_of_week if 0 <= d <= 6) or "周一"
                return f"每{days} {time_str} 执行"
            case FrequencyKind.MONTHLY:
                days = ", ".join(f"{d}日" for d in descriptor.days_of_month if 1 <= d <= 31) or "1日"
                return f"每月{days} {time_str} 执行"
            case _:
                return "未知调度模式"
