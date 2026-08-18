"""Chrome MCP E2E: Brand Studio reset confirmation full flow.

Covers the real WebUI wiring behind the Brand Studio "Clear" action, which is a
destructive step: clearing the form and saving deletes the saved ``brand_*``
profile memories that the agent consumes.

The test drives the true flow through the real frontend (settings → brand-studio)
and asserts on real API effects:

1. Seed a ``brand_name`` profile memory through the real memory API, then open
   the brand-studio panel and confirm it renders the seeded value in the brand
   name field.
2. Click "Clear": the ``ConfirmDialog`` (``data-testid=confirm-dialog-*``) must
   appear and warn about the destructive consequence.
3. Cancel: the dialog closes and the field value is preserved.
4. Click "Clear" again and confirm: the dialog closes and the field is emptied.
5. Click "Save brand style": the real ``DELETE /memory/{key}?memory_type=profile``
   is issued and the ``brand_name`` memory is gone from the backend list.

No critical path is mocked. The flow uses the same memory API the UI calls, so it
also guards against the shared-store filter pollution bug class (the panel loads
profile memories explicitly, independent of the main memory view filters).
"""

from __future__ import annotations

import sys
import time
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
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)
from tests.support.local_embedding_server import LocalEmbeddingServer  # noqa: E402
from tests.support.test_secrets import load_test_secrets  # noqa: E402

_BRAND_STUDIO_PATH = "/settings/brand-studio"
_BRAND_NAME_KEY = "brand_name"
_MEMORY_API = "/api/v1/memory"

# Panel shell: brand-studio section title + the brand-name text input must be
# rendered after the profile memories load.
_PANEL_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTitle = /Brand Details|品牌信息/.test(text);
  const inputs = Array.from(document.querySelectorAll('input'));
  const nameInput = inputs.find((el) =>
    /e\\.g\\. Aurora Studio|例如：极光工作室/.test(el.placeholder || ''),
  );
  return {
    ready: hasTitle && !!nameInput,
    hasTitle,
    nameFound: !!nameInput,
    nameValue: nameInput?.value ?? null,
  };
})()"""

# Click the destructive "Clear" trigger button (must not match the dialog action).
_CLICK_CLEAR_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((el) =>
    /^(Clear|清空)$/.test((el.textContent || '').trim()) &&
    !el.closest('[data-testid="confirm-dialog-confirm"],[data-testid="confirm-dialog-cancel"]'),
  );
  if (!btn || btn.disabled) {
    return { clicked: false, disabled: btn?.disabled ?? null };
  }
  btn.click();
  return { clicked: true };
})()"""

# ConfirmDialog content becomes visible with the destructive warning.
_DIALOG_READY_JS = """(() => {
  const dialog = document.querySelector('[role="alertdialog"]');
  if (!dialog) return { ready: false };
  const text = dialog.textContent || '';
  return {
    ready: /Clear brand style\\?|要清空品牌风格吗[?？]/.test(text),
    hasConfirm: !!dialog.querySelector('[data-testid="confirm-dialog-confirm"]'),
    hasCancel: !!dialog.querySelector('[data-testid="confirm-dialog-cancel"]'),
    sample: text.slice(0, 160),
  };
})()"""

_CLICK_CANCEL_JS = """(() => {
  const btn = document.querySelector('[data-testid="confirm-dialog-cancel"]');
  if (!btn) return { clicked: false };
  btn.click();
  return { clicked: true };
})()"""

_CLICK_CONFIRM_JS = """(() => {
  const btn = document.querySelector('[data-testid="confirm-dialog-confirm"]');
  if (!btn || btn.disabled) return { clicked: false, disabled: btn?.disabled ?? null };
  btn.click();
  return { clicked: true };
})()"""

# After confirming, the dialog closes and the form name field is emptied.
_FORM_CLEARED_JS = """(() => {
  const dialogOpen = !!document.querySelector('[role="alertdialog"]');
  const inputs = Array.from(document.querySelectorAll('input'));
  const nameInput = inputs.find((el) =>
    /e\\.g\\. Aurora Studio|例如：极光工作室/.test(el.placeholder || ''),
  );
  return { ready: !dialogOpen && !!nameInput && (nameInput.value || '') === '' };
})()"""

_CLICK_SAVE_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((el) =>
    /Save brand style|保存品牌风格/.test(el.textContent || ''),
  );
  if (!btn || btn.disabled) return { clicked: false, disabled: btn?.disabled ?? null };
  btn.click();
  return { clicked: true };
})()"""


def _brand_memory_deleted() -> bool:
    """Query the profile memories list and report whether brand_name is gone."""
    payload = http_json(
        "GET",
        f"{get_e2e_api_url()}{_MEMORY_API}?type=profile&page_size=100",
    )
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return False
    return not any(str(item.get("key")) == _BRAND_NAME_KEY for item in items)


def _configure_embedding() -> None:
    """Configure retrieval embedding via the WebUI settings API (real path).

    A PRIVATE backend starts from an empty database, so the retrieval embedding
    must be provisioned for the Brand Studio profile store (its memory API goes
    through the same MemoryManager). Prefers the real embedding account from
    ``.env.test``; falls back to a local OpenAI-compatible endpoint when none is
    present, matching the shared backend's known-model BAAI/bge-m3 setup.
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
        put_config_value(
            "retrieval",
            {"embeddingApplied": True, "embeddingConfig": embedding_config},
            api_url=api_url,
        )
    finally:
        if server is not None:
            server.stop()


def _seed_brand_name() -> None:
    """Seed a brand_name profile memory via the real memory API (upsert)."""
    http_json(
        "POST",
        f"{get_e2e_api_url()}{_MEMORY_API}/",
        body={
            "memory_type": "profile",
            "content": "brand_name: Acme Studio",
            "key": _BRAND_NAME_KEY,
            "value": "Acme Studio",
        },
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_brand_studio_reset_confirm_full_flow_chrome_e2e() -> None:
    """Clear with confirm deletes the seeded brand memory; cancel preserves it."""
    api_base = get_e2e_api_url()

    # The Brand Studio profile store goes through the memory API, whose manager
    # requires a configured embedding backend. PRIVATE backends start empty, so
    # provision embedding via the same settings API the WebUI writes.
    _configure_embedding()
    prepare_e2e_ui_session(api_base)
    _seed_brand_name()

    warm_ui_route(_BRAND_STUDIO_PATH)
    with open_settings_subroute(_BRAND_STUDIO_PATH, timeout_ms=120_000) as (
        client,
        page,
    ):
        panel = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=60.0)
        assert panel.get("ready") is True, panel
        assert panel.get("nameValue") == "Acme Studio", panel

        # First open the destructive dialog, then cancel: value must be kept.
        first = client.evaluate(page, _CLICK_CLEAR_JS, timeout_sec=15.0)
        assert isinstance(first, dict) and first.get("clicked") is True, first

        dialog = wait_for_state(client, page, _DIALOG_READY_JS, timeout_sec=15.0)
        assert dialog.get("ready") is True, dialog
        assert dialog.get("hasConfirm") is True and dialog.get("hasCancel") is True, dialog

        cancelled = client.evaluate(page, _CLICK_CANCEL_JS, timeout_sec=15.0)
        assert isinstance(cancelled, dict) and cancelled.get("clicked") is True, cancelled

        kept = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=15.0)
        assert kept.get("ready") is True, kept
        assert kept.get("nameValue") == "Acme Studio", kept

        # Re-open, then confirm: the form is cleared (destructive step).
        second = client.evaluate(page, _CLICK_CLEAR_JS, timeout_sec=15.0)
        assert isinstance(second, dict) and second.get("clicked") is True, second

        dialog2 = wait_for_state(client, page, _DIALOG_READY_JS, timeout_sec=15.0)
        assert dialog2.get("ready") is True, dialog2

        confirmed = client.evaluate(page, _CLICK_CONFIRM_JS, timeout_sec=15.0)
        assert isinstance(confirmed, dict) and confirmed.get("clicked") is True, confirmed

        cleared = wait_for_state(client, page, _FORM_CLEARED_JS, timeout_sec=15.0)
        assert cleared.get("ready") is True, cleared

        # Save issues the real delete of the previously configured brand field.
        saved = client.evaluate(page, _CLICK_SAVE_JS, timeout_sec=15.0)
        assert isinstance(saved, dict) and saved.get("clicked") is True, saved

        deadline = time.monotonic() + 20.0
        deleted = False
        while time.monotonic() < deadline:
            if _brand_memory_deleted():
                deleted = True
                break
            time.sleep(0.5)
        assert deleted, "brand_name profile memory still present after save"
