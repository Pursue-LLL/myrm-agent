"""Real Chrome MCP E2E for Memory tag visibility (read contract).

Covers the user journey for memory tags on WebUI /settings/memory:

1. Seed one semantic memory with a unique tag through the real same-origin API.
2. Verify ``GET /api/v1/memory/tags`` reports it — the read converters used to
   drop the payload tag list, so tag statistics answered empty in every mode.
3. Verify the Top tags card renders that tag for the user.
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

_TAG = f"e2e-tag-{int(time.time())}"
_CONTENT = f"E2E 标签可见性校验：TypeScript strict 模式 ({_TAG})"

_SEED_JS = f"""(async () => {{
  const ids = [];
  try {{
    for (let index = 0; index < 8; index += 1) {{
      const res = await fetch('/api/v1/memory/', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          memory_type: 'semantic',
          content: '{_CONTENT} #' + index,
          importance: 0.5,
          tags: ['{_TAG}'],
        }}),
      }});
      const data = await res.json().catch(() => ({{}}));
      if (!res.ok) {{
        return {{ ok: false, status: res.status, ids }};
      }}
      if (data.id) ids.push(data.id);
    }}
    return {{ ok: true, status: 200, ids }};
  }} catch (err) {{
    return {{ ok: false, err: String(err), ids }};
  }}
}})()"""

_TAGS_JS = f"""(async () => {{
  try {{
    const res = await fetch('/api/v1/memory/tags?limit=20', {{ cache: 'no-store' }});
    const data = await res.json().catch(() => ({{}}));
    const tags = Array.isArray(data.tags) ? data.tags : [];
    return {{
      ok: res.ok,
      status: res.status,
      hit: tags.some((entry) => entry.tag === '{_TAG}'),
      totalTagged: data.total_tagged,
    }};
  }} catch (err) {{
    return {{ ok: false, err: String(err) }};
  }}
}})()"""

_TAG_CARD_JS = f"""(() => {{
  const text = document.body ? document.body.innerText : '';
  return {{ ready: text.includes('{_TAG}'), matched: text.includes('{_TAG}') }};
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
def test_memory_tags_visible_in_stats_card_chrome_e2e() -> None:
    """Browser same-origin verification that a stored tag reaches the Top tags card."""
    api_url = get_e2e_api_url()
    # The manual create path embeds the content, so the embedding must answer
    # while the memories are written; the tag round-trip is what this test guards.
    with configured_retrieval_embedding(api_url):
        prepare_e2e_ui_session(api_url)

        warm_ui_route("/settings/memory")
        with open_settings_subroute("/settings/memory", timeout_ms=90_000) as (client, page):
            dismiss_blocking_modals(client, page)

            seeded = client.evaluate(page, _SEED_JS)
            assert seeded.get("ok") is True, seeded
            memory_ids = [str(memory_id) for memory_id in (seeded.get("ids") or [])]
            assert len(memory_ids) == 8, seeded
            try:
                contract = client.evaluate(page, _TAGS_JS)
                assert contract.get("ok") is True, contract
                assert contract.get("hit") is True, contract

                reload_mcp_page(client, page, timeout_ms=90_000)
                state = wait_for_state(client, page, _TAG_CARD_JS, timeout_sec=90.0)
                assert state.get("ready") is True, state
            finally:
                for seeded_id in memory_ids:
                    client.evaluate(page, _DELETE_JS.replace("__MEMORY_ID__", seeded_id))
