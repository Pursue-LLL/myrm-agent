"""Autouse plugin: process-wide singletons that tests mutate are reset around every test.

Each fixture undoes state that outlives a test through a module-level singleton, which would otherwise make the
outcome of a test depend on which tests ran before it in the same worker process. Every reset does nothing until
the suite has imported the singleton's module.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from unittest.mock import patch

import pytest


def _forget_event_history() -> None:
    module = sys.modules.get("app.services.event.app_event_bus")
    if module is None or module._bus is None:
        return
    module._bus._backlogs.clear()
    module._bus._last_event_key.clear()


@pytest.fixture(autouse=True)
def _isolate_event_bus_history() -> Iterator[None]:
    """``PubSubBus`` replays each topic's backlog to a new subscriber and drops an event identical to the previous
    one on its topic: without a reset a test reads events an earlier test published, or never sees its own because
    it repeats the one before."""
    _forget_event_history()
    yield
    _forget_event_history()


@pytest.fixture(autouse=True)
def _isolate_agent_gateway_drain() -> Iterator[None]:
    """A test that drains the agent gateway (shutdown API, lifespan teardown) would leave it rejecting every agent
    turn of the tests that follow with ``AgentDrainingError``."""
    yield
    module = sys.modules.get("app.services.agent.gateway")
    if module is not None and module._gateway is not None:
        module._gateway.cancel_drain()


@pytest.fixture(autouse=True)
def _isolate_task_metrics_registry() -> Iterator[None]:
    """Task metrics are kept per chat id in a process-wide registry, and tests share ids such as ``chat-1``: the
    archive refetch events one test leaves behind would exhaust the per-task restore budget of the next test that
    restores the same path."""
    yield
    module = sys.modules.get("myrm_agent_harness.agent.context_management.tracking.task_metrics_registry")
    if module is not None:
        for chat_id in module.get_all_active_metrics():
            module.clear_task_metrics(chat_id)


@pytest.fixture(autouse=True)
def _isolate_settings_singleton() -> Iterator[None]:
    """``get_settings`` builds a new object after its cache is cleared, and the one every module imported as
    ``settings`` stays the old one: a test that patches ``settings`` would then not reach code that calls
    ``get_settings()``. The singleton goes back to being the imported object after each test."""
    yield
    module = sys.modules.get("app.config.settings.singleton")
    if module is None:
        return
    module.get_settings.cache_clear()
    with patch.object(module, "AppSettings", return_value=module.settings):
        module.get_settings()
