"""Explicit search constraints → provider parameters (processing/_explicit_params.py).

[POS]
Unit tests for resolve_time_range, describe_time_range_caveats, split_site_operators and resolve_site_operators.
Dates are anchored on a fixed ``today`` so the conversion of date ranges into relative buckets is deterministic.
"""

from __future__ import annotations

from datetime import date

import pytest

from myrm_agent_harness.toolkits.web_search.processing._explicit_params import (
    SiteOperators,
    describe_time_range_caveats,
    resolve_site_operators,
    resolve_time_range,
    split_site_operators,
)

TODAY = date(2026, 11, 5)
BUCKETS = ["day", "week", "month", "year"]
PROVIDERS = ["volcengine_doubao", "tavily", "searxng", "brave"]


class TestVolcengine:
    @pytest.mark.parametrize(
        ("bucket", "expected"),
        [("day", "OneDay"), ("week", "OneWeek"), ("month", "OneMonth"), ("year", "OneYear")],
    )
    def test_buckets_map_to_its_enum(self, bucket: str, expected: str) -> None:
        resolution = resolve_time_range(bucket, "volcengine_doubao", TODAY)

        assert resolution.params == {"TimeRange": expected}
        assert resolution.caveat is None

    def test_date_range_is_passed_through(self) -> None:
        resolution = resolve_time_range("2025-01-01..2025-06-30", "volcengine_doubao", TODAY)

        assert resolution.params == {"TimeRange": "2025-01-01..2025-06-30"}
        assert resolution.caveat is None


class TestTavily:
    @pytest.mark.parametrize("bucket", BUCKETS)
    def test_buckets_use_the_time_range_field(self, bucket: str) -> None:
        resolution = resolve_time_range(bucket, "tavily", TODAY)

        assert resolution.params == {"time_range": bucket}
        assert resolution.caveat is None

    def test_date_range_uses_start_and_end_date(self) -> None:
        resolution = resolve_time_range("2025-01-01..2025-06-30", "tavily", TODAY)

        assert resolution.params == {"start_date": "2025-01-01", "end_date": "2025-06-30"}
        assert resolution.caveat is None


class TestSearxng:
    @pytest.mark.parametrize("bucket", BUCKETS)
    def test_buckets_pass_through(self, bucket: str) -> None:
        resolution = resolve_time_range(bucket, "searxng", TODAY)

        assert resolution.params == {"time_range": bucket}
        assert resolution.caveat is None

    @pytest.mark.parametrize(
        ("start", "bucket"),
        [("2026-11-04", "day"), ("2026-10-30", "week"), ("2026-10-10", "month"), ("2026-01-01", "year")],
    )
    def test_date_range_becomes_the_smallest_bucket_covering_its_start(self, start: str, bucket: str) -> None:
        resolution = resolve_time_range(f"{start}..2026-11-05", "searxng", TODAY)

        assert resolution.params == {"time_range": bucket}
        assert resolution.caveat is not None
        assert f"last {bucket}" in resolution.caveat
        assert f"{start}..2026-11-05" in resolution.caveat

    def test_date_range_starting_over_a_year_ago_is_dropped_and_disclosed(self) -> None:
        resolution = resolve_time_range("2025-10-01..2025-10-31", "searxng", TODAY)

        assert resolution.params == {}
        assert resolution.caveat is not None
        assert "over a year ago" in resolution.caveat


class TestUnsupportedAndInvalid:
    def test_a_provider_without_time_parameters_gets_none_and_a_caveat(self) -> None:
        resolution = resolve_time_range("week", "brave", TODAY)

        assert resolution.params == {}
        assert resolution.caveat is not None
        assert "brave" in resolution.caveat

    @pytest.mark.parametrize("provider", PROVIDERS)
    @pytest.mark.parametrize(
        "value",
        ["quarter", "last week", "2025-06-30..2025-01-01", "not-a-date..also-bad", "2025-02-30..2025-03-01", ""],
    )
    def test_an_unparseable_value_is_never_replaced_by_a_default(self, provider: str, value: str) -> None:
        resolution = resolve_time_range(value, provider, TODAY)

        assert resolution.params == {}
        assert resolution.caveat is not None
        assert f"'{value}'" in resolution.caveat

    def test_case_and_surrounding_whitespace_are_tolerated(self) -> None:
        assert resolve_time_range(" Week ", "tavily", TODAY).params == {"time_range": "week"}
        assert resolve_time_range("2025-01-01 .. 2025-06-30", "tavily", TODAY).params == {
            "start_date": "2025-01-01",
            "end_date": "2025-06-30",
        }


class TestDescribeTimeRangeCaveats:
    def test_no_caveat_when_every_provider_applies_the_range_exactly(self) -> None:
        assert describe_time_range_caveats("week", ["searxng", "tavily", "volcengine_doubao"], TODAY) is None

    def test_each_shortfall_is_named_once(self) -> None:
        caveats = describe_time_range_caveats("2026-10-30..2026-11-05", ["tavily", "searxng", "brave", "brave"], TODAY)

        assert caveats is not None
        assert caveats.count("brave") == 1
        assert "searxng cannot filter by date range" in caveats
        assert "tavily" not in caveats

    def test_an_invalid_value_is_reported_once_for_all_providers(self) -> None:
        caveats = describe_time_range_caveats("quarter", ["searxng", "tavily"], TODAY)

        assert caveats is not None
        assert caveats.count("'quarter'") == 1


class TestSplitSiteOperators:
    def test_separates_included_and_excluded_domains_from_the_remaining_text(self) -> None:
        operators = split_site_operators("react hooks site:react.dev -site:reddit.com site:github.com/facebook")

        assert operators == SiteOperators(
            included=("react.dev", "github.com/facebook"),
            excluded=("reddit.com",),
            remainder="react hooks",
        )

    def test_a_domain_written_twice_appears_once_in_the_order_it_first_appeared(self) -> None:
        operators = split_site_operators("x site:b.com site:a.com site:b.com -site:c.com -site:c.com")

        assert operators.included == ("b.com", "a.com")
        assert operators.excluded == ("c.com",)

    def test_a_query_without_operators_keeps_its_text_with_collapsed_whitespace(self) -> None:
        assert split_site_operators("  python   asyncio\ttutorial ") == SiteOperators((), (), "python asyncio tutorial")

    @pytest.mark.parametrize(
        "query", ["foo-site:bar.com baz", "x website:foo.com", "x site:192.168.1.1", "what does site: do"]
    )
    def test_text_that_is_not_an_operator_yields_no_domain(self, query: str) -> None:
        operators = split_site_operators(query)

        assert operators.included == ()
        assert operators.excluded == ()
        assert operators.remainder == query

    def test_a_query_that_is_only_operators_has_an_empty_remainder(self) -> None:
        assert split_site_operators('site:"bilibili.com" -site:reddit.com') == SiteOperators(
            ("bilibili.com",), ("reddit.com",), ""
        )


class TestResolveSiteOperators:
    @pytest.mark.parametrize(
        ("query", "cleaned", "params"),
        [
            ("site:gov.cn 数字经济 政策", "数字经济 政策", {"search_domain_filter": ["gov.cn"]}),
            ("AI policy site:gov.cn site:edu.cn", "AI policy", {"search_domain_filter": ["gov.cn", "edu.cn"]}),
            ("x site:a.com site:a.com", "x", {"search_domain_filter": ["a.com"]}),
            ("react hooks -site:reddit.com", "react hooks", {"exclude_domains": ["reddit.com"]}),
            (
                "x -site:reddit.com -site:quora.com site:react.dev",
                "x",
                {"search_domain_filter": ["react.dev"], "exclude_domains": ["reddit.com", "quora.com"]},
            ),
            ('x site:"example.com"', "x", {"search_domain_filter": ["example.com"]}),
            ("x site:gov.cn,", "x", {"search_domain_filter": ["gov.cn"]}),
            ("x site:github.com/openai.", "x", {"search_domain_filter": ["github.com/openai"]}),
            ("x site:gov.cn/", "x", {"search_domain_filter": ["gov.cn"]}),
            ("x site:*.edu", "x", {"search_domain_filter": ["*.edu"]}),
            ("x site:.edu", "x", {"search_domain_filter": [".edu"]}),
            ("x -site:.edu", "x", {"exclude_domains": [".edu"]}),
            ("x site:中国.cn", "x", {"search_domain_filter": ["中国.cn"]}),
            (
                "x site:zh.wikipedia.org/wiki/人工智能",
                "x",
                {"search_domain_filter": ["zh.wikipedia.org/wiki/人工智能"]},
            ),
            ("AI site:gov.cn, site:edu.cn", "AI", {"search_domain_filter": ["gov.cn", "edu.cn"]}),
            ("x SITE:GOV.CN", "x", {"search_domain_filter": ["GOV.CN"]}),
            ('"exact phrase" site:docs.python.org', '"exact phrase"', {"search_domain_filter": ["docs.python.org"]}),
        ],
    )
    def test_tavily_takes_the_operators_as_domain_filters(
        self, query: str, cleaned: str, params: dict[str, list[str]]
    ) -> None:
        assert resolve_site_operators(query, "tavily") == (cleaned, params)

    def test_a_parenthesised_group_yields_every_domain_and_leaves_no_site_or_parenthesis_in_the_query(self) -> None:
        cleaned, params = resolve_site_operators("llm (site:a.com OR site:b.com)", "tavily")

        assert params == {"search_domain_filter": ["a.com", "b.com"]}
        assert cleaned.startswith("llm")
        assert all(fragment not in cleaned for fragment in ("(", ")", "site:"))

    @pytest.mark.parametrize(
        ("query", "params"),
        [
            ("site:gov.cn", {"search_domain_filter": ["gov.cn"]}),
            ("-site:reddit.com", {"exclude_domains": ["reddit.com"]}),
        ],
    )
    def test_a_query_that_is_only_an_operator_keeps_its_text(self, query: str, params: dict[str, list[str]]) -> None:
        assert resolve_site_operators(query, "tavily") == (query, params)

    @pytest.mark.parametrize(
        "query",
        [
            "python asyncio tutorial",
            "foo-site:bar.com baz",
            "x website:foo.com",
            "数字经济site:gov.cn",
            "x site:/ y",
            "what does site: do",
        ],
    )
    def test_text_that_is_not_an_operator_is_left_alone(self, query: str) -> None:
        assert resolve_site_operators(query, "tavily") == (query, {})

    @pytest.mark.parametrize(
        "query",
        [
            "AI 监管 site:gov.cn，site:edu.cn",
            "AI 监管 site:gov.cn、site:edu.cn",
            "AI 监管 site:gov.cn,site:edu.cn",
            "site:gov.cn人工智能政策 政策",
            "人工智能 site:gov.cn。",
            "人工智能 site:gov.cn）",
            "x site:<domain>",
            "x site:*",
            "x site:192.168.1.1",
            "x site:example.com:8080",
            "x site:https://example.com",
            "x site:例子.中国",
        ],
    )
    def test_a_site_value_that_is_not_a_host_is_no_domain_filter(self, query: str) -> None:
        assert resolve_site_operators(query, "tavily") == (query, {})

    @pytest.mark.parametrize("provider", ["searxng", "brave", "perplexity", "exa_ai", "volcengine_doubao"])
    def test_other_providers_receive_the_query_as_written(self, provider: str) -> None:
        query = "x -site:a.com site:b.com"

        assert resolve_site_operators(query, provider) == (query, {})
