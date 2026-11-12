"""Temporal window derivation for time-scoped memory retrieval.

Derives a wide ``(since, until)`` window from natural-language temporal
markers (English + Chinese) in a query, so time-scoped queries such as
“上个月讨论的部署方案” prune candidates at the collect stage instead of
scanning the full library and relying on result-side temporal reweighting
alone.

Design contract (explicit-scope invariance, mirroring ChannelPruner):
- Derivation only fills boundaries when the caller provided neither
  ``since`` nor ``until``; any explicit boundary wins untouched.
- Windows are deliberately wide: each marker's semantic period is padded
  with a spill margin so adjacent-period memories and timezone skew
  (markers resolve against the caller-injected ``now``) survive the hard
  filter. The window also carries an ``anchor`` that result-side temporal
  proximity reweighting (query_analyzer) centers on, so ranking inside
  the window still narrows: the hard filter prunes, the soft reweight
  ranks.
- Only past-facing markers derive windows; future markers (“明天”,
  “next week”) describe plans rather than recall scope and are ignored,
  as are windows fully in the future (e.g. “今年冬天” asked in autumn
  falls through to the broader “今年” rule instead).
- Stacked “上” steps back one period per character: “上周” is the
  previous week, “上上周” the one before it.

[INPUT]
- .temporal_window_resolvers::WindowResolver, calendar_resolver, stepped_calendar_resolver, season_resolver, recent_span_resolver, recent_fallback_resolver, relative_resolver (POS: calendar and numeric arithmetic that turns one marker match into a wide window)
- (stdlib only - datetime + re)

[OUTPUT]
- TemporalWindow: derived boundaries, proximity anchor and marker metadata
- derive_temporal_window: marker extraction + wide-window derivation

[POS]
Single rule table for time phrases in memory retrieval: one resolved
marker feeds the vector stores' since/until hard filters (collect side)
and query_analyzer's proximity anchor (soft, result side). The window
only prunes what is clearly outside the marker's semantic period, never
ranks inside it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from myrm_agent_harness.toolkits.memory._internal.temporal_window_resolvers import (
    WindowResolver,
    calendar_resolver,
    recent_fallback_resolver,
    recent_span_resolver,
    relative_resolver,
    season_resolver,
    stepped_calendar_resolver,
)

TemporalWindowKind = Literal["day", "week", "month", "quarter", "year", "season", "recent", "relative"]
"""Marker family of a derived window; drives margin selection and trace labels."""


@dataclass(frozen=True, slots=True)
class TemporalWindow:
    """Hard-filter boundaries derived from one past-facing temporal marker.

    Attributes:
        since: Wide-window lower bound (inclusive), in ``now``'s timezone.
        until: Wide-window upper bound: the period end padded by the kind's
        spill margin, in ``now``'s timezone.
        marker: Matched marker text (trace metadata).
        window_kind: Marker family (trace metadata).
        anchor: Point that result-side proximity scoring centers on: the
            period center for finished periods and relative points, ``now``
            for recency markers, ``None`` for the current week / month /
            year, which still contain ``now`` and have no past point to
            center on.
    """

    since: datetime
    until: datetime
    marker: str
    window_kind: TemporalWindowKind
    anchor: datetime | None


@dataclass(frozen=True, slots=True)
class _MarkerRule:
    """One temporal marker pattern bound to its window resolver.

    ``anchored`` is False for periods that still contain ``now`` (this week /
    month / year): they yield a hard-filter window but no proximity anchor.
    """

    kind: TemporalWindowKind
    pattern: re.Pattern[str]
    resolve: WindowResolver
    anchored: bool = True


_RULES: tuple[_MarkerRule, ...] = (
    # Compound seasons first: “去年春天” must win over the bare “去年” rule.
    _MarkerRule(
        "season",
        re.compile(
            r"(?P<ctx>去年|今年|last|this)\s*(?P<season>spring|summer|autumn|fall|winter|春天|春季|夏天|夏季|秋天|秋季|冬天|冬季)",
            re.IGNORECASE,
        ),
        season_resolver(),
    ),
    # Calendar-anchored simple markers, specific before broad.
    _MarkerRule("day", re.compile(r"yesterday|昨天", re.IGNORECASE), calendar_resolver("day", -1)),
    _MarkerRule("day", re.compile(r"前天"), calendar_resolver("day", -2)),
    _MarkerRule("day", re.compile(r"today|今天|当天", re.IGNORECASE), calendar_resolver("day", 0)),
    _MarkerRule(
        "week",
        re.compile(r"(?:last|previous)\s+week|(?P<back>上+)(?:周|星期)", re.IGNORECASE),
        stepped_calendar_resolver("week"),
    ),
    _MarkerRule(
        "week",
        re.compile(r"this\s+week|本周|这周|这一周", re.IGNORECASE),
        calendar_resolver("week", 0),
        anchored=False,
    ),
    _MarkerRule(
        "month",
        re.compile(r"(?:last|previous)\s+month|(?P<back>上+)(?:个月|月)", re.IGNORECASE),
        stepped_calendar_resolver("month"),
    ),
    _MarkerRule(
        "month",
        re.compile(r"this\s+month|本月|这个月|当月", re.IGNORECASE),
        calendar_resolver("month", 0),
        anchored=False,
    ),
    _MarkerRule(
        "quarter",
        re.compile(r"(?:last|previous)\s+quarter|(?P<back>上+)个?季度", re.IGNORECASE),
        stepped_calendar_resolver("quarter"),
    ),
    _MarkerRule(
        "year",
        re.compile(r"last\s+year|previous\s+year|去年", re.IGNORECASE),
        calendar_resolver("year", -1),
    ),
    _MarkerRule(
        "year",
        re.compile(r"this\s+year|今年", re.IGNORECASE),
        calendar_resolver("year", 0),
        anchored=False,
    ),
    # Bounded recent spans before the bare fallback: “最近三天” is a 3-day
    # window, not the 30-day one “最近” alone would buy.
    _MarkerRule(
        "recent",
        re.compile(
            r"(?:最近|过去|近期|近)\s*(?P<n>\d{1,3}|[零一二两三四五六七八九十百]{1,4})\s*"
            r"(?P<unit>个\s*月|天|日|周|星期|年)"
        ),
        recent_span_resolver(),
    ),
    _MarkerRule(
        "recent",
        re.compile(
            r"(?:last|past|in\s+the\s+last)\s+(?P<n>\d{1,3})\s+(?P<unit>days?|weeks?|months?|years?)",
            re.IGNORECASE,
        ),
        recent_span_resolver(),
    ),
    _MarkerRule(
        "recent",
        re.compile(r"recently|最近|近期|不久前|前段时间|这阵子", re.IGNORECASE),
        recent_fallback_resolver(),
    ),
    # Relative points. The ZH month unit requires “个” so “3月前” (March)
    # is never mistaken for “三个月前” (three months ago).
    _MarkerRule(
        "relative",
        re.compile(
            r"(?P<n>\d{1,3}|[零一二两三四五六七八九十百]{1,4})\s*"
            r"(?P<unit>个\s*月|天|日|周|星期|年)\s*(?:之?前|以前)"
        ),
        relative_resolver(),
    ),
    _MarkerRule(
        "relative",
        re.compile(r"(?P<n>\d{1,3})\s+(?P<unit>days?|weeks?|months?|years?)\s+ago", re.IGNORECASE),
        relative_resolver(),
    ),
)


def _proximity_anchor(rule: _MarkerRule, now: datetime, since: datetime, until: datetime) -> datetime | None:
    """Point result-side proximity scoring centers on (see ``TemporalWindow.anchor``).

    Spill margins are symmetric for every non-recency kind, so the window
    midpoint is the semantic period's center.
    """
    if not rule.anchored:
        return None
    if rule.kind == "recent":
        return now
    return since + (until - since) / 2


def derive_temporal_window(query: str, *, now: datetime | None = None) -> TemporalWindow | None:
    """Derive a wide ``(since, until)`` window from the query's first past-facing marker.

    Returns ``None`` when the query carries no temporal marker or the
    matched window starts fully in the future (plans, not recall scope).
    The first match in rule order wins (a query has one reference period);
    a skipped future window falls through to broader markers (e.g. “今年冬天”
    in autumn → the “今年” rule).

    Args:
        query: Sanitized retrieval query.
        now: Reference instant; defaults to UTC now. Inject the session
            timezone to anchor calendar boundaries locally — spill margins
            absorb the residual skew either way.
    """
    if not query:
        return None
    reference = now or datetime.now(UTC)
    for rule in _RULES:
        match = rule.pattern.search(query)
        if match is None:
            continue
        since, until = rule.resolve(reference, match)
        if since >= reference:
            continue
        return TemporalWindow(
            since=since,
            until=until,
            marker=match.group(0),
            window_kind=rule.kind,
            anchor=_proximity_anchor(rule, reference, since, until),
        )
    return None
