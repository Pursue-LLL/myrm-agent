"""``CronManagerPort`` restates a subset of ``CronManager``'s signatures by hand.

A parameter renamed or retyped on the manager would leave the port promising something the manager no longer
accepts, and callers typed against the port would fail only at run time. These checks pin the two together.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.cron.manager_port import CronManagerPort

PORT_METHODS = sorted(
    name for name, _ in inspect.getmembers(CronManagerPort, inspect.isfunction) if not name.startswith("_")
)


def _parameters(function: Callable[..., object]) -> dict[str, inspect.Parameter]:
    return {name: param for name, param in inspect.signature(function).parameters.items() if name != "self"}


def test_port_declares_the_eight_operations_the_tool_and_heartbeat_use() -> None:
    assert PORT_METHODS == [
        "create_job",
        "delete_job",
        "get_job",
        "list_jobs",
        "pause_job",
        "resume_job",
        "run_now",
        "update_job",
    ]


@pytest.mark.parametrize("method", PORT_METHODS)
def test_manager_accepts_every_parameter_the_port_declares(method: str) -> None:
    manager_params = _parameters(getattr(CronManager, method))

    for name, declared in _parameters(getattr(CronManagerPort, method)).items():
        assert name in manager_params, f"{method}: the manager has no parameter {name!r}"
        actual = manager_params[name]
        assert actual.kind == declared.kind, f"{method}.{name}: kind {actual.kind} != {declared.kind}"
        assert actual.annotation == declared.annotation, (
            f"{method}.{name}: {actual.annotation} != {declared.annotation}"
        )
        has_default = actual.default is not inspect.Parameter.empty
        declares_default = declared.default is not inspect.Parameter.empty
        assert has_default == declares_default, f"{method}.{name}: default presence differs"


@pytest.mark.parametrize("method", PORT_METHODS)
def test_manager_returns_what_the_port_declares(method: str) -> None:
    manager_method = getattr(CronManager, method)
    port_method = getattr(CronManagerPort, method)

    assert inspect.iscoroutinefunction(manager_method) and inspect.iscoroutinefunction(port_method)
    assert inspect.signature(manager_method).return_annotation == inspect.signature(port_method).return_annotation
