"""相对时间自然语言与延迟时序解析模块。

提供将 '+5m', '30m', '2h', '1d', '+10分钟', '明天上午09:00' 等相对/快捷时序表达式，
基于基准时间即刻转换为不可变绝对 UTC 时间戳的能力，彻底杜绝服务重启累积漂移。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from typing import ClassVar

# 正则：数字 + 单位简写（如 "5m", "+5m", "30min", "2h", "1d", "10s"）
_SHORT_UNIT_REGEX = re.compile(
    r"^\+?(?P<val>\d+)\s*(?P<unit>s|sec|m|min|h|hr|hour|d|day)s?$",
    re.IGNORECASE,
)

# 正则：中文相对时间（如 "5分钟", "30分钟后", "2小时", "1天后", "10秒"）
_ZH_UNIT_REGEX = re.compile(
    r"^\+?(?P<val>\d+)\s*(?P<unit>秒|分|分钟|小时|钟头|天|日)(?:后|之后)?$"
)

# 正则：明天上午/下午/指定时间（如 "明天上午9点", "明天上午09:00", "明天下午3点", "明天15:30"）
_TOMORROW_REGEX = re.compile(
    r"^明天(?:(?P<period>上午|下午|早上|晚上))?\s*(?P<hour>\d{1,2})(?:[:点时](?P<minute>\d{1,2}))?分?$"
)


class RelativeDelayParseError(ValueError):
    """相对时间解析失败或格式非法异常。"""


@dataclass(frozen=True, slots=True)
class ParsedRelativeDelay:
    """解析后的相对时间延迟不可变实体。"""

    raw_expression: str
    delta_seconds: float
    base_timestamp: float
    execute_at_timestamp: float
    is_relative: bool
    summary_text: str


class RelativeDelayParser:
    """相对时间与延迟表达解析器。"""

    _UNIT_MULTIPLIERS: ClassVar[dict[str, float]] = {
        "s": 1.0,
        "sec": 1.0,
        "秒": 1.0,
        "m": 60.0,
        "min": 60.0,
        "分": 60.0,
        "分钟": 60.0,
        "h": 3600.0,
        "hr": 3600.0,
        "hour": 3600.0,
        "小时": 3600.0,
        "钟头": 3600.0,
        "d": 86400.0,
        "day": 86400.0,
        "天": 86400.0,
        "日": 86400.0,
    }

    @classmethod
    def parse(
        cls,
        expression: str,
        *,
        base_time: float | None = None,
        tz: timezone | None = None,
    ) -> ParsedRelativeDelay:
        """将相对时间表达式解析为确定的绝对时间戳。

        参数:
            expression: 相对时间字符串（如 '5m', '+2h', '30分钟后', '明天上午09:00'）
            base_time: 基准时间戳（秒），默认当前系统时间
            tz: 业务时区，默认 UTC
        """
        expr = expression.strip()
        if not expr:
            raise RelativeDelayParseError("Empty relative delay expression.")

        effective_tz = tz or timezone.utc
        now_dt = (
            datetime.fromtimestamp(base_time, tz=effective_tz)
            if base_time is not None
            else datetime.now(tz=effective_tz)
        )
        base_ts = now_dt.timestamp()

        # 1. 尝试匹配西文字符简写：5m, +2h, 30min, 1d 等
        short_match = _SHORT_UNIT_REGEX.match(expr)
        if short_match:
            val = int(short_match.group("val"))
            unit_key = short_match.group("unit").lower()
            multiplier = cls._UNIT_MULTIPLIERS.get(unit_key)
            if multiplier is None:
                raise RelativeDelayParseError(f"Unsupported time unit: '{unit_key}'")

            delta_sec = float(val) * multiplier
            target_ts = base_ts + delta_sec
            summary = f"{val} {unit_key} 后执行"
            return ParsedRelativeDelay(
                raw_expression=expr,
                delta_seconds=delta_sec,
                base_timestamp=base_ts,
                execute_at_timestamp=target_ts,
                is_relative=True,
                summary_text=summary,
            )

        # 2. 尝试匹配中文相对时间：5分钟后, 2小时, 1天后 等
        zh_match = _ZH_UNIT_REGEX.match(expr)
        if zh_match:
            val = int(zh_match.group("val"))
            unit_key = zh_match.group("unit")
            multiplier = cls._UNIT_MULTIPLIERS.get(unit_key)
            if multiplier is None:
                raise RelativeDelayParseError(f"Unsupported Chinese time unit: '{unit_key}'")

            delta_sec = float(val) * multiplier
            target_ts = base_ts + delta_sec
            summary = f"{val}{unit_key}后执行"
            return ParsedRelativeDelay(
                raw_expression=expr,
                delta_seconds=delta_sec,
                base_timestamp=base_ts,
                execute_at_timestamp=target_ts,
                is_relative=True,
                summary_text=summary,
            )

        # 3. 尝试匹配“明天”语义：明天上午9点, 明天15:30 等
        tomorrow_match = _TOMORROW_REGEX.match(expr)
        if tomorrow_match:
            period = tomorrow_match.group("period") or ""
            raw_hour = int(tomorrow_match.group("hour"))
            raw_minute = int(tomorrow_match.group("minute") or 0)

            # 下午/晚上 修正 12 小时制
            hour = raw_hour
            minute = raw_minute
            if period in ("下午", "晚上") and 1 <= hour <= 11:
                hour += 12
            elif period in ("上午", "早上") and hour == 12:
                hour = 0

            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise RelativeDelayParseError(
                    f"Invalid clock time: {raw_hour}:{raw_minute:02d} ({period})"
                )

            tomorrow_date = (now_dt + timedelta(days=1)).date()
            target_dt = datetime.combine(
                tomorrow_date,
                dt_time(hour=hour, minute=minute),
                tzinfo=effective_tz,
            )
            target_ts = target_dt.timestamp()
            delta_sec = max(0.0, target_ts - base_ts)
            summary = f"明天 {hour:02d}:{minute:02d} 执行"

            return ParsedRelativeDelay(
                raw_expression=expr,
                delta_seconds=delta_sec,
                base_timestamp=base_ts,
                execute_at_timestamp=target_ts,
                is_relative=True,
                summary_text=summary,
            )

        raise RelativeDelayParseError(
            f"Unrecognized relative delay expression: '{expr}'. "
            "Examples: '5m', '+2h', '30分钟后', '明天上午09:00'"
        )
