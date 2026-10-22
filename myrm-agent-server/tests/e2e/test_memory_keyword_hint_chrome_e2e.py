"""Real Chrome MCP E2E for the keyword-mode hint on /settings/memory.

A zero-config deployment (no embedding model configured) must tell the user
that recall runs on keywords and how to upgrade to semantic recall. The hint
renders from the retrieval config alone (``enableMemory && !embeddingApplied``),
so this node pins the user-visible copy without touching the memory APIs.
"""

from __future__ import annotations

import sys
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
    wait_for_state,
    warm_ui_route,
)

_HINT_TEXT = "当前为关键词记忆模式"

_HINT_JS = f"""(() => {{
  const text = document.body ? document.body.innerText : '';
  return {{ ready: text.includes('{_HINT_TEXT}'), matched: text.includes('{_HINT_TEXT}') }};
}})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_memory_keyword_hint_visible_without_embedding_chrome_e2e() -> None:
    """The zero-config keyword-mode hint must reach the memory settings page."""
    api_url = get_e2e_api_url()
    # Same settings path the WebUI writes when a user has no embedding model.
    put_config_value("retrieval", {"embeddingApplied": False}, api_url=api_url)

    prepare_e2e_ui_session(api_url)

    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        state = wait_for_state(client, page, _HINT_JS, timeout_sec=90.0)
        assert state.get("ready") is True, state
