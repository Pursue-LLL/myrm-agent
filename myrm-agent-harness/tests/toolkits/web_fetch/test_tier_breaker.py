"""The tier breaker moves a domain's start tier only on contrast evidence: a higher tier succeeding where a lower failed.

Failures alone are never enough. A network outage or a slow site fails every tier alike, so counting them would pin
a healthy domain to a slower tier; only "this tier failed and the next one then worked" shows the tier is the problem.
"""

from __future__ import annotations

import logging
import threading

import pytest

from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetcherType
from myrm_agent_harness.toolkits.web_fetch.router import TierBreaker, get_global_tier_breaker

HTTP, BROWSER, STEALTH = FetcherType.HTTP, FetcherType.BROWSER, FetcherType.STEALTH
DOMAIN = "example.com"


@pytest.fixture
def breaker() -> TierBreaker:
    return TierBreaker(open_after=3, probe_every=10, max_domains=4096)


def _fail(breaker: TierBreaker, tier: FetcherType, domain: str = DOMAIN) -> None:
    breaker.report(domain, tier, success=False)


def _succeed(breaker: TierBreaker, tier: FetcherType, domain: str = DOMAIN) -> None:
    breaker.report(domain, tier, success=True)


def _http_made_up_for_by_browser(breaker: TierBreaker, times: int, domain: str = DOMAIN) -> None:
    for _ in range(times):
        _fail(breaker, HTTP, domain)
        _succeed(breaker, BROWSER, domain)


def _both_made_up_for_by_stealth(breaker: TierBreaker, times: int, domain: str = DOMAIN) -> None:
    for _ in range(times):
        _fail(breaker, HTTP, domain)
        _fail(breaker, BROWSER, domain)
        _succeed(breaker, STEALTH, domain)


class TestStartTier:
    def test_defaults_open_after_three_contrasts_and_probe_every_tenth_visit(self) -> None:
        default = TierBreaker()
        _http_made_up_for_by_browser(default, 2)
        assert default.select(DOMAIN) is HTTP
        _http_made_up_for_by_browser(default, 1)

        visits = [default.select(DOMAIN) for _ in range(10)]

        assert visits == [BROWSER] * 9 + [HTTP]

    def test_unknown_domain_starts_on_http(self, breaker: TierBreaker) -> None:
        assert breaker.select(DOMAIN) is HTTP

    def test_failures_without_a_higher_tier_succeeding_never_move_the_start_tier(self, breaker: TierBreaker) -> None:
        for _ in range(50):
            _fail(breaker, HTTP)
            _fail(breaker, BROWSER)
            _fail(breaker, STEALTH)

        assert breaker.select(DOMAIN) is HTTP

    def test_a_tier_opens_after_three_failures_a_higher_tier_made_up_for(self, breaker: TierBreaker) -> None:
        _http_made_up_for_by_browser(breaker, 2)
        assert breaker.select(DOMAIN) is HTTP

        _http_made_up_for_by_browser(breaker, 1)

        assert breaker.select(DOMAIN) is BROWSER

    def test_repeated_failures_before_one_success_count_as_one_contrast(self, breaker: TierBreaker) -> None:
        for _ in range(5):
            _fail(breaker, HTTP)
        _succeed(breaker, BROWSER)
        assert breaker.select(DOMAIN) is HTTP

        _http_made_up_for_by_browser(breaker, 2)

        assert breaker.select(DOMAIN) is BROWSER

    def test_a_success_of_the_tier_itself_resets_its_count(self, breaker: TierBreaker) -> None:
        _http_made_up_for_by_browser(breaker, 2)
        _succeed(breaker, HTTP)

        _http_made_up_for_by_browser(breaker, 2)

        assert breaker.select(DOMAIN) is HTTP

    def test_a_contrast_blames_every_lower_tier_that_failed(self, breaker: TierBreaker) -> None:
        _both_made_up_for_by_stealth(breaker, 3)

        assert breaker.select(DOMAIN) is STEALTH

    def test_domains_are_independent(self, breaker: TierBreaker) -> None:
        _http_made_up_for_by_browser(breaker, 3, "blocked.example")

        assert breaker.select("blocked.example") is BROWSER
        assert breaker.select("fine.example") is HTTP

    def test_stealth_failures_are_ignored(self, breaker: TierBreaker) -> None:
        _fail(breaker, STEALTH)

        assert breaker.select(DOMAIN) is HTTP
        assert breaker._domains == {}


class TestProbing:
    def test_an_open_tier_is_retried_on_every_tenth_visit(self, breaker: TierBreaker) -> None:
        _http_made_up_for_by_browser(breaker, 3)

        first_round = [breaker.select(DOMAIN) for _ in range(10)]
        _http_made_up_for_by_browser(breaker, 1)  # the probe failed again, so the tier stays open
        second_round = [breaker.select(DOMAIN) for _ in range(10)]

        assert first_round == [BROWSER] * 9 + [HTTP]
        assert second_round == [BROWSER] * 9 + [HTTP]

    def test_a_probe_success_closes_the_tier(self, breaker: TierBreaker) -> None:
        _http_made_up_for_by_browser(breaker, 3)
        for _ in range(9):
            breaker.select(DOMAIN)
        assert breaker.select(DOMAIN) is HTTP

        _succeed(breaker, HTTP)

        assert breaker.select(DOMAIN) is HTTP
        _http_made_up_for_by_browser(breaker, 2)  # a closed tier starts from a clean count
        assert breaker.select(DOMAIN) is HTTP

    def test_stealth_is_the_only_start_when_both_lower_tiers_are_open(self, breaker: TierBreaker) -> None:
        _both_made_up_for_by_stealth(breaker, 3)

        visits = [breaker.select(DOMAIN) for _ in range(12)]

        # The HTTP probe comes first on visit 10; the browser, reached only on visits that skip HTTP, probes on 11.
        assert visits == [STEALTH] * 9 + [HTTP, BROWSER, STEALTH]

    def test_a_browser_success_closes_the_browser_but_leaves_http_open(self, breaker: TierBreaker) -> None:
        _both_made_up_for_by_stealth(breaker, 3)
        _succeed(breaker, BROWSER)

        assert breaker.select(DOMAIN) is BROWSER  # HTTP stays open, the browser works again


class TestConcurrentRequests:
    def test_a_success_on_another_request_clears_the_failure_this_one_left_pending(self, breaker: TierBreaker) -> None:
        for _ in range(3):
            _fail(breaker, HTTP)  # request A: HTTP failed, still running
            _succeed(breaker, HTTP)  # request B: HTTP works here
            _succeed(breaker, BROWSER)  # request A: its browser fallback succeeded

        assert breaker.select(DOMAIN) is HTTP


class TestBounds:
    def test_least_recently_used_domains_are_evicted(self) -> None:
        breaker = TierBreaker(max_domains=3)
        for index in range(4):
            _fail(breaker, HTTP, f"d{index}.example")

        assert list(breaker._domains) == ["d1.example", "d2.example", "d3.example"]

    def test_selecting_a_domain_keeps_it_from_being_evicted(self) -> None:
        breaker = TierBreaker(max_domains=3)
        for index in range(3):
            _fail(breaker, HTTP, f"d{index}.example")
        breaker.select("d0.example")

        _fail(breaker, HTTP, "d3.example")

        assert list(breaker._domains) == ["d2.example", "d0.example", "d3.example"]

    def test_domains_are_tracked_only_while_a_tier_is_failing(self, breaker: TierBreaker) -> None:
        _succeed(breaker, HTTP, "healthy.example")
        _fail(breaker, HTTP, "recovering.example")
        _succeed(breaker, HTTP, "recovering.example")

        assert breaker._domains == {}


class TestObservability:
    def test_opening_warns_once_and_closing_is_logged(
        self, breaker: TierBreaker, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="myrm_agent_harness.toolkits.web_fetch.router.tier_breaker"):
            _http_made_up_for_by_browser(breaker, 4)
            _succeed(breaker, HTTP)

        records = [(record.levelno, record.getMessage()) for record in caplog.records]
        assert [level for level, _ in records] == [logging.WARNING, logging.INFO]
        assert "opened" in records[0][1]
        assert "HTTP" in records[0][1]
        assert DOMAIN in records[0][1]
        assert "closed" in records[1][1]


class TestThreadSafety:
    def test_concurrent_selects_and_reports_keep_the_state_consistent(self) -> None:
        breaker = TierBreaker(max_domains=10)
        errors: list[Exception] = []
        start = threading.Barrier(8)

        def worker(offset: int) -> None:
            start.wait()
            try:
                for step in range(2000):
                    domain = f"d{(step + offset) % 25}.example"
                    breaker.select(domain)
                    kind = (step + offset) % 5
                    if kind == 0:
                        _fail(breaker, HTTP, domain)
                    elif kind == 1:
                        _succeed(breaker, BROWSER, domain)
                    elif kind == 2:
                        _fail(breaker, BROWSER, domain)
                    elif kind == 3:
                        _succeed(breaker, STEALTH, domain)
                    else:
                        _succeed(breaker, HTTP, domain)
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=worker, args=(offset,)) for offset in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert len(breaker._domains) <= 10
        assert all(
            state.blamed >= 0 and state.skipped >= 0 for tiers in breaker._domains.values() for state in tiers.values()
        )


def test_the_global_breaker_is_one_shared_instance() -> None:
    assert get_global_tier_breaker() is get_global_tier_breaker()
