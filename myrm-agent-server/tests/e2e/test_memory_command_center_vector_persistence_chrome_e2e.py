"""Real Chrome MCP E2E for Memory Command Center vector persistence row.

Covers the real-user flow on the settings memory page:

1. Open /settings/memory and confirm the Command Center has loaded (tabs render).
2. Switch to the Verify tab and assert the Memory Doctor panel exposes the
   "Vector index" static check whose status derives from the same runtime
   snapshot (persistence-aware via ``probe_vector_index``).
3. Assert the Runtime panel renders the "Vector persistence" row with one of
   the three states (Persistent / Memory mode (lost on restart) / Unavailable).

The command-center API needs a configured embedding model to build a
MemoryManager. A PRIVATE backend starts from an empty database, so the test
configures retrieval embedding through the same settings API the WebUI writes.
It prefers the real SiliconFlow embedding account from ``.env.test`` (the
exact provider a user configures in the WebUI settings page, stored in the
database); a local OpenAI-compatible endpoint is used only as a fallback when
no test embedding account exists. The model ``BAAI/bge-m3`` is a known model
whose dimension is resolved synchronously (no live embedding call needed),
matching how the shared backend is configured.

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
from tests.support.test_secrets import load_test_secrets  # noqa: E402

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
  const rows = Array.from(document.querySelectorAll('span.text-xs.text-muted-foreground'));
  const target = rows.find((el) => /Vector persistence|向量存储持久化/.test(el.textContent || ''));
  if (!target) return { ready: false, matchedLabel: false, labelRows: rows.length };
  const valueEl = target.nextElementSibling;
  const value = valueEl ? valueEl.textContent.trim() : '';
  const ok =
    /Persistent|Memory mode \(lost on restart|Unavailable|持久化|内存模式|不可用/.test(value);
  return { ready: ok, matchedLabel: true, value, labelRows: rows.length };
})()"""

_VECTOR_INDEX_DOCTOR_READY_JS = """(() => {
  const labels = Array.from(document.querySelectorAll('div.text-sm.font-medium'));
  const target = labels.find((el) => /Vector index|向量索引/.test(el.textContent || ''));
  if (!target) return { ready: false, matchedLabel: false, labelCount: labels.length };
  let card = target.parentElement;
  while (card && !(card.className && String(card.className).includes('rounded-lg'))) {
    card = card.parentElement;
  }
  const pill = card ? card.querySelector('span.rounded-full.border') : null;
  const pillText = pill ? pill.textContent.trim() : '';
  const statusOk =
    /Ready|Warning|Missing|Critical|就绪|警告|缺失|严重/.test(pillText);
  return { ready: statusOk, matchedLabel: true, pillText };
})()"""


def _configure_embedding() -> None:
    """Configure retrieval embedding via the WebUI settings API (real path).

    Uses the real SiliconFlow embedding account from ``.env.test`` first (the
    same provider the WebUI settings page writes into the database for a real
    user). ``BAAI/bge-m3`` is a known-dimension model so the MemoryManager is
    built without any live embedding call. Falls back to a local
    OpenAI-compatible endpoint only when no test embedding account is present.
    """
    api_url = get_e2e_api_url().rstrip("/")
    existing = fetch_config_value("retrieval", api_url=api_url)
    if existing.get("embeddingConfig"):
        return

    secrets = load_test_secrets()
    embedding_key = secrets.get("EMBEDDING_API_KEY")
    server: LocalEmbeddingServer | None = None
    try:
        if embedding_key:
            embedding_config = {
                "provider": secrets.get("EMBEDDING_PROVIDER", "siliconflow"),
                "model": secrets.get("EMBEDDING_MODEL", "BAAI/bge-m3"),
                "apiKey": embedding_key,
                "apiBase": secrets.get("EMBEDDING_BASE_URL", ""),
            }
        else:
            server = LocalEmbeddingServer(port=8398)
            server.start()
            embedding_config = {
                "provider": "openai_compatible",
                "model": "BAAI/bge-m3",
                "apiKey": "test-key",
                "apiBase": server.base_url,
            }
        retrieval = {
            "embeddingApplied": True,
            "embeddingConfig": embedding_config,
        }
        put_config_value("retrieval", retrieval, api_url=api_url)
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
        if server is not None:
            server.stop()


@contextmanager
def _command_center_verify_panel() -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    _configure_embedding()
    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (
        client,
        page,
    ):
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
    """Real user flow: open Command Center, verify Doctor + Runtime persistence rows."""
    with _command_center_verify_panel() as (client, page):
        ready = wait_for_state(client, page, _COMMAND_CENTER_READY_JS, timeout_sec=90.0)
        assert ready.get("hasVerifyTab") is True, ready

        # Verify tab renders both the Memory Doctor panel (vector_index static
        # check) and the Runtime panel (vector_persistence row).
        opened = wait_for_state(client, page, _OPEN_VERIFY_TAB_JS, timeout_sec=30.0)
        assert opened.get("clicked") is True, opened

        doctor = wait_for_state(client, page, _VECTOR_INDEX_DOCTOR_READY_JS, timeout_sec=90.0)
        assert doctor.get("ready") is True, doctor

        panel = wait_for_state(
            client, page, _VECTOR_PERSISTENCE_READY_JS, timeout_sec=90.0
        )
        assert panel.get("ready") is True, panel
