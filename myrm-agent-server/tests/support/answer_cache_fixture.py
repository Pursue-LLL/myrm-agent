"""The provider answer cache switched on and empty, the way the server runs it.

[INPUT]
- myrm_agent_harness.toolkits.llms.transport.answer_cache::answer_cache (POS: the process-wide store of provider answers)

[OUTPUT]
- answer_cache_on: explicit-request fixture; the cache is on and empty for one test, and what the test left in it is dropped

[POS]
The suite starts with the cache off (`tests/conftest.py`) so a test reaches its fake provider every time. A test that
asserts something about the cache, or about a call that has to bypass it, requests this fixture.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from myrm_agent_harness.toolkits.llms.transport.answer_cache import answer_cache


@pytest.fixture
def answer_cache_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(answer_cache, "enabled", True)
    answer_cache.clear()
    yield
    answer_cache.clear()
