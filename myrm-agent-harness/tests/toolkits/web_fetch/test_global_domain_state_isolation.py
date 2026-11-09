"""The process-wide domain state does not carry what one test taught it into the next.

Wait-strategy learning is keyed by ``host:port``, so a leftover entry for a loopback test server's port
changes the wait path of any later test that is handed the same ephemeral port. The tier breaker likewise
remembers which tier failed on a domain. ``tests/conftest.py`` drops both around every test. Each pair of
tests below only means something in this order.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetcherType
from myrm_agent_harness.toolkits.web_fetch.router import get_global_domain_metrics_manager, get_global_tier_breaker

_LOOPBACK_SERVER = "127.0.0.1:43210"


def test_a_test_teaches_the_global_manager_a_domain() -> None:
    get_global_domain_metrics_manager().get_or_create(_LOOPBACK_SERVER).record_networkidle_result(success=False)

    assert get_global_domain_metrics_manager().get(_LOOPBACK_SERVER) is not None


def test_the_next_test_starts_without_it() -> None:
    assert get_global_domain_metrics_manager().get(_LOOPBACK_SERVER) is None


def test_a_test_teaches_the_global_breaker_to_skip_a_tier() -> None:
    breaker = get_global_tier_breaker()
    for _ in range(3):
        breaker.report(_LOOPBACK_SERVER, FetcherType.HTTP, success=False)
        breaker.report(_LOOPBACK_SERVER, FetcherType.BROWSER, success=True)

    assert breaker.select(_LOOPBACK_SERVER) is FetcherType.BROWSER


def test_the_next_test_starts_on_the_first_tier() -> None:
    assert get_global_tier_breaker().select(_LOOPBACK_SERVER) is FetcherType.HTTP
