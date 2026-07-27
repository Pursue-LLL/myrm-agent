"""Chrome READ E2E: same message_id retry surfaces AgentBusy without duplicating user rows."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)


def _seed_stream_retry_busy_fixture(api_url: str) -> dict[str, str]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-stream-retry-busy-fixture")
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    message_id = str(seeded.get("message_id") or "")
    query = str(seeded.get("query") or "")
    assert chat_id.startswith("e2estreamretry")
    assert message_id.startswith("msg_")
    assert query
    return {"chat_id": chat_id, "message_id": message_id, "query": query}


def _release_busy_fixture(api_url: str, chat_id: str) -> None:
    http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/release-stream-retry-busy-fixture?chat_id={chat_id}",
    )


def _post_agent_stream_snippet(
    api_url: str,
    *,
    chat_id: str,
    message_id: str,
    query: str,
) -> str:
    payload = json.dumps(
        {
            "message_id": message_id,
            "query": query,
            "chat_id": chat_id,
            "action_mode": "agent",
            "timezone": "UTC",
            "enable_memory": False,
        }
    ).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310
        f"{api_url.rstrip('/')}/api/v1/agents/agent-stream",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.read(8192).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read(8192).decode("utf-8", errors="replace")
        return f"HTTP {exc.code}: {body}"


def _user_count_probe(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(() => {{
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {{}};
  return {{
    ready: snap.chatId === {chat_id_json},
    userCount: snap.userCount ?? 0,
  }};
}})()"""


def _attach_chat_probe(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {{
    return {{ ok: false, err: 'no-bridge' }};
  }}
  await bridge.attachToChat({chat_id_json});
  const snap = bridge.turnSnapshot?.() ?? {{}};
  return {{
    ok: snap.chatId === {chat_id_json} && snap.userCount >= 1 && snap.isStreaming !== true,
    snap,
  }};
}})()"""


_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_stream_retry_same_message_id_is_busy_without_duplicate_user_row() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_stream_retry_busy_fixture(api_url)
    chat_id = seeded["chat_id"]
    message_id = seeded["message_id"]
    query = seeded["query"]

    warm_ui_route(f"/{chat_id}")

    try:
        with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            attached = client.evaluate(
                page,
                _attach_chat_probe(chat_id),
                timeout_sec=90.0,
            )
            assert isinstance(attached, dict) and attached.get("ok") is True, attached
            snap = attached.get("snap") if isinstance(attached.get("snap"), dict) else {}
            baseline_users = snap.get("userCount")
            assert isinstance(baseline_users, int) and baseline_users >= 1

            busy_snippet = _post_agent_stream_snippet(
                api_url,
                chat_id=chat_id,
                message_id=message_id,
                query=query,
            )
            assert "AgentBusyError" in busy_snippet, busy_snippet[:500]

            after = wait_for_state(
                client,
                page,
                _user_count_probe(chat_id),
                timeout_sec=30.0,
            )
            assert after.get("userCount") == baseline_users, after
    finally:
        _release_busy_fixture(api_url, chat_id)
