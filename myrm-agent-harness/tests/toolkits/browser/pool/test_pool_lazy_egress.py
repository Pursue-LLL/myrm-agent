"""The pool package loads the egress guard on first access, so importing the pool does not load the HTTP client.

The guard brings in the HTTP client and the security detection stack. The browser toolkit is imported through the
pool, and a program that only wants a session should not pay for either.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from myrm_agent_harness.toolkits.browser import pool

_PROBE = """
import json
import sys

import myrm_agent_harness.toolkits.browser.pool as pool

GUARD = "myrm_agent_harness.toolkits.browser.pool.egress_guard"
before = [name for name in (GUARD, "httpx") if name in sys.modules]
pool.EgressGuard
print(json.dumps({"before": before, "guard_after_access": GUARD in sys.modules}))
"""
_LAZY_NAMES = {"EgressGuard", "EgressGuardError", "create_egress_guard"}


def test_importing_the_pool_loads_neither_the_guard_nor_the_http_client() -> None:
    # A fresh interpreter: this process has long since imported both.
    result = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    probe = json.loads(result.stdout)
    assert probe["before"] == []
    assert probe["guard_after_access"] is True


def test_the_pool_lists_its_lazy_names_and_refuses_unknown_ones() -> None:
    unknown = "NoSuchName"

    assert set(dir(pool)) >= _LAZY_NAMES
    assert not hasattr(pool, unknown)
    with pytest.raises(AttributeError, match=unknown):
        getattr(pool, unknown)
