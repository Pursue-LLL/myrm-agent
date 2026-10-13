"""Lifecycle test isolation: the cognitive-clock singletons are process-global, so every test starts from fresh ones."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from myrm_agent_harness.runtime.cognitive_clock.signals import get_global_pause_signal

from app.lifecycle.cognitive_clock import activity_sensor, wakeup_guard


@pytest.fixture(autouse=True)
def _fresh_cognitive_clock_singletons(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A grace period or recorded activity left by one test must not suppress the next one."""
    monkeypatch.setattr(wakeup_guard, "_GLOBAL_WAKEUP_GUARD", None)
    monkeypatch.setattr(activity_sensor, "_GLOBAL_ACTIVITY_SENSOR", None)
    pause_signal = get_global_pause_signal()
    pause_signal.clear()
    yield
    pause_signal.clear()
