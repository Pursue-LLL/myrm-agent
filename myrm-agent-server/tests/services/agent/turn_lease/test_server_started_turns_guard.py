"""Guardrail: every agent turn the server starts by itself runs under ``server_turn_lease``.

A turn that nobody's request carries can be stopped only through its chat claim and its registered cancel token, and
a stopped turn must end the background jobs it started. Every ``ai_agent_service_stream`` call under ``app/`` is
therefore either bound to a request that has its own lifecycle (listed in ``REQUEST_BOUND``) or started by the server
and wrapped in the lease (``SERVER_STARTED``). A new call site fails here until it is classified; one that claims the
chat or registers a token by hand instead of taking the lease fails too.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from functools import cache
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[4]
APP_ROOT = SERVER_ROOT / "app"

# Call sites carried by an HTTP request, a voice session or a chat stream, each with its own cancellation lifecycle.
REQUEST_BOUND: dict[str, int] = {
    "app/api/openai_compat/completions.py": 2,
    "app/api/voice/agent_bridge.py": 1,
    "app/api/voice/realtime.py": 1,
    "app/services/agent/stream_session/stream_loop.py": 1,
}

# Call sites the server starts by itself.
SERVER_STARTED: dict[str, int] = {
    "app/lifecycle/auto_continue.py": 1,
    "app/services/agent/goals/unattended/trigger.py": 1,
    "app/services/agent/streaming_support/hitl_timeout.py": 1,
}

# The wake turn a settled background task starts is a server-started turn too, but it streams through the agent
# itself rather than ``ai_agent_service_stream``; the scheduler is the one place that starts it, under the lease.
WAKE_TURN_STARTER = "app/services/agent/adaptive_wakeup/wake_turn_scheduler.py"

# The only places that may take a chat or register a cancel token themselves.
CLAIM_OWNERS: frozenset[str] = frozenset(
    {
        "app/api/chats/test_fixtures/stream_retry_busy.py",
        "app/services/agent/gateway.py",
        "app/services/agent/stream_session/orchestrator_turn_body.py",
        "app/services/agent/stream_session/session_reservation.py",
        "app/services/agent/turn_lease/lease.py",
    }
)


# Only modules that mention one of these can make a call the guard looks for; parsing the rest would only slow it down.
_NEEDLES = ("ai_agent_service_stream", "reserve_session", "CancellationRegistry", "server_turn_lease", "stream_wake_turn")


@cache
def _candidates() -> tuple[Path, ...]:
    return tuple(
        path for path in APP_ROOT.rglob("*.py") if any(needle in path.read_text(encoding="utf-8") for needle in _NEEDLES)
    )


@cache
def _calls(path: Path) -> tuple[str, ...]:
    """The callee of every call in the module as written: ``CancellationRegistry.register``, ``get_agent_gateway().reserve_session``."""
    return tuple(
        ast.unparse(node.func) for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.Call)
    )


def _files_calling(matches: Callable[[str], bool]) -> dict[str, int]:
    """Every module under ``app/`` with the number of its calls whose callee satisfies ``matches``."""
    found: dict[str, int] = {}
    for path in _candidates():
        count = sum(1 for callee in _calls(path) if matches(callee))
        if count:
            found[path.relative_to(SERVER_ROOT).as_posix()] = count
    return found


def test_every_agent_stream_call_site_is_classified_as_request_bound_or_server_started() -> None:
    assert _files_calling(lambda callee: callee.endswith("ai_agent_service_stream")) == {**REQUEST_BOUND, **SERVER_STARTED}


def test_every_server_started_turn_runs_under_the_lease() -> None:
    for relative in SERVER_STARTED:
        assert "server_turn_lease" in _calls(SERVER_ROOT / relative), f"{relative} starts a turn without the lease"


def test_only_the_lease_and_the_chat_turn_take_a_chat_or_register_a_cancel_token() -> None:
    claimers = set(_files_calling(lambda callee: callee.endswith(".reserve_session"))) | set(
        _files_calling(lambda callee: callee == "CancellationRegistry.register")
    )
    assert claimers <= CLAIM_OWNERS, f"take the chat and the token through server_turn_lease: {sorted(claimers - CLAIM_OWNERS)}"


def test_the_wake_turn_is_started_only_by_the_scheduler_and_only_under_the_lease() -> None:
    assert set(_files_calling(lambda callee: callee.endswith(".stream_wake_turn"))) == {WAKE_TURN_STARTER}
    assert "server_turn_lease" in _calls(SERVER_ROOT / WAKE_TURN_STARTER)
