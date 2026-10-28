"""A run binds its security config and opens its directory grants in one step, so no entry point can do one without the other."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from myrm_agent_harness.agent._internals._agent_helpers import bind_run_security
from myrm_agent_harness.agent.middlewares._session_context import get_security_config, set_security_config
from myrm_agent_harness.agent.security.types import PathPolicy, PrivacyPolicy, SecurityConfig
from myrm_agent_harness.core.context_vars import (
    access_grants_var,
    reachable_access_roots,
    scoped_value,
    session_access_roots_var,
)
from myrm_agent_harness.core.security.types import AccessRoot

DECLARED = AccessRoot(path="/declared", writable=False, source="declared")
SESSION = AccessRoot(path="/session", writable=True, source="path_ask_grant")


@pytest.fixture(autouse=True)
def _isolated_run() -> Iterator[None]:
    with scoped_value(access_grants_var, None), scoped_value(session_access_roots_var, ()):
        yield
    set_security_config(None)


def _security(*roots: AccessRoot) -> SecurityConfig:
    return SecurityConfig(
        yolo_mode_enabled=False,
        privacy_policy=PrivacyPolicy(enabled=False),
        path_policy=PathPolicy(forbidden_paths=frozenset(), access_roots=roots),
    )


def test_the_bound_config_is_the_one_the_run_reads() -> None:
    config = _security(DECLARED)

    bind_run_security(config)

    assert get_security_config() is config


def test_the_run_opens_with_the_declared_roots_and_the_session_grants_the_host_seeded() -> None:
    session_access_roots_var.set((SESSION,))

    bind_run_security(_security(DECLARED))

    grants = access_grants_var.get()
    assert grants is not None
    assert grants.declared == (DECLARED,)
    assert reachable_access_roots() == (DECLARED, SESSION)
