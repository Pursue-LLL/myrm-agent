"""The process-wide domain metrics manager does not carry what one test taught it into the next.

Wait-strategy learning is keyed by ``host:port``, so a leftover entry for a loopback test server's port
changes the wait path of any later test that is handed the same ephemeral port. ``tests/conftest.py``
drops the manager around every test. The two tests below only mean something in this order.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.web_fetch.router import get_global_domain_metrics_manager

_LOOPBACK_SERVER = "127.0.0.1:43210"


def test_a_test_teaches_the_global_manager_a_domain() -> None:
    get_global_domain_metrics_manager().get_or_create(_LOOPBACK_SERVER).record_networkidle_result(success=False)

    assert get_global_domain_metrics_manager().get(_LOOPBACK_SERVER) is not None


def test_the_next_test_starts_without_it() -> None:
    assert get_global_domain_metrics_manager().get(_LOOPBACK_SERVER) is None
