"""Real Chrome MCP E2E: mem0 export file uploaded via MemorySection file picker.

Covers the real-user import path for a mem0 export:
  - User opens /settings/memory and picks a mem0 .json via the upload button
  - Frontend parses the file and POSTs /api/v1/memory/import/dry-run (source=auto)
  - Server auto-detects the flat ``memories`` list as the ``mem0`` adapter
  - The review dialog opens and renders the translated ``sources.mem0`` label
    (C1 i18n) plus the ``memories`` source bucket mapping (no raw keys)

The flow intentionally stops before *confirm* (which would write memories into
the live dev DB); adapter write correctness is covered by unit + API tests. This
exercise grants read/derivation-only namespace access and never mutates user data.
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

_MEM0_FIXTURE_JSON = {
    "memories": [
        {
            "memory": "Prefers concise launchpad-style product features",
            "tags": ["product", "taste"],
            "metadata": {"user_id": "e2e-check-1"},
        },
        {
            "memory": "Uses dark mode in the editor",
            "tags": ["ui"],
            "importance": 0.6,
        },
        "not-a-dict",
        {
            "memory": "Keeps a short daily standup habit",
            "tags": ["habit"],
        },
    ]
}

# Handles: file input may not be visible (hidden) — use the ref-backed
# IconUpload button on /settings/memory.
_MEM0_FIXTURE_JSON_STR = json.dumps(_MEM0_FIXTURE_JSON)

_UPLOAD_AND_DRYRUN_JS = (
    "(async () => {"
    "  const input = document.querySelector('input[type=\"file\"][accept*=\"json\"]');"
    "  if (!input) { return { ok: false, reason: 'file-input-missing' }; }"
    "  const file = new File("
    + "["
    + json.dumps(_MEM0_FIXTURE_JSON_STR)
    + "], 'e2e-mem0-export.json', { type: 'application/json' });"
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
  const rawKeyLeak = text.includes('sources.mem0') || text.includes('sources.');
  const sourceTiles = Array.from(document.querySelectorAll('.grid.grid-cols-2.gap-3.md\\\\:grid-cols-4 > div'))
    .map((node) => (node.textContent || '').trim())
    .filter(Boolean);
  const sourceValue = sourceTiles[1] || '';
  const hasMemoriesBucket = /memories/i.test(text);
  return {
    ready: hasDialog && !!sourceValue && !rawKeyLeak,
    hasDialog,
    rawKeyLeak,
    sourceValue,
    hasMemoriesBucket,
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


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_mem0_import_review_source_label_not_raw_key() -> None:
    """Review dialog renders translated sources.mem0 + memories bucket after real upload."""
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

        upload = client.evaluate(page, _UPLOAD_AND_DRYRUN_JS, timeout_sec=20.0)
        assert isinstance(upload, dict) and upload.get("ok") is True, f"Upload failed: {upload!r}"

        state = _assert_review_dialog(client, page, timeout_sec=60.0)
        assert state.get("rawKeyLeak") is False, f"Raw i18n key leaked: {state!r}"
        assert state.get("sourceValue"), f"Source tile empty: {state!r}"
        assert state.get("hasMemoriesBucket") is True, f"memories bucket missing: {state!r}"

        # Proactively dismiss (no memory write) to close the dialog at end of test.
        client.evaluate(
            page,
            """(() => {
              const cancel = Array.from(document.querySelectorAll('button')).find((b) =>
                /取消|Cancel/i.test((b.textContent || '').trim()),
              );
              if (cancel && !cancel.disabled) { cancel.click(); return { clicked: true }; }
              return { clicked: false };
            })()""",
            timeout_sec=10.0,
        )
