"""Search adapters at the edges of what a caller or a provider may send: nothing but the pure request and row shapes."""

from __future__ import annotations

from myrm_agent_harness.toolkits.web_search.providers.search_adapters import ADAPTERS, SearchRequest


def _request(provider: str, limit: int = 5, **unified: object) -> SearchRequest:
    return ADAPTERS[provider].build("q", limit, unified, "key:secret", None)


def _body(request: SearchRequest) -> dict[str, object]:
    assert isinstance(request.json_body, dict)
    return request.json_body


def test_one_domain_given_as_plain_text_is_a_one_item_filter() -> None:
    request = _request("tavily", search_domain_filter="docs.python.org")

    assert _body(request)["include_domains"] == ["docs.python.org"]


class TestParallel:
    def test_the_excerpt_cap_and_both_domain_lists_reach_the_provider(self) -> None:
        request = _request(
            "parallel_ai", max_chars_per_result=500, search_domain_filter=["a.com"], exclude_domains=["b.com"]
        )

        settings = _body(request)["advanced_settings"]
        assert isinstance(settings, dict)
        assert settings["excerpt_settings"] == {"max_chars_per_result": 500}
        assert settings["source_policy"] == {"include_domains": ["a.com"], "exclude_domains": ["b.com"]}

    def test_only_the_lists_the_caller_gave_appear_in_the_policy(self) -> None:
        request = _request("parallel_ai", exclude_domains=["b.com"])

        settings = _body(request)["advanced_settings"]
        assert isinstance(settings, dict)
        assert settings["source_policy"] == {"exclude_domains": ["b.com"]}

    def test_the_callers_advanced_settings_win_over_what_the_unified_parameters_mapped(self) -> None:
        request = _request("parallel_ai", limit=5, advanced_settings={"max_results": 50, "fetch_policy": "fresh"})

        settings = _body(request)["advanced_settings"]
        assert isinstance(settings, dict)
        assert settings["max_results"] == 50
        assert settings["fetch_policy"] == "fresh"


class TestDataForSeo:
    @staticmethod
    def _answer(status: int) -> dict[str, object]:
        item = {"type": "organic", "title": "Title", "url": "https://x.test", "description": "About"}
        return {"tasks": [{"status_code": status, "result": [{"items": [item]}]}]}

    def test_a_task_the_provider_reports_as_failed_yields_no_rows(self) -> None:
        adapter = ADAPTERS["dataforseo"]

        assert adapter.parse(self._answer(40501), _request("dataforseo")) == []

    def test_a_task_that_succeeded_yields_its_organic_rows(self) -> None:
        adapter = ADAPTERS["dataforseo"]

        rows = adapter.parse(self._answer(20000), _request("dataforseo"))

        assert rows == [{"title": "Title", "url": "https://x.test", "snippet": "About", "date": None}]


class TestFirecrawl:
    def test_a_flat_list_of_results_is_read_with_markdown_before_description(self) -> None:
        payload = {
            "data": [
                {"title": "A", "url": "https://a.test", "markdown": "# body", "description": "unused"},
                {"title": "B", "url": "https://b.test", "description": "only a description"},
            ]
        }

        rows = ADAPTERS["firecrawl"].parse(payload, _request("firecrawl"))

        assert [row["snippet"] for row in rows] == ["# body", "only a description"]

    def test_data_that_is_neither_a_list_nor_sections_yields_no_rows(self) -> None:
        assert ADAPTERS["firecrawl"].parse({"data": "oops"}, _request("firecrawl")) == []
        assert ADAPTERS["firecrawl"].parse({}, _request("firecrawl")) == []


class TestBrave:
    @staticmethod
    def _section(prefix: str, count: int) -> dict[str, object]:
        return {"results": [{"title": f"{prefix}{i}", "url": f"https://{prefix}{i}.test"} for i in range(count)]}

    def test_the_rows_stop_at_the_requested_count_across_sections(self) -> None:
        request = _request("brave", limit=4)
        payload = {"web": self._section("w", 3), "news": self._section("n", 3)}

        rows = ADAPTERS["brave"].parse(payload, request)

        assert [row["title"] for row in rows] == ["w0", "w1", "w2", "n0"]

    def test_the_count_is_never_more_than_twenty_nor_less_than_one(self) -> None:
        assert len(ADAPTERS["brave"].parse({"web": self._section("w", 30)}, _request("brave", limit=99))) == 20
        assert len(ADAPTERS["brave"].parse({"web": self._section("w", 3)}, _request("brave", limit=0))) == 1
