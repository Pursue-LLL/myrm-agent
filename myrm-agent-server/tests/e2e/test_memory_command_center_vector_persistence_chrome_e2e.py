"""Real Chrome MCP E2E for Memory Command Center vector persistence row.

Covers the real-user flow on the settings memory page:

1. Open /settings/memory and confirm the Command Center has loaded (tabs render).
2. Switch to the Verify tab and assert the Runtime panel renders the "Vector
   persistence" row with one of the three states (Persistent / Memory mode
   (lost on restart) / Unavailable).

The command-center API needs a configured embedding model to build a
MemoryManager (``require_platform_embedding_config``). A PRIVATE backend starts
from an empty database, so the test configures retrieval embedding through the
same settings API the WebUI writes, pointing at a local OpenAI-compatible
endpoint (a supported self-hosted provider path, no external quota).

This test drives the real dev stack and the real command-center API (no mock on
the critical path). It runs PRIVATE because the workspace backend carries the
new ``vector_persistence`` field that is not yet deployed to the shared :8080
epoch.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import (  # noqa: E402
    fetch_config_value,
    get_e2e_api_url,
    put_config_value,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    ChromeMcpClient,
    McpPage,
    http_json,
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)
from tests.support.local_embedding_server import LocalEmbeddingServer  # noqa: E402

_COMMAND_CENTER_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const buttons = Array.from(document.querySelectorAll('button')).map((el) =>
    (el.textContent || '').trim(),
  );
  const hasVerifyTab = buttons.some((label) => /^(验证|Verify)$/.test(label));
  const hasSkeleton = !!document.querySelector('[data-slot="skeleton"]');
  const hasLoadFailed = /加载失败|load failed|Load failed|loadFailed/i.test(text);
  return {
    ready: hasVerifyTab,
    hasVerifyTab,
    hasSkeleton,
    hasLoadFailed,
    bodyLength: text.length,
    buttons: buttons.slice(0, 40),
    text: text.slice(0, 900),
  };
})()"""

_OPEN_VERIFY_TAB_JS = r"""(() => {
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

_VECTOR_PERSISTENCE_READY_JS = r"""(() => {
  const text = document.body?.textContent || '';
  const hasLabel = /Vector persistence|向量持久化|向量持久性/.test(text);
  const hasState =
    /Persistent|Permanent|Memory mode \(lost on restart|Unavailable|持久|重启丢失|不可用/.test(text);
  return { ready: hasLabel && hasState, hasLabel, hasState, text: text.slice(0, 1200) };
})()"""


def _configure_embedding() -> None:
    """Configure retrieval embedding via the WebUI settings API (real path)."""
    api_url = get_e2e_api_url().rstrip("/")
    existing = fetch_config_value("retrieval", api_url=api_url)
    if existing.get("embeddingConfig"):
        return

    server = LocalEmbeddingServer(port=8398)
    server.start()
    try:
        retrieval = {
            "embeddingApplied": True,
            "embeddingConfig": {
                "provider": "openai",
                "model": "test-embed-v1",
                "apiKey": "test-key",
                "apiBase": server.base_url,
            },
        }
        put_config_value("retrieval", retrieval, api_url=api_url)
        # Verify the backend can now build a memory manager (the exact path the
        # command-center API depends on) before opening the page.
        snapshot = http_json(
            "GET",
            f"{api_url}/api/v1/memory/command-center",
            expected_statuses=frozenset({200}),
        )
        assert isinstance(snapshot, dict), snapshot
        assert snapshot.get("runtime", {}).get("vector_persistence") in {
            "persistent",
            "memory_fallback",
            "unavailable",
        }, snapshot
    finally:
        server.stop()


@contextmanager
def _command_center_verify_panel() -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    _configure_embedding()
    warm_ui_route("/settings/memory")
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
        ready = wait_for_state(client, page, _COMMAND_CENTER_READY_JS, timeout_sec=90.0)
        assert ready.get("hasVerifyTab") is True, ready

        opened = wait_for_state(client, page, _OPEN_VERIFY_TAB_JS, timeout_sec=30.0)
        assert opened.get("clicked") is True, opened

        panel = wait_for_state(client, page, _VECTOR_PERSISTENCE_READY_JS, timeout_sec=90.0)
        assert panel.get("ready") is True, panel
