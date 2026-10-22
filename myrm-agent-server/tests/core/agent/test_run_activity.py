"""In-flight counter for agent runs that AgentGateway does not count."""

from __future__ import annotations

import gc
import weakref
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from app.core.agent.run_activity import active_background_agent_runs, track_background_agent_run

_REGISTRY = "app.core.agent.run_activity.ACTIVE_SUBAGENTS"


@pytest.fixture(autouse=True)
def _no_live_subagents() -> Iterator[None]:
    with patch(_REGISTRY, {}):
        yield


def test_counter_tracks_nested_runs() -> None:
    assert active_background_agent_runs() == 0
    with track_background_agent_run():
        with track_background_agent_run():
            assert active_background_agent_runs() == 2
        assert active_background_agent_runs() == 1
    assert active_background_agent_runs() == 0


def test_counter_released_when_run_raises() -> None:
    with pytest.raises(RuntimeError):
        with track_background_agent_run():
            raise RuntimeError("boom")
    assert active_background_agent_runs() == 0


def test_running_subagent_tasks_count_even_after_their_parent_turn_ended() -> None:
    """A detached sub-agent outlives the turn that spawned it; the registry is what still sees it."""
    manager = MagicMock()
    with patch(_REGISTRY, {"task-1": manager, "task-2": manager}):
        assert active_background_agent_runs() == 2
        with track_background_agent_run():
            assert active_background_agent_runs() == 3

    assert active_background_agent_runs() == 0


def test_a_subagent_registry_entry_disappears_with_its_manager() -> None:
    """The harness registry holds managers weakly, so a manager that is gone is not a run in flight."""

    class _Manager:
        pass

    manager = _Manager()
    registry: weakref.WeakValueDictionary[str, _Manager] = weakref.WeakValueDictionary({"task-1": manager})
    with patch(_REGISTRY, registry):
        assert active_background_agent_runs() == 1
        del manager
        gc.collect()
        assert active_background_agent_runs() == 0
