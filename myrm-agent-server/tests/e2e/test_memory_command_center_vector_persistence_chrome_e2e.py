"""Real Chrome MCP E2E for Memory Command Center vector persistence row.

Covers the real-user flow on the settings memory page:

1. Open /settings/memory and switch to the Verify tab.
2. Assert the Runtime panel renders the "Vector persistence" row with one of
   the three states (Persistent / Memory mode (lost on restart) / Unavailable).

This test drives the real dev stack and the real command-center API (no mock on
the critical path). It runs PRIVATE because the workspace backend carries the
new ``vector_persistence`` field that is not yet deployed to the shared :8080
epoch.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    open_settings_subroute,
    wait_for_state,
)

_OPEN_VERIFY_TAB_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => {
      const label = (el.textContent || '').trim();
      return /^(验证|Verify)$/.test(label);
    },
  );
  if (!btn) return { ready: false, clicked: false };
  btn.click();
  return { ready: true, clicked: true };
})()"""

_VECTOR_PERSISTENCE_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const hasLabel = /Vector persistence|向量持久化|向量持久性/.test(text);
  const hasState =
    /Persistent|Permanent|Memory mode \(lost on restart|Unavailable|持久|重启丢失|不可用/.test(text);
  return { ready: hasLabel && hasState, hasLabel, hasState, text: text.slice(0, 1200) };
})()"""


@contextmanager
def _command_center_verify_panel() -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    open_settings_subroute("/settings/memory", timeout_ms=120_000)
    with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (client, page):
        yield client, page


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_command_center_vector_persistence_row_chrome_e2e() -> None:
    """Real user flow: open Command Center, switch to Verify, assert persistence row."""
    with _command_center_verify_panel() as (client, page):
        opened = wait_for_state(client, page, _OPEN_VERIFY_TAB_JS, timeout_sec=60.0)
        assert opened.get("clicked") is True, opened

        panel = wait_for_state(client, page, _VECTOR_PERSISTENCE_READY_JS, timeout_sec=90.0)
        assert panel.get("ready") is True, panel
