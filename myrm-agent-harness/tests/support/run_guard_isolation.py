"""Keep the per-run guard registries a test leaves behind away from the next test (a pytest plugin).

[INPUT]
- agent.middlewares._session_context::isolated_terminal_errors (POS: the terminal-error registry, scoped by a ``with`` block)
- agent.middlewares.completion.completion_guard.state::_run_states / _run_disclosures (POS: the completion guard's turn state and
  disclosure payload, keyed by the bound message id, or by one shared slot when none is bound)

[OUTPUT]
- _isolate_run_guard_registries: autouse fixture; every test starts, and ends, with these registries empty

[POS]
Registered from ``tests/conftest.py`` (``pytest_plugins``). A direct executor run never calls ``reset_all_guards``, so
what a test leaves in these registries stays in the worker process until another test reads it: a ``network_blocked``
makes the circuit breaker refuse the next test's MCP tool, and a disclosure published with no message bound lands on the
shared slot that the next ``post_run_events`` call attaches to its event. Which test ran before which depends on how
xdist hands out the classes, so without this the same code passes in one run and fails in the next.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_run_guard_registries() -> Iterator[None]:
    from myrm_agent_harness.agent.middlewares._session_context import isolated_terminal_errors
    from myrm_agent_harness.agent.middlewares.completion.completion_guard import state

    with (
        isolated_terminal_errors(),
        patch.dict(state._run_states, clear=True),
        patch.dict(state._run_disclosures, clear=True),
    ):
        yield
