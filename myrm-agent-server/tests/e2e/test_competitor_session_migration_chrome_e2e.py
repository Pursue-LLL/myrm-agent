"""Real Chrome MCP E2E: Competitor session migration review and preview rendering.

Covers the real-user import path for cross-tool session transcripts:
  - User opens /settings/memory and uploads a competitor export .json with session data
  - Frontend auto-detects codex sessions and POSTs /api/v1/memory/import/dry-run
  - Server normalizes transcripts into canonical turns and returns session previews
  - The review dialog opens and renders mapped source buckets and session metadata
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from chrome_mcp.client import ChromeMcpClient, McpPage  # type: ignore[import-not-found]  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # type: ignore[import-not-found]  # noqa: E402
    get_e2e_ui_url,
    open_settings_subroute,
    wait_for_state,
)

_CODEX_SESSION_FIXTURE = {
    "_source": "codex",
    "codex_sessions": [
        {
            "id": "codex-e2e-migrate-01",
            "created_at": 1700000000.0,
            "title": "Refactor Order Service Architecture",
            "messages": [
                {"role": "user", "content": "Analyze and refactor the checkout workflow"},
                {
                    "role": "assistant",
                    "content": "Inspecting checkout handler",
                    "tool_calls": [
                        {
                            "id": "tc-order-1",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path": "/Users/dev/order/checkout.py"}',
                            },
                            "output": "def process_payment(): pass\n",
                        }
                    ],
                },
            ],
        }
    ],
    "codex_config": {"model": "gpt-4o"},
}

_CODEX_SESSION_FIXTURE_JSON_STR = json.dumps(_CODEX_SESSION_FIXTURE)

_UPLOAD_CODEX_JS = (
    "(async () => {"
    '  const input = document.querySelector(\'input[type="file"][accept*="json"]\');'
    "  if (!input) { return { ok: false, reason: 'file-input-missing' }; }"
    "  const file = new File("
    + "["
    + json.dumps(_CODEX_SESSION_FIXTURE_JSON_STR)
    + "], 'e2e-codex-session-export.json', { type: 'application/json' });"
    "  const transfer = new DataTransfer();"
    "  transfer.items.add(file);"
    "  input.files = transfer.files;"
    "  input.dispatchEvent(new Event('input', { bubbles: true }));"
    "  input.dispatchEvent(new Event('change', { bubbles: true }));"
    "  return { ok: true };"
    "})()"
)

_REVIEW_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasDialog = /来源|Source/i.test(text) && /可导入|mapped/i.test(text);
  const hasCodexBucket = /codex/i.test(text) || /Refactor Order Service/i.test(text);
  return {
    ready: hasDialog && hasCodexBucket,
    hasDialog,
    hasCodexBucket,
    bodySnippet: text.slice(0, 400),
  };
})()"""


def _assert_review_dialog(
    client: ChromeMcpClient,
    page: McpPage,
    timeout_sec: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        raw = client.evaluate(page, _REVIEW_READY_JS, timeout_sec=20.0)
        last = raw if isinstance(raw, dict) else {}
        if last.get("ready") is True:
            return last
        time.sleep(0.5)
    raise AssertionError(f"Review dialog did not become ready for codex session import: {last!r}")


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_competitor_session_migration_chrome_e2e() -> None:
    """Review dialog renders Codex competitor session import mapping after real JSON upload."""
    ui_base = get_e2e_ui_url().rstrip("/")
    page_url = f"{ui_base}/settings/memory"

    with open_settings_subroute(
        "/settings/memory",
        layout_timeout_sec=120.0,
    ) as (client, page):
        memory_ready = wait_for_state(
            client,
            page,
            """(() => {
              const text = document.body?.innerText || '';
              const hasImport = !!document.querySelector('input[type="file"][accept*="json"]');
              return { ready: hasImport && text.length > 0 };
            })()""",
            timeout_sec=90.0,
            page_url=page_url,
            blank_heal_mode="direct",
        )
        assert memory_ready.get("ready") is True, f"MemorySection not ready: {memory_ready!r}"

        upload = client.evaluate(page, _UPLOAD_CODEX_JS, timeout_sec=20.0)
        assert isinstance(upload, dict) and upload.get("ok") is True, f"Upload failed: {upload!r}"

        state = _assert_review_dialog(client, page, timeout_sec=60.0)
        assert state.get("hasCodexBucket") is True, f"codex bucket missing: {state!r}"

        # Close dialog cleanly
        client.evaluate(
            page,
            """(() => {
              const cancel = Array.from(document.querySelectorAll('button')).find(
                b => /取消|Cancel|关闭|Close/i.test(b.textContent || '')
              );
              if (cancel) cancel.click();
            })()""",
            timeout_sec=10.0,
        )
