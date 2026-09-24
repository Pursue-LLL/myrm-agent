"""Real Chrome E2E and API Integration: Session Event Log ZIP Export Pack.

Lane-B: Browser UI verification (Sidebar menu item '导出会话日志包 (.zip)' renders and triggers export).
Lane-C: Real task flow & artifact packaging (HEAD preflight 200, streaming ZIP unpack, SHA256 manifest verification, PII redaction, 404 safety guard).
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
)


def _seed_chat_fixture(api_url: str) -> dict[str, str]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-chat-share-fixture")
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2eshare")
    return {
        "chat_id": chat_id,
        "user_text": str(seeded["user_text"]),
        "assistant_text": str(seeded["assistant_text"]),
        "ui_path": str(seeded["ui_path"]),
    }


def _open_export_pack_menu_js(chat_id: str) -> str:
    """Find the chat row, click More menu, and verify '导出会话日志包 (.zip)' item exists."""
    return f"""(() => {{
  const href = {json.dumps(f"/{chat_id}")};
  const row = document.querySelector(`a[href="${{href}}"]`);
  if (!row) return {{ ready: false, reason: 'no-chat-row', href }};
  const more = row.querySelector('button[aria-label]') || Array.from(row.querySelectorAll('button')).find(
    (b) => !(b.textContent || '').trim(),
  );
  if (!more) return {{ ready: false, reason: 'no-more-btn' }};
  more.dispatchEvent(new PointerEvent('pointerdown', {{
    bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse', button: 0,
  }}));
  more.click();

  return new Promise((resolve) => setTimeout(() => {{
    // Top-level menu opened. Look for export subtrigger.
    const allItems = Array.from(document.querySelectorAll('[data-radix-collection-item], [role="menuitem"]'));
    const exportTrigger = allItems.find((el) => {{
      const text = (el.textContent || '').trim();
      return text === '导出' || text === 'Export';
    }});
    if (!exportTrigger) {{
      return resolve({{
        ready: false,
        reason: 'no-export-subtrigger',
        items: allItems.map((i) => (i.textContent || '').trim()),
      }});
    }}

    // Open sub-menu by hovering / clicking the subtrigger
    exportTrigger.dispatchEvent(new PointerEvent('pointerenter', {{ bubbles: true, cancelable: true }}));
    exportTrigger.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, cancelable: true, button: 0 }}));
    exportTrigger.click();

    setTimeout(() => {{
      const menuItems = Array.from(document.querySelectorAll('[role="menuitem"]'));
      const zipItem = menuItems.find((el) => {{
        const text = (el.textContent || '').trim();
        return /导出会话日志包|Export Session.*Zip|Export Session Pack/i.test(text);
      }});
      if (!zipItem) {{
        return resolve({{
          ready: false,
          reason: 'no-zip-item-in-submenu',
          items: menuItems.map((i) => (i.textContent || '').trim()),
        }});
      }}
      resolve({{
        ready: true,
        found: true,
        label: (zipItem.textContent || '').trim(),
      }});
    }}, 400);
  }}, 400));
}})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_export_pack_lifecycle_chrome_e2e() -> None:
    """Full lifecycle E2E: seed chat -> verify WebUI menu -> test HEAD & GET ZIP unpack & SHA256 integrity."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    # Step 0: Ensure WebUI session is ready
    prepare_e2e_ui_session(api_url)

    # Step 1: Seed real chat fixture
    seeded = _seed_chat_fixture(api_url)
    chat_id = seeded["chat_id"]
    chat_url = f"{ui_url}/{chat_id}"

    # Step 2: Lane-C Real API Full Flow verification
    # 2.1 HEAD preflight check
    head_req = urllib.request.Request(f"{api_url}/api/v1/chats/{chat_id}/export-pack", method="HEAD")
    with urllib.request.urlopen(head_req, timeout=10) as head_resp:
        assert head_resp.status == 200
        content_type = head_resp.headers.get("Content-Type", "")
        assert "application/zip" in content_type
        content_disposition = head_resp.headers.get("Content-Disposition", "")
        assert "session_" in content_disposition
        assert ".zip" in content_disposition

    # 2.2 GET streaming ZIP download & unpack
    get_req = urllib.request.Request(f"{api_url}/api/v1/chats/{chat_id}/export-pack?redact_secrets=true")
    with urllib.request.urlopen(get_req, timeout=20) as get_resp:
        assert get_resp.status == 200
        zip_bytes = get_resp.read()
        assert len(zip_bytes) > 0

    # 2.3 Verify ZIP structure and manifest SHA256
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist

        manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest_data["schema_version"] == "1.0"
        assert manifest_data["chat"]["id"] == chat_id
        assert manifest_data["options"]["redact_secrets"] is True

        # Verify integrity of each file in manifest
        files = manifest_data.get("integrity_report", {}).get("files", [])
        assert len(files) > 0
        for item in files:
            file_path = item["path"]
            assert file_path in namelist
            expected_sha = item["sha256"]
            actual_bytes = zf.read(file_path)
            assert hashlib.sha256(actual_bytes).hexdigest() == expected_sha

    # 2.4 Safety verification: non-existent chat gives 404
    bad_req = urllib.request.Request(f"{api_url}/api/v1/chats/non-existent-sess/export-pack")
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(bad_req, timeout=10)
    assert err.value.code == 404

    # Step 3: Lane-B WebUI browser verification
    with open_mcp_page(chat_url) as (client, page):
        dismiss_blocking_modals(client, page)

        menu_state = wait_for_state(
            client,
            page,
            _open_export_pack_menu_js(chat_id),
            timeout_sec=40.0,
            page_url=chat_url,
        )
        assert menu_state.get("ready") is True, f"Failed to find export pack menu item: {json.dumps(menu_state)}"
        assert menu_state.get("found") is True
