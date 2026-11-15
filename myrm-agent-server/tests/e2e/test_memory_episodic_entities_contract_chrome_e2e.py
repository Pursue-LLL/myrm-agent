"""Real Chrome MCP E2E for the episodic memory related-entity contract.

Covers the user journey on WebUI /settings/memory:

1. Seed one episodic memory with a unique related entity through the real
   same-origin API (episodic memories are the type that carries entities).
2. Open the memory settings page and click the seeded memory card.
3. Verify the episodic list API returns the entity and the memory card renders —
   the read converter must carry ``related_entities`` from the payload metadata.
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
_ENTITY = f"E2E-Entity-{_STAMP}"
_CONTENT = f"E2E 详情抽屉校验：情景记忆关联实体还原 ({_STAMP})"

_SEED_JS = f"""(async () => {{
  try {{
    const res = await fetch('/api/v1/memory/', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        memory_type: 'episodic',
        content: '{_CONTENT}',
        importance: 0.6,
        related_entities: ['{_ENTITY}'],
      }}),
    }});
    const data = await res.json().catch(() => ({{}}));
    return {{ ok: res.ok, status: res.status, id: data.id }};
  }} catch (err) {{
    return {{ ok: false, err: String(err) }};
  }}
}})()"""

_ENTITY_CONTRACT_JS = f"""(async () => {{
  try {{
    const res = await fetch('/api/v1/memory/?type=episodic&page_size=100', {{ cache: 'no-store' }});
    const data = await res.json().catch(() => ({{}}));
    const items = Array.isArray(data.items) ? data.items : [];
    const hit = items.find((item) => String(item.content || '').includes('{_STAMP}'));
    return {{
      ok: res.ok,
      status: res.status,
      found: Boolean(hit),
      entities: hit ? hit.related_entities : null,
      hasEntity: Boolean(hit) && Array.isArray(hit.related_entities) && hit.related_entities.includes('{_ENTITY}'),
    }};
  }} catch (err) {{
    return {{ ok: false, err: String(err) }};
  }}
}})()"""

_CARD_READY_JS = f"""(() => {{
  const text = document.body ? document.body.innerText : '';
  return {{ ready: text.includes('{_CONTENT}'), matched: text.includes('{_CONTENT}') }};
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
def test_memory_episodic_entities_contract_chrome_e2e() -> None:
    """An episodic memory keeps its related entity through write, list and render."""
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
                contract = client.evaluate(page, _ENTITY_CONTRACT_JS)
                assert contract.get("ok") is True, contract
                assert contract.get("found") is True, contract
                assert contract.get("hasEntity") is True, contract

                # The settings page listed the memories before this one was written.
                reload_mcp_page(client, page, timeout_ms=90_000)
                card = wait_for_state(client, page, _CARD_READY_JS, timeout_sec=90.0)
                assert card.get("ready") is True, card
            finally:
                client.evaluate(page, _DELETE_JS.replace("__MEMORY_ID__", memory_id))
