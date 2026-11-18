"""Cross-layer contract tests for the neutral ``core/`` primitives.

These lock the SSOT identity and ContextVar wiring that keep ``toolkits/`` free of
``agent/``/``backends/`` imports: a regression here would silently reintroduce a
forbidden dependency edge even while the boundary gate still passes.
"""

from __future__ import annotations

from contextvars import copy_context

import pytest

import myrm_agent_harness.api as api
from myrm_agent_harness.agent.middlewares._session_context import (
    get_approval_session,
    set_approval_session,
)
from myrm_agent_harness.agent.resilience import task_airbag
from myrm_agent_harness.agent.resilience.task_airbag import arm_task_airbag
from myrm_agent_harness.agent.streaming.utils import set_user_timezone
from myrm_agent_harness.backends.skills.workflow_compiler import (
    DEFAULT_ALLOWED_TOOLS as COMPILER_DEFAULT_ALLOWED_TOOLS,
)
from myrm_agent_harness.core.context_vars import approval_session_var, request_timezone, scoped_value, user_timezone_var
from myrm_agent_harness.core.skill import DEFAULT_ALLOWED_TOOLS
from myrm_agent_harness.toolkits.cron.engine.parser import validate_timezone


def test_default_allowed_tools_is_the_shared_ssot() -> None:
    """The compiler re-exports the exact core object, not a divergent copy."""
    assert COMPILER_DEFAULT_ALLOWED_TOOLS is DEFAULT_ALLOWED_TOOLS
    assert api.DEFAULT_ALLOWED_TOOLS is DEFAULT_ALLOWED_TOOLS


def test_default_allowed_tools_entries_are_meaningful() -> None:
    assert isinstance(DEFAULT_ALLOWED_TOOLS, tuple)
    assert DEFAULT_ALLOWED_TOOLS, "the default allowed-tools allow-list must not be empty"
    assert all(isinstance(name, str) and name for name in DEFAULT_ALLOWED_TOOLS)


def test_task_airbag_is_reexported_from_api_security() -> None:
    """The agent-owned airbag is surfaced through the API facade unchanged."""
    from myrm_agent_harness.api.security import arm_task_airbag as api_arm_task_airbag

    assert api_arm_task_airbag is arm_task_airbag
    assert task_airbag.TaskAirbagStatus.ARMED.value == "armed"


def test_approval_session_var_is_the_cross_layer_source() -> None:
    """The core ContextVar and the agent accessor observe the same value."""
    assert approval_session_var.get() == ""
    token = approval_session_var.set("session-a")
    try:
        assert get_approval_session() == "session-a"
    finally:
        approval_session_var.reset(token)
    assert get_approval_session() == ""


def test_set_approval_session_updates_the_core_var() -> None:
    from myrm_agent_harness.core.context_vars import chat_id_var

    session_token = approval_session_var.set("")
    chat_token = chat_id_var.set("")
    try:
        set_approval_session("session-b")
        assert approval_session_var.get() == "session-b"
        assert chat_id_var.get() == "session-b"
    finally:
        chat_id_var.reset(chat_token)
        approval_session_var.reset(session_token)
    assert get_approval_session() == ""
    assert chat_id_var.get() == ""


def test_request_timezone_sees_the_zone_the_agent_runtime_sets() -> None:
    """The agent's setter and the toolkit accessor share one ContextVar."""

    def run_request() -> str | None:
        set_user_timezone("Asia/Shanghai")
        return request_timezone()

    assert copy_context().run(run_request) == "Asia/Shanghai"


@pytest.mark.parametrize(
    ("sent", "expected"),
    [
        ("Asia/Shanghai", "Asia/Shanghai"),
        ("  America/New_York  ", "America/New_York"),
        ("UTC", "UTC"),
        (None, None),
        ("", None),
        ("   ", None),
        ("Mars/Olympus", None),
        ("America", None),  # a directory of zones, not a zone
        ("../etc/passwd", None),
        ("/etc/localtime", None),
        ("Asia/Shanghai\x00", None),
        ("x" * 5000, None),
    ],
    ids=[
        "real",
        "padded",
        "utc",
        "none",
        "empty",
        "blank",
        "unknown",
        "directory",
        "relative-path",
        "absolute-path",
        "null-byte",
        "overlong",
    ],
)
def test_request_timezone_is_the_requests_zone_only_when_it_is_a_real_one(
    sent: str | None, expected: str | None
) -> None:
    with scoped_value(user_timezone_var, sent):
        assert request_timezone() == expected


@pytest.mark.parametrize(
    "name",
    [
        "Asia/Shanghai",
        "EST5EDT",
        "Etc/GMT+14",
        "America",
        "Mars/Olympus",
        "../etc/passwd",
        "Asia/Shanghai\x00",
        "x" * 5000,
    ],
)
def test_request_timezone_accepts_the_names_the_cron_validator_accepts(name: str) -> None:
    """An explicit zone of ``cron_manage`` and the zone a request carries are judged the same way."""
    with scoped_value(user_timezone_var, name):
        assert (request_timezone() is not None) == validate_timezone(name)
