"""Window resolvers behind the temporal rule table.

Each resolver turns ``now`` plus one regex match into the final wide
``(since, until)`` window of a marker family: calendar periods (day / week /
month / quarter / year), compound seasons, bounded recent spans, the bare
recency fallback, and relative points. Every window is padded with a spill
margin so adjacent-period memories and timezone skew survive the collect-stage
hard filter.

[INPUT]
- (stdlib only - datetime + re)

[OUTPUT]
- WindowResolver: signature a rule binds to its pattern
- calendar_resolver: calendar-anchored period at a fixed offset from the current one
- stepped_calendar_resolver: previous period whose leading “上” count is the step back
- season_resolver: compound season window (“去年春天” / “last spring”)
- recent_span_resolver: bounded recent span (“最近三个月”)
- recent_fallback_resolver: bare recency marker (“最近” / “recently”)
- relative_resolver: relative point (“三天前” / “3 weeks ago”)

[POS]
Calendar and numeric arithmetic behind temporal_window's rule table; knows
nothing about patterns, anchors or ranking.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, tzinfo

WindowResolver = Callable[[datetime, re.Match[str]], tuple[datetime, datetime]]
"""Derives the final wide ``(since, until)`` window from ``now`` + one marker match."""

# Spill margins per window family. Wide on purpose: they absorb calendar
# ambiguity, oral sloppiness (“上个月” said on the 1st), and timezone skew
# between the marker's origin and the injected ``now``.
_MARGIN_DAY = timedelta(days=1)
_MARGIN_WEEK = timedelta(days=2)
_MARGIN_MONTH = timedelta(days=5)
_MARGIN_QUARTER = timedelta(days=7)
_MARGIN_YEAR = timedelta(days=15)
_MARGIN_SEASON = timedelta(days=15)
_MARGIN_RECENT = timedelta(days=2)
_RECENT_FALLBACK_SPAN = timedelta(days=30)

_CALENDAR_MARGINS: dict[str, timedelta] = {
    "day": _MARGIN_DAY,
    "week": _MARGIN_WEEK,
    "month": _MARGIN_MONTH,
    "quarter": _MARGIN_QUARTER,
    "year": _MARGIN_YEAR,
}

_SEASON_MONTHS: dict[str, tuple[int, int]] = {
    "spring": (3, 5),
    "summer": (6, 8),
    "autumn": (9, 11),
    "winter": (12, 2),  # spans the year boundary; the end resolves into next year.
}
_SEASON_CANONICAL: dict[str, str] = {
    **dict.fromkeys(("spring", "春天", "春季"), "spring"),
    **dict.fromkeys(("summer", "夏天", "夏季"), "summer"),
    **dict.fromkeys(("autumn", "fall", "秋天", "秋季"), "autumn"),
    **dict.fromkeys(("winter", "冬天", "冬季"), "winter"),
}
_UNIT_DAYS: dict[str, float] = {"day": 1.0, "week": 7.0, "month": 30.0, "year": 365.0}


def _first_of_month(year: int, month: int, tz: tzinfo | None) -> datetime:
    """Month start with overflow normalization (month 13 → next Jan, 0 → prev Dec)."""
    shifted = year * 12 + (month - 1)
    return datetime.combine(date(shifted // 12, shifted % 12 + 1, 1), time.min, tzinfo=tz)


def _month_shift(now: datetime, offset: int) -> tuple[int, int]:
    """``(year, month)`` shifted by whole calendar months."""
    shifted = now.year * 12 + (now.month - 1) + offset
    return shifted // 12, shifted % 12 + 1


def _parse_number(text: str) -> float:
    """Arabic or simple Chinese numeral (1-999) to its numeric value.

    Chinese unit compounds parse positionally: 十二 → 12, 二十 → 20,
    两百三十 → 230. Arabic digits go through unchanged.
    """
    if text.isdigit():
        return float(text)
    digits = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    total, section = 0, 0
    for ch in text:
        if ch in digits:
            section = digits[ch]
        elif ch == "十":
            total += (section or 1) * 10
            section = 0
        else:  # 百
            total += (section or 1) * 100
            section = 0
    return float(total + section)


def _unit_key(unit_text: str) -> str:
    """Normalize an EN or ZH unit token to its ``_UNIT_DAYS`` key."""
    text = unit_text.lower().replace(" ", "").replace("个", "")
    if text in ("day", "days", "天", "日"):
        return "day"
    if text in ("week", "weeks", "周", "星期"):
        return "week"
    if text in ("month", "months", "月"):
        return "month"
    return "year"


def calendar_resolver(kind: str, offset: int) -> WindowResolver:
    """Calendar-anchored window: ``offset`` -1 = previous period, 0 = current.

    Weeks are Monday-anchored; the semantic period is padded by the kind's
    spill margin on both sides so edge-day memories survive the hard filter.
    """

    def resolve(now: datetime, match: re.Match[str]) -> tuple[datetime, datetime]:
        tz = now.tzinfo
        if kind == "day":
            start_day = now.date() + timedelta(days=offset)
            start = datetime.combine(start_day, time.min, tzinfo=tz)
            end = start + timedelta(days=1)
        elif kind == "week":
            monday = now.date() - timedelta(days=now.weekday())
            start = datetime.combine(monday + timedelta(weeks=offset), time.min, tzinfo=tz)
            end = start + timedelta(days=7)
        elif kind == "month":
            y, m = _month_shift(now, offset)
            start = _first_of_month(y, m, tz)
            end = _first_of_month(y, m + 1, tz)
        elif kind == "quarter":
            quarter_first = (now.month - 1) // 3 * 3 + 1
            shifted = now.year * 12 + quarter_first - 1 + offset * 3
            y, m = shifted // 12, shifted % 12 + 1
            start = _first_of_month(y, m, tz)
            end = _first_of_month(y, m + 3, tz)
        else:  # "year"
            start = _first_of_month(now.year + offset, 1, tz)
            end = _first_of_month(now.year + offset + 1, 1, tz)
        margin = _CALENDAR_MARGINS[kind]
        return start - margin, end + margin

    return resolve


def stepped_calendar_resolver(kind: str) -> WindowResolver:
    """Previous-period marker whose leading “上” count is the step back: 上周 → -1, 上上周 → -2.

    The English “last / previous” alternative has no ``back`` group and steps back once.
    """

    def resolve(now: datetime, match: re.Match[str]) -> tuple[datetime, datetime]:
        steps = len(match.group("back") or "上")
        return calendar_resolver(kind, -steps)(now, match)

    return resolve


def season_resolver() -> WindowResolver:
    """Compound season window (“去年春天” / “last spring”): anchor-year months ± 15d."""

    def resolve(now: datetime, match: re.Match[str]) -> tuple[datetime, datetime]:
        season = _SEASON_CANONICAL[match.group("season").lower()]
        year_offset = -1 if match.group("ctx").lower() in ("last", "去年") else 0
        year = now.year + year_offset
        start_month, end_month = _SEASON_MONTHS[season]
        tz = now.tzinfo
        start = _first_of_month(year, start_month, tz)
        # Winter crosses the year boundary: December of the anchor year into
        # February of the next one.
        end = _first_of_month(year if season != "winter" else year + 1, end_month + 1, tz)
        return start - _MARGIN_SEASON, end + _MARGIN_SEASON

    return resolve


def recent_span_resolver() -> WindowResolver:
    """Span window (“最近三个月” / “last 3 months”): ``[now - N units, now]`` + 2d spill."""

    def resolve(now: datetime, match: re.Match[str]) -> tuple[datetime, datetime]:
        units = _parse_number(match.group("n"))
        span = timedelta(days=_UNIT_DAYS[_unit_key(match.group("unit"))] * units)
        return now - span - _MARGIN_RECENT, now + _MARGIN_RECENT

    return resolve


def recent_fallback_resolver() -> WindowResolver:
    """Bare “最近 / recently”: a 30-day window buys most of the pruning value."""

    def resolve(now: datetime, match: re.Match[str]) -> tuple[datetime, datetime]:
        return now - _RECENT_FALLBACK_SPAN - _MARGIN_RECENT, now + _MARGIN_RECENT

    return resolve


def relative_resolver() -> WindowResolver:
    """Point marker (“三天前” / “3 weeks ago”): center ± max(1d, span/4) spill.

    Relative points are fuzzy by nature: “三天前” crosses day boundaries, so
    the spill grows with the unit scale (day → 1d, month → 7.5d, year → 91d).
    """

    def resolve(now: datetime, match: re.Match[str]) -> tuple[datetime, datetime]:
        span_days = _UNIT_DAYS[_unit_key(match.group("unit"))] * _parse_number(match.group("n"))
        center = now - timedelta(days=span_days)
        spill = timedelta(days=max(1.0, span_days / 4))
        return center - spill, center + spill

    return resolve
