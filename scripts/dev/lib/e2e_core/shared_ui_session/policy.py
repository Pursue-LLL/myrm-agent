"""Search policy of a chrome_e2e item (pytest marker -> env) and the per-api empty-policy clear bookkeeping."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import Literal, Protocol

E2E_SEARCH_POLICY_ENV = "MYRM_E2E_SEARCH_POLICY"
SearchPolicy = Literal["empty", "hydrate_private"]
DEFAULT_SEARCH_POLICY: SearchPolicy = "hydrate_private"
_EMPTY_POLICY_STRONG_CLEAR_DONE: set[tuple[str, str]] = set()


def _normalize_api_url(api_url: str) -> str:
    return api_url.rstrip("/")


def _current_pytest_node_id() -> str:
    raw = os.environ.get("PYTEST_CURRENT_TEST", "").strip()
    if not raw:
        return "global"
    node_id = raw.partition(" (")[0].strip()
    return node_id or "global"


def _empty_policy_state_key(api_url: str) -> tuple[str, str]:
    return (_normalize_api_url(api_url), _current_pytest_node_id())


def _empty_policy_strong_clear_done(key: tuple[str, str]) -> bool:
    return key in _EMPTY_POLICY_STRONG_CLEAR_DONE


def _mark_empty_policy_strong_clear_done(key: tuple[str, str]) -> None:
    _EMPTY_POLICY_STRONG_CLEAR_DONE.add(key)


def _reset_empty_policy_runtime_state_for_tests() -> None:
    _EMPTY_POLICY_STRONG_CLEAR_DONE.clear()


class _PytestMarker(Protocol):
    args: tuple[object, ...]
    kwargs: dict[str, object]


def resolve_search_policy_from_item(item: object) -> SearchPolicy:
    """Map pytest markers to shared UI search policy (default hydrate_private)."""
    get_marker: Callable[[str], _PytestMarker | None] | None = getattr(item, "get_closest_marker", None)
    if not callable(get_marker):
        return DEFAULT_SEARCH_POLICY

    policy_marker = get_marker("e2e_search_policy")
    if policy_marker is not None:
        raw = (
            policy_marker.args[0]
            if policy_marker.args
            else policy_marker.kwargs.get("policy")
        )
        policy = str(raw or "").strip()
        if policy in ("empty", "hydrate_private"):
            return policy  # type: ignore[return-value]
        raise ValueError(
            f"Invalid e2e_search_policy marker value {raw!r}; "
            "expected 'empty' or 'hydrate_private'"
        )

    if get_marker("requires_empty_search_services") is not None:
        return "empty"

    return DEFAULT_SEARCH_POLICY


def prime_search_policy_env(item: object) -> SearchPolicy:
    """Persist resolved policy for bootstrap hooks (conftest autouse)."""
    policy = resolve_search_policy_from_item(item)
    os.environ[E2E_SEARCH_POLICY_ENV] = policy
    print(
        f"E2E_SHARED_UI_SESSION_POLICY: policy={policy}",
        file=sys.stderr,
        flush=True,
    )
    return policy


def current_search_policy() -> SearchPolicy | None:
    raw = os.environ.get(E2E_SEARCH_POLICY_ENV, "").strip()
    if raw in ("empty", "hydrate_private"):
        return raw  # type: ignore[return-value]
    return None
