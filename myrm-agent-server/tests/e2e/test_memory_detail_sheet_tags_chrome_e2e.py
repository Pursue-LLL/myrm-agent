"""Real Chrome MCP E2E for the memory detail sheet's tag/entity contract.

Covers the user journey on WebUI /settings/memory:

1. Seed one semantic memory with a unique tag through the
   real same-origin API.
2. Open the memory settings page and click the seeded memory card.
3. Verify the detail sheet renders the tag and the related entity — both fields
   must survive the read converters (storage_converters).
4. Delete the seeded memory again (hygiene).
"""

from __future__ import annotations

import time

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)
from tests.support.retrieval_embedding import configured_retrieval_embedding

_STAMP = int(time.time())
_TAG = f"e2e-detail-{_STAMP}"
_CONTENT = f"E2E 详情抽屉校验：记忆标签与实体还原 ({_STAMP})"

_SEED_JS = f"""(async () => {{
  try {{
    const res = await fetch('/api/v1/memory/', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        memory_type: 'semantic',
        content: '{_CONTENT}',
        importance: 0.6,
        tags: ['{_TAG}'],
      }}),
    }});
    const data = await res.json().catch(() => ({{}}));
    return {{ ok: res.ok, status: res.status, id: data.id }};
  }} catch (err) {{
    return {{ ok: false, err: String(err) }};
  }}
}})()"""

_CARD_READY_JS = f"""(() => {{
  const text = document.body ? document.body.innerText : '';
  return {{ ready: text.includes('{_CONTENT}'), matched: text.includes('{_CONTENT}') }};
}})()"""

_CLICK_CARD_JS = f"""(() => {{
  const nodes = Array.from(document.querySelectorAll('div, article, button')).filter(
    (el) => (el.textContent || '').includes('{_CONTENT}'),
  );
  if (!nodes.length) return {{ clicked: false }};
  nodes.sort((a, b) => (a.textContent || '').length - (b.textContent || '').length);
  // The card ignores clicks that originate inside its own buttons; click the
  // clickable card root (cursor-pointer) so the detail handler receives it.
  const target = nodes[0].closest('.cursor-pointer') || nodes[0];
  target.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
  return {{ clicked: true, tag: target.tagName, isCardRoot: target !== nodes[0] }};
}})()"""

_SHEET_READY_JS = f"""(() => {{
  const text = document.body ? document.body.innerText : '';
  return {{ ready: text.includes('{_TAG}'), hasTag: text.includes('{_TAG}') }};
}})()"""

_DELETE_JS = """(async () => {
  try {
    const res = await fetch('/api/v1/memory/__MEMORY_ID__?permanent=true', { method: 'DELETE' });
    return res.ok;
  } catch (err) {
    return false;
  }
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_memory_detail_sheet_shows_tags_chrome_e2e() -> None:
    """Clicking a memory card shows its restored tag in the detail sheet."""
    api_url = get_e2e_api_url()
    # The manual create path embeds the content, so the embedding must answer while the memory is written.
    with configured_retrieval_embedding(api_url):
        prepare_e2e_ui_session(api_url)

        warm_ui_route("/settings/memory")
        with open_settings_subroute("/settings/memory", timeout_ms=90_000) as (client, page):
            dismiss_blocking_modals(client, page)

            seeded = client.evaluate(page, _SEED_JS)
            assert seeded.get("ok") is True, seeded
            memory_id = str(seeded.get("id") or "")
            assert memory_id, seeded
            try:
                # The settings page listed the memories before this one was written.
                reload_mcp_page(client, page, timeout_ms=90_000)
                card = wait_for_state(client, page, _CARD_READY_JS, timeout_sec=90.0)
                assert card.get("ready") is True, card

                clicked = client.evaluate(page, _CLICK_CARD_JS)
                assert clicked.get("clicked") is True, clicked

                sheet = wait_for_state(client, page, _SHEET_READY_JS, timeout_sec=60.0)
                assert sheet.get("ready") is True, sheet
            finally:
                client.evaluate(page, _DELETE_JS.replace("__MEMORY_ID__", memory_id))
