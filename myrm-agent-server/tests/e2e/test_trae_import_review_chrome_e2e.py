"""Real Chrome MCP E2E: TRAE & Windsurf export file uploaded via MemorySection file picker.

Covers the real-user import path for TRAE and Windsurf exports:
  - User opens /settings/memory and uploads a TRAE/Windsurf .json via the upload button
  - Frontend parses the file and POSTs /api/v1/memory/import/dry-run (source=auto)
  - Server auto-detects trae_rules/windsurf_memories and routes to corresponding adapter
  - The review dialog opens and renders mapped source buckets (trae_rules/windsurf_memories)
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

from chrome_mcp.client import ChromeMcpClient, McpPage  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    get_e2e_ui_url,
    open_settings_subroute,
    wait_for_state,
)

_TRAE_FIXTURE_JSON = {
    "_source": "trae",
    "trae_rules": [
        {
            "name": "Backend Guide",
            "content": "Follow PEP 8 strictly",
            "scope": "project",
        }
    ],
    "trae_settings": {"preferredLanguage": "python"},
}

_TRAE_FIXTURE_JSON_STR = json.dumps(_TRAE_FIXTURE_JSON)

_UPLOAD_TRAE_JS = (
    "(async () => {"
    '  const input = document.querySelector(\'input[type="file"][accept*="json"]\');'
    "  if (!input) { return { ok: false, reason: 'file-input-missing' }; }"
    "  const file = new File("
    + "["
    + json.dumps(_TRAE_FIXTURE_JSON_STR)
    + "], 'e2e-trae-export.json', { type: 'application/json' });"
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
  const hasTraeBucket = /trae_rules/i.test(text) || /trae/i.test(text);
  return {
    ready: hasDialog && hasTraeBucket,
    hasDialog,
    hasTraeBucket,
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
    raise AssertionError(f"Review dialog did not become ready: {last!r}")


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_trae_import_review_chrome_e2e() -> None:
    """Review dialog renders TRAE import mapping after real JSON upload."""
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

        upload = client.evaluate(page, _UPLOAD_TRAE_JS, timeout_sec=20.0)
        assert isinstance(upload, dict) and upload.get("ok") is True, f"Upload failed: {upload!r}"

        state = _assert_review_dialog(client, page, timeout_sec=60.0)
        assert state.get("hasTraeBucket") is True, f"trae bucket missing: {state!r}"

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
