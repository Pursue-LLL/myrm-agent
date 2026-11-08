"""Agent explicit search constraints → provider-specific parameters.

[INPUT]
- (none — pure string/date transforms)

[OUTPUT]
- ProviderParams: provider parameters an explicit constraint is mapped onto
- TimeRangeResolution: provider parameters that carry a time constraint, plus the caveat when they cannot honor it exactly
- resolve_time_range: time_range → parameters of one provider (SearXNG, Tavily, Volcengine Doubao) or a caveat
- describe_time_range_caveats: one line naming how the given providers fall short of a time_range, or None
- resolve_site_operators: query site: operators → the domain filters of one provider (Tavily) or the query as written
- SiteOperators, split_site_operators: the one reading of a query's site: operators (domains included, domains excluded, remaining text)

[POS]
Explicit-constraint mapper of the web_search toolkit. A constraint the agent states is never inferred or guessed.
A time constraint reaches each provider hop as a parameter that provider accepts, or is reported as a caveat when
the provider cannot honor it exactly; ``site:`` operators become domain filters for Tavily and are otherwise left
in the query text as written. Every consumer of ``site:`` operators reads them through ``split_site_operators``,
so the grammar exists once.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

ProviderParams = dict[str, str | int | bool | list[str]]

TimeBucket = Literal["day", "week", "month", "year"]

# Window length of each bucket; the dict order is smallest window first.
_BUCKET_DAYS: dict[TimeBucket, int] = {"day": 1, "week": 7, "month": 30, "year": 365}

_VOLCENGINE_TIME_RANGE: dict[TimeBucket, str] = {
    "day": "OneDay",
    "week": "OneWeek",
    "month": "OneMonth",
    "year": "OneYear",
}

_DATE_RANGE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*\.\.\s*(\d{4}-\d{2}-\d{2})$")

# A site: operator is a whole token that may be negated, quoted or parenthesised and may end in punctuation. So
# ``-site:a.com``, ``site:"a.com"``, ``(site:a.com OR site:b.com)`` and ``site:a.com,`` read as the operators they
# are, while ``website:a.com``, ``foo-site:a.com`` and a ``site:`` glued to a word stay plain text. Its value must
# be a host (``gov.cn``, ``.edu``, ``*.edu``, ``中国.cn``) with an optional path, so ``<domain>``, an IP, a port, a
# scheme or ``gov.cn，site:edu.cn`` are no domain filter and stay plain text too. The ASCII top-level domain is what
# keeps a host from swallowing the CJK text glued behind it.
_SITE_OPERATOR_PATTERN = re.compile(
    r"""
    (?<![^\s"'(])       # starts a token, or follows an opening quote or parenthesis
    ["'(]?
    (?P<negated>-?)
    site:
    ["']?
    (?P<domain>
        (?:\*?\.)?                  # a leading dot or wildcard: .edu, *.edu
        (?:[\w-]+\.)*[A-Za-z]{2,}   # host: internationalised labels, ASCII top-level domain
        (?:/[^\s"')]*?)?            # optional path; lazy, so a closing dot stays outside it
    )
    ["')]?
    [,;.]?
    (?!\S)              # ends the token
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True, slots=True)
class _DateRange:
    start: date
    end: date

    def __str__(self) -> str:
        return f"{self.start.isoformat()}..{self.end.isoformat()}"


@dataclass(frozen=True, slots=True)
class TimeRangeResolution:
    """How one provider receives a time constraint.

    ``params`` is empty when the provider gets no time parameter. ``caveat`` is None when the provider applies
    the constraint exactly, otherwise a sentence stating what was applied instead.
    """

    params: ProviderParams
    caveat: str | None = None


def _parse_time_range(value: str) -> TimeBucket | _DateRange | None:
    """A bucket name or a valid ``YYYY-MM-DD..YYYY-MM-DD`` range; None for anything else."""
    text = value.strip().lower()
    for bucket in _BUCKET_DAYS:
        if text == bucket:
            return bucket

    match = _DATE_RANGE_PATTERN.match(text)
    if match is None:
        return None
    try:
        start, end = date.fromisoformat(match[1]), date.fromisoformat(match[2])
    except ValueError:
        return None
    return _DateRange(start, end) if start <= end else None


def _resolve_volcengine(parsed: TimeBucket | _DateRange, today: date) -> TimeRangeResolution:
    if isinstance(parsed, _DateRange):
        return TimeRangeResolution({"TimeRange": str(parsed)})
    return TimeRangeResolution({"TimeRange": _VOLCENGINE_TIME_RANGE[parsed]})


def _resolve_tavily(parsed: TimeBucket | _DateRange, today: date) -> TimeRangeResolution:
    if isinstance(parsed, _DateRange):
        return TimeRangeResolution({"start_date": parsed.start.isoformat(), "end_date": parsed.end.isoformat()})
    return TimeRangeResolution({"time_range": parsed})


def _resolve_searxng(parsed: TimeBucket | _DateRange, today: date) -> TimeRangeResolution:
    """SearXNG accepts only the four buckets, so a range becomes the smallest bucket that still covers its start."""
    if not isinstance(parsed, _DateRange):
        return TimeRangeResolution({"time_range": parsed})

    age_days = (today - parsed.start).days
    covering_bucket = next((bucket for bucket, days in _BUCKET_DAYS.items() if age_days <= days), None)
    if covering_bucket is None:
        return TimeRangeResolution(
            {},
            f"searxng cannot filter by date range and {parsed} starts over a year ago, so no time filter was applied.",
        )
    return TimeRangeResolution(
        {"time_range": covering_bucket},
        f"searxng cannot filter by date range, so it searched the last {covering_bucket} instead of {parsed}; "
        "results outside the range may appear.",
    )


_RESOLVERS: dict[str, Callable[[TimeBucket | _DateRange, date], TimeRangeResolution]] = {
    "volcengine_doubao": _resolve_volcengine,
    "tavily": _resolve_tavily,
    "searxng": _resolve_searxng,
}


def resolve_time_range(time_range: str, provider: str, today: date | None = None) -> TimeRangeResolution:
    """Map the agent's ``time_range`` onto the parameters ``provider`` accepts.

    ``today`` anchors the relative buckets a date range may need to be converted into; it defaults to the
    current local date.
    """
    parsed = _parse_time_range(time_range)
    if parsed is None:
        return TimeRangeResolution(
            {},
            f"time_range '{time_range}' is not day/week/month/year or a valid YYYY-MM-DD..YYYY-MM-DD range, "
            "so no time filter was applied.",
        )

    resolver = _RESOLVERS.get(provider)
    if resolver is None:
        return TimeRangeResolution(
            {}, f"time filters are not passed to {provider}, so time_range '{time_range}' was not applied."
        )
    return resolver(parsed, today or date.today())


def describe_time_range_caveats(time_range: str, providers: Sequence[str], today: date | None = None) -> str | None:
    """Every distinct way ``providers`` fall short of ``time_range``, joined into one line; None when none does."""
    caveats = dict.fromkeys(
        caveat for provider in providers if (caveat := resolve_time_range(time_range, provider, today).caveat)
    )
    return " ".join(caveats) or None


@dataclass(frozen=True, slots=True)
class SiteOperators:
    """The ``site:`` operators of a query, and the text that remains once they are removed."""

    included: tuple[str, ...]
    excluded: tuple[str, ...]
    remainder: str


def split_site_operators(query: str) -> SiteOperators:
    """Read the ``site:`` / ``-site:`` operators of ``query``.

    Each domain appears once, in the order it was written. ``remainder`` is the query without the operators and with
    its whitespace collapsed; it is empty when the query was nothing but operators.
    """
    included: list[str] = []
    excluded: list[str] = []

    def take_domain(match: re.Match[str]) -> str:
        domain = match["domain"].rstrip("/")
        domains = excluded if match["negated"] else included
        if domain not in domains:
            domains.append(domain)
        return " "

    remainder = " ".join(_SITE_OPERATOR_PATTERN.sub(take_domain, query).split())
    return SiteOperators(tuple(included), tuple(excluded), remainder)


def resolve_site_operators(query: str, provider: str) -> tuple[str, ProviderParams]:
    """Map the ``site:`` operators of ``query`` onto the domain filters ``provider`` accepts.

    Tavily filters with ``include_domains`` / ``exclude_domains``, which LiteLLM receives as
    ``search_domain_filter`` / ``exclude_domains``. Its operators therefore become those parameters
    (``-site:`` excludes) and leave the query, unless nothing else remains: a query of only operators keeps its
    text. This module maps no domain filter for any other provider, which gets the query as written.
    """
    if provider != "tavily":
        return query, {}

    operators = split_site_operators(query)
    params: ProviderParams = {}
    if operators.included:
        params["search_domain_filter"] = list(operators.included)
    if operators.excluded:
        params["exclude_domains"] = list(operators.excluded)
    if not params:
        return query, {}
    return operators.remainder or query, params


__all__ = [
    "ProviderParams",
    "SiteOperators",
    "TimeRangeResolution",
    "describe_time_range_caveats",
    "resolve_site_operators",
    "resolve_time_range",
    "split_site_operators",
]
