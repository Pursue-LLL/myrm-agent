"""Chrome LIVE Lane-C E2E: a catalog remote MCP serves a real agent turn.

Machinery proof for the catalog-connect path that credential-gated chains
(such as the Postiz draft test) build on, exercised end to end with the
credential-free Microsoft Learn entry:

1. Connect the hosted MCP from the real Service Directory UI (remote
   entries skip the localhost probe and pass the security gate), so the
   MCP config is persisted through the settings store.
2. Bind the saved server to a fresh agent by name (``mcp_ids``) and read
   the binding back.
3. Send a real chat turn whose answer requires the MCP's documentation
   tools; the completed reply must carry a learn.microsoft.com link.

The PRIVATE namespace is ephemeral, so the saved config, agent, and chat
are destroyed with the runtime at seal time.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import snapshot_backend_log_offset, wait_e2e_provider_ready  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)
from tests.support.chrome_skill_hooks_composer import drive_chat_turn  # noqa: E402
from tests.support.chrome_skill_hooks_live_e2e import SkillChat  # noqa: E402
from tests.support.chrome_skill_hooks_observe import (  # noqa: E402
    transcript_text,
    wait_completed_assistant_reply_containing,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger  # noqa: E402

_MCP_SERVER_NAME = "microsoft-learn"
_PROBE_SKILL_ID = "content-distribution-pipeline"

_PROMPT = "请用 Microsoft Learn 搜索 Azure Functions 冷启动（cold start）的官方说明，给我一句话解释，并附上官方文档链接。"

_AGENT_BOUND_JS = """((agentId) => {
  const bound = window.__myrmChatStore?.getState?.()?.agentConfig?.agentId ?? null;
  return { ready: bound === agentId, bound };
})"""

# Polls the catalog card until Microsoft Learn shows Connected; clicks the
# dialog's Connect once and confirms a high-risk acknowledgement if raised.
_CONNECT_SETTLE_JS = """(() => {
  const titles = Array.from(document.querySelectorAll('h4'));
  const title = titles.find((el) => /Microsoft Learn/i.test(el.textContent || ''));
  const card = title ? title.closest('div') : null;
  const text = card ? (card.textContent || '') : '';
  const buttons = card ? Array.from(card.querySelectorAll('button')).map((el) => el.textContent || '') : [];
  const connected = /Connected|已连接/i.test(text) && !buttons.some((t) => /Connect|连接/i.test(t));
  if (connected) return { ready: true, connected: true };
  const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"]'));
  for (const dialog of dialogs) {
    if (/风险|risk/i.test(dialog.textContent || '')) {
      const ack = Array.from(dialog.querySelectorAll('button')).find(
        (el) => /仍然|继续|确认|Continue|Proceed|Accept/i.test(el.textContent || '') && !el.disabled
      );
      if (ack) { ack.click(); return { ready: false, ackClicked: true }; }
      continue;
    }
    if (!window.__catalogConnectClicked) {
      const btn = Array.from(dialog.querySelectorAll('button')).find(
        (el) => /Connect|连接/i.test(el.textContent || '') && !el.disabled
      );
      if (btn) { window.__catalogConnectClicked = true; btn.click(); return { ready: false, connectClicked: true }; }
    }
  }
  return { ready: false, connected: false };
})()"""


def _is_retryable_open_mcp_error(exc: RuntimeError) -> bool:
    message = str(exc)
    if "No McpPage found for the given page" in message:
        return True
    if "SHPOIB runtime rebind after reload failed" in message:
        return True
    if "pageId " in message and "not owned by this shim session" in message:
        return True
    if "Chrome MCP new_page failed: Error: Timed out after waiting 30000ms" in message:
        return True
    return False


def _connect_microsoft_learn_via_ui() -> None:
    """Connect the credential-free catalog entry; the card must end Connected."""
    warm_ui_route("/settings/integrationCatalog")
    last_open_error: RuntimeError | None = None
    for attempt in range(3):
        try:
            with open_settings_subroute("/settings/integrationCatalog", timeout_ms=90_000) as (client, page):
                open_dialog = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const titles = Array.from(document.querySelectorAll('h4'));
                      const title = titles.find((el) => /Microsoft Learn/i.test(el.textContent || ''));
                      if (!title) return { ready: false, reason: 'entry_missing' };
                      const card = title.closest('div');
                      if (!card) return { ready: false, reason: 'card_missing' };
                      const button = Array.from(card.querySelectorAll('button')).find((el) =>
                        /Connect|连接/i.test(el.textContent || '')
                      );
                      if (!button) return { ready: false, reason: 'card_connect_missing' };
                      button.click();
                      return { ready: true };
                    })()""",
                    timeout_sec=30.0,
                )
                assert isinstance(open_dialog, dict)
                assert open_dialog.get("ready") is True, f"failed to open dialog: {open_dialog}"

                settled = wait_for_state(client, page, _CONNECT_SETTLE_JS, timeout_sec=150.0)
                assert settled.get("connected") is True, f"card never reached Connected: {settled}"
            return
        except RuntimeError as exc:
            last_open_error = exc
            if not _is_retryable_open_mcp_error(exc) or attempt == 2:
                raise
            time.sleep(2.0)
    raise AssertionError(f"failed to open MCP page after retries: {last_open_error}")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_catalog_mcp_bound_agent_answers_with_live_tool_call(tmp_path: Path, e2e_resource_ledger: E2EResourceLedger) -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    _connect_microsoft_learn_via_ui()
    # The catalog gate persists the MCP config through the settings store;
    # give the namespace backend a moment to observe it before binding.
    time.sleep(3.0)

    suffix = uuid.uuid4().hex[:8]
    created = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": f"Catalog MCP Lane-C E2E {suffix}",
            "description": "Lane-C probe: agent answers through a catalog-connected remote MCP",
            "system_prompt": "You are a helpful personal assistant.",
            "skill_ids": [],
            "mcp_ids": [_MCP_SERVER_NAME],
            "enabled_builtin_tools": [],
        },
    )
    assert isinstance(created, dict), created
    created_data = created.get("data")
    agent_id = created_data.get("id") if isinstance(created_data, dict) else created.get("id")
    assert isinstance(agent_id, str) and agent_id, created
    e2e_resource_ledger.register("agent", agent_id)

    bound = http_json("GET", f"{api_url}/api/v1/user-agents/{agent_id}")
    bound_data = bound.get("data") if isinstance(bound, dict) else None
    bound_ids = bound_data.get("mcp_ids") if isinstance(bound_data, dict) else None
    assert isinstance(bound_ids, list) and _MCP_SERVER_NAME in bound_ids, bound

    chat_id = f"e2emcp{suffix}"
    created_chat = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "Catalog MCP Lane-C E2E",
            "agent_id": agent_id,
            "action_mode": "agent",
            "messages": [],
        },
    )
    assert isinstance(created_chat, dict) and created_chat.get("success") is True, created_chat
    e2e_resource_ledger.register("chat", chat_id)

    probe = SkillChat(
        skill_name=_PROBE_SKILL_ID,
        agent_id=agent_id,
        chat_id=chat_id,
        out=tmp_path,
        log_offset=snapshot_backend_log_offset(api_url),
    )
    chat_url = f"{ui_url.rstrip('/')}{probe.ui_path}"

    def agent_bound(client: ChromeMcpClient, page: McpPage) -> None:
        applied = wait_for_state(
            client,
            page,
            f"({_AGENT_BOUND_JS})({json.dumps(agent_id)})",
            timeout_sec=90.0,
            page_url=chat_url,
        )
        assert applied.get("ready") is True, applied

    drive_chat_turn(ui_url, probe, _PROMPT, invoke_skill=False, before_send=agent_bound)

    reply = wait_completed_assistant_reply_containing(chat_id, api_url, "learn.microsoft.com", timeout_sec=300.0)
    print(f"E2E_ASSISTANT_REPLY[{chat_id}]: {reply[:500]}", flush=True)

    transcript = transcript_text(chat_id, api_url)
    assert "learn.microsoft.com" in transcript, "transcript must carry the live MCP documentation link"
