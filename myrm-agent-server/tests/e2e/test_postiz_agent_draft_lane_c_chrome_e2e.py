"""Chrome LIVE Lane-C E2E: a real agent turn creates a Postiz draft via MCP.

This is the credential-gated positive chain for the Postiz catalog entry. It
skips cleanly unless ``POSTIZ_API_KEY`` is configured (``.env.test`` is loaded
into the environment by ``tests/conftest.py``). External preconditions that
only the account owner can satisfy:

1. A Postiz account (cloud or self-hosted) with an API key.
2. At least one social channel connected inside Postiz (Postiz refuses to
   schedule without a connected channel integration).

Chain under test: connect the catalog entry in the real Settings UI with the
real key (remote entries skip the localhost probe and pass the security
gate), bind the saved ``postiz`` MCP server to a fresh agent, then send a
plain chat turn asking for an X post draft. The turn must create the draft
in Postiz (draft-first, never publish) and answer with the Postiz preview
link. The PRIVATE namespace is ephemeral, so the saved MCP config, agent,
and chat are destroyed with the runtime at seal time.
"""

from __future__ import annotations

import json
import os
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

_SKILL_ID = "content-distribution-pipeline"
_MCP_SERVER_NAME = "postiz"

_PROMPT = (
    "请用 Postiz 把下面这条内容做成一篇适合发到 X 的帖子，先在 Postiz 里创建草稿，不要直接发布。"
    "创建成功后，把 Postiz 返回的草稿预览链接发给我：\n\n"
    "「Myrm 是一款开源的个人 AI 助手，数据始终由用户自己掌控。」"
)

_AGENT_BOUND_JS = """((agentId) => {
  const bound = window.__myrmChatStore?.getState?.()?.agentConfig?.agentId ?? null;
  return { ready: bound === agentId, bound };
})"""

# Polls the catalog card until Postiz shows Connected; clicks through a
# high-risk acknowledgement dialog if the security gate raises one.
_CONNECT_SETTLE_JS = """(() => {
  const titles = Array.from(document.querySelectorAll('h4'));
  const title = titles.find((el) => /Postiz/i.test(el.textContent || ''));
  const card = title ? title.closest('div') : null;
  const text = card ? (card.textContent || '') : '';
  const buttons = card ? Array.from(card.querySelectorAll('button')).map((el) => el.textContent || '') : [];
  const connected = /Connected|已连接/i.test(text) && !buttons.some((t) => /Connect|连接/i.test(t));
  if (connected) return { ready: true, connected: true };
  const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"]'));
  for (const dialog of dialogs) {
    if (!/风险|risk/i.test(dialog.textContent || '')) continue;
    const ack = Array.from(dialog.querySelectorAll('button')).find(
      (el) => /仍然|继续|确认|Continue|Proceed|Accept/i.test(el.textContent || '') && !el.disabled
    );
    if (ack) { ack.click(); return { ready: false, ackClicked: true }; }
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


def _connect_postiz_via_ui(api_key: str) -> None:
    """Connect the Postiz catalog entry with a real key; the card must end Connected."""
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
                      const title = titles.find((el) => /Postiz/i.test(el.textContent || ''));
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

                fill_key = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const dialog = document.querySelector('[role="dialog"]');
                      if (!dialog) return { ready: false, reason: 'dialog_missing' };
                      const input = dialog.querySelector('input');
                      if (!input) return { ready: false, reason: 'credential_input_missing' };
                      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                      setter.call(input, KEY_JSON);
                      input.dispatchEvent(new Event('input', { bubbles: true }));
                      input.dispatchEvent(new Event('change', { bubbles: true }));
                      return { ready: true };
                    })()""".replace("KEY_JSON", json.dumps(api_key)),
                    timeout_sec=30.0,
                )
                assert fill_key.get("ready") is True, f"failed to fill API key: {fill_key}"

                click_connect = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const dialog = document.querySelector('[role="dialog"]');
                      if (!dialog) return { ready: false };
                      const button = Array.from(dialog.querySelectorAll('button')).find((el) =>
                        /Connect|连接/i.test(el.textContent || '') && !el.disabled
                      );
                      if (!button) return { ready: false, reason: 'dialog_connect_missing' };
                      button.click();
                      return { ready: true };
                    })()""",
                    timeout_sec=30.0,
                )
                assert click_connect.get("ready") is True

                settled = wait_for_state(client, page, _CONNECT_SETTLE_JS, timeout_sec=150.0)
                assert settled.get("connected") is True, f"Postiz card never reached Connected: {settled}"
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
def test_postiz_agent_turn_creates_draft_with_preview_link(tmp_path: Path, e2e_resource_ledger: E2EResourceLedger) -> None:
    api_key = os.environ.get("POSTIZ_API_KEY", "").strip()
    if not api_key:
        pytest.skip(
            "POSTIZ_API_KEY not configured in .env.test; the Postiz positive Lane-C chain "
            "needs a real Postiz account, API key, and a connected social channel"
        )

    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    enabled = http_json("POST", f"{api_url}/api/v1/skills/{_SKILL_ID}/enable")
    assert isinstance(enabled, dict), enabled

    _connect_postiz_via_ui(api_key)
    # The catalog gate persists the MCP config through the settings store;
    # give the namespace backend a moment to observe it before binding.
    time.sleep(3.0)

    suffix = uuid.uuid4().hex[:8]
    created = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": f"Postiz Draft Lane-C E2E {suffix}",
            "description": "Lane-C probe: agent creates a Postiz draft through the catalog MCP",
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

    chat_id = f"e2epostiz{suffix}"
    created_chat = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "Postiz draft Lane-C E2E",
            "agent_id": agent_id,
            "action_mode": "agent",
            "messages": [],
        },
    )
    assert isinstance(created_chat, dict) and created_chat.get("success") is True, created_chat
    e2e_resource_ledger.register("chat", chat_id)

    probe = SkillChat(
        skill_name=_SKILL_ID,
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

    reply = wait_completed_assistant_reply_containing(chat_id, api_url, "postiz.com", timeout_sec=300.0)
    print(f"E2E_ASSISTANT_REPLY[{chat_id}]: {reply[:500]}", flush=True)

    transcript = transcript_text(chat_id, api_url)
    assert "postiz.com" in transcript, "transcript must carry the Postiz preview link"
