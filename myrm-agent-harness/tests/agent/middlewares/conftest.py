"""Session-context isolation for the middleware test suite.

Middleware tests configure the per-run session ContextVars (workspace root,
security config, approval session, subagent flags, ...). Without teardown those
values leak into later tests in the same process, which makes default-value and
subagent assertions order-dependent. Resetting the session context after every
test keeps each test on the documented defaults.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.middlewares._session_context import (
    set_allowed_domains_map,
    set_approval_session,
    set_approval_user_id,
    set_event_logger,
    set_is_subagent,
    set_security_config,
    set_subagent_task_id,
    set_workspace_root,
)
from myrm_agent_harness.agent.middlewares.completion import completion_guard
from tests.support.completion_guard_harness import GUARD_DECISIONS


@pytest.fixture(autouse=True)
def _record_guard_decisions(monkeypatch: pytest.MonkeyPatch):
    """Keep the reasons of every answer the completion guard holds back, for tests that read what it found."""
    GUARD_DECISIONS.clear()
    log_decision = completion_guard.log_guard_decision

    async def recording(reasons, **kwargs):
        GUARD_DECISIONS.append(reasons)
        await log_decision(reasons, **kwargs)

    monkeypatch.setattr(completion_guard, "log_guard_decision", recording)


@pytest.fixture(autouse=True)
def _reset_session_context_after_test():
    yield
    set_security_config(None)
    set_workspace_root("")
    set_approval_session("")
    set_approval_user_id("")
    set_event_logger(None)
    set_is_subagent(False)
    set_subagent_task_id(None)
    set_allowed_domains_map({})
