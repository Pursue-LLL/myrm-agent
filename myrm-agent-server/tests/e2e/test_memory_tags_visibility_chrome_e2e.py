"""Real Chrome MCP E2E for Memory tag visibility (read contract).

Covers the user journey for memory tags on WebUI /settings/memory:

1. Seed one semantic memory with a unique tag through the real same-origin API.
2. Verify ``GET /api/v1/memory/tags`` reports it — the read converters used to
   drop the payload tag list, so tag statistics answered empty in every mode.
3. Verify the Top tags card renders that tag for the user.
4. Delete the seeded memory again (hygiene).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import put_config_value  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)
from tests.support.local_embedding_server import LocalEmbeddingServer  # noqa: E402
from tests.support.test_secrets import load_test_secrets  # noqa: E402

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


def _configure_embedding(api_url: str) -> None:
    """Configure the retrieval embedding through the same settings API the WebUI writes.

    The memory CRUD service builds a platform MemoryManager, so it needs an
    embedding provider: prefer the real test account from ``.env.test``, fall
    back to a local OpenAI-compatible endpoint. ``BAAI/bge-m3`` resolves its
    dimension synchronously, so no live embedding call happens at build time.
    """
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
    # The manual create path needs a platform embedding provider (settings-API
    # write, PRIVATE global-write lane); the tag round-trip itself is what this
    # test guards.
    _configure_embedding(api_url)

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
