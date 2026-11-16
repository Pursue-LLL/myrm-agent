"""Real Chrome MCP E2E for Memory Command Center vector persistence row.

Covers the real-user flow on the settings memory page:

1. Open /settings/memory and confirm the Command Center has loaded (tabs render).
2. Switch to the Verify tab and assert the Memory Doctor panel exposes the
   "Vector index" static check whose status derives from the same runtime
   snapshot (persistence-aware via ``probe_vector_index``).
3. Assert the Runtime panel renders the "Vector persistence" row with one of
   the three states (Persistent / Memory mode (lost on restart) / Unavailable).

The command-center API needs a retrieval embedding to build a MemoryManager. The
test gets one from ``configured_retrieval_embedding``: the account the stack seeded
when it can embed, else a ``.env.test`` account, written through the same settings
API the WebUI uses. It fails when no account can embed.

This test drives the real dev stack and the real command-center API (no mock on
the critical path). It runs PRIVATE because the workspace backend carries the
new ``vector_persistence`` field that is not yet deployed to the shared backend
epoch.

The Command Center is a Memory Labs surface: the node needs a runtime started with
both Labs switches on and skips, naming the command, on one that was not. Formal run::

    MYRM_MEMORY_LABS=1 NEXT_PUBLIC_MEMORY_LABS=1 ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_memory_command_center_vector_persistence_chrome_e2e.py
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

from cdp_chat.support import get_e2e_api_url  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    ChromeMcpClient,
    McpPage,
    http_json,
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)
from tests.support.memory_labs import require_memory_labs  # noqa: E402
from tests.support.retrieval_embedding import configured_retrieval_embedding  # noqa: E402

# Visible text only: ``textContent`` also carries the inline scripts, and the message bundle in their payload has the
# key ``loadFailed``, which the pattern below matches.
_COMMAND_CENTER_READY_JS = """(() => {
  const text = document.body?.innerText || '';
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


def _assert_runtime_snapshot(api_url: str) -> None:
    """The command-center API builds its MemoryManager from the retrieval embedding and reports how vectors persist."""
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


@contextmanager
def _command_center_verify_panel() -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    api_url = get_e2e_api_url().rstrip("/")
    with configured_retrieval_embedding(api_url):
        _assert_runtime_snapshot(api_url)
        warm_ui_route("/settings/memory")
        with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (
            client,
            page,
        ):
            yield client, page


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_command_center_vector_persistence_row_chrome_e2e() -> None:
    """Real user flow: open Command Center, verify Doctor + Runtime persistence rows."""
    require_memory_labs(get_e2e_api_url())
    with _command_center_verify_panel() as (client, page):
        ready = wait_for_state(client, page, _COMMAND_CENTER_READY_JS, timeout_sec=90.0)
        assert ready.get("hasVerifyTab") is True, ready

        # Verify tab renders both the Memory Doctor panel (vector_index static
        # check) and the Runtime panel (vector_persistence row).
        opened = wait_for_state(client, page, _OPEN_VERIFY_TAB_JS, timeout_sec=30.0)
        assert opened.get("clicked") is True, opened

        doctor = wait_for_state(client, page, _VECTOR_INDEX_DOCTOR_READY_JS, timeout_sec=90.0)
        assert doctor.get("ready") is True, doctor

        panel = wait_for_state(client, page, _VECTOR_PERSISTENCE_READY_JS, timeout_sec=90.0)
        assert panel.get("ready") is True, panel
