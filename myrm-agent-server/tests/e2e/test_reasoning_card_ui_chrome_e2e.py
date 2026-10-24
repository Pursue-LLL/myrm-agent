"""Chrome E2E: the reasoning card renders a persisted chain with localized controls and 40px targets.

Seeds a real reasoning turn through the shared API (no mocks), then opens the WebUI chat and asserts:
1. the reasoning accordion is mounted from persisted ``reasoning_content``;
2. its icon buttons expose a >= 40px hit target (mobile/desktop safe);
3. the aria labels are localized (no hard-coded ``Expand``/``Collapse``);
4. the token label is rendered.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
)

_PROMPT = "请一步步推理：一个农夫有17只羊，除了9只以外都死了，还剩几只？请解释推理过程"

_READ_CARD_JS = """(async () => {
  const deadline = Date.now() + 45000;
  let acc = null;
  while (Date.now() < deadline) {
    acc = document.querySelector('[data-testid="reasoning-process-accordion"]');
    if (acc) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  if (!acc) {
    return { ok: false, reason: 'accordion-not-found', body: document.body.innerText.slice(0, 200) };
  }
  const buttons = Array.from(acc.querySelectorAll('button')).map((b) => {
    const rect = b.getBoundingClientRect();
    const aria = (b.getAttribute('aria-label') || '').trim();
    return {
      aria: aria.slice(0, 32),
      hasAria: aria.length > 0,
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    };
  });
  return { ok: true, text: acc.textContent.slice(0, 160), buttons };
})()"""


def _request(method: str, url: str, payload: dict[str, object] | None, timeout: float) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def _seed_reasoning_turn(api_url: str, chat_id: str) -> str:
    """Run one real turn until the model persists a reasoning chain; return the assistant messageId."""
    status, body = _request(
        "POST",
        f"{api_url}/api/v1/agents/agent-stream",
        {
            "messageId": f"e2e-reason-{int(time.time() * 1000)}",
            "query": _PROMPT,
            "action_mode": "agent",
            "chat_id": chat_id,
            "reasoning_display_mode": "collapsed",
        },
        timeout=240.0,
    )
    assert status == 200, body[:400]

    status, messages = _request("GET", f"{api_url}/api/v1/chats/{chat_id}/messages?page=1&page_size=20", None, 60.0)
    assert status == 200, messages[:400]
    payload = json.loads(messages)
    items = (payload.get("data") or {}).get("messages") or []
    assistants = [item for item in items if item.get("role") == "assistant"]
    assert assistants, payload
    metadata = assistants[-1].get("metadata") or {}
    reasoning = metadata.get("reasoning_content") or metadata.get("reasoning") or ""
    assert reasoning, f"this turn persisted no reasoning: {metadata}"
    return str(assistants[-1].get("messageId") or "")


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(420)
def test_reasoning_card_ui_chrome_e2e() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    chat_id = f"e2e-reasoning-card-{int(time.time())}"
    _seed_reasoning_turn(api_url, chat_id)

    try:
        # Open the chat route directly: a full reload after SHPOIB binding would re-apply the
        # private API runtime, and the orchestrator's route-open path already does that.
        with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)
            res = client.evaluate(page, _READ_CARD_JS, timeout_sec=90.0)

        assert isinstance(res, dict), res
        assert res.get("ok") is True, res

        buttons = res.get("buttons") or []
        labelled = [button for button in buttons if button.get("hasAria")]
        assert len(labelled) >= 2, res
        assert all(int(button["width"]) >= 40 and int(button["height"]) >= 40 for button in labelled), res
        assert not any(button["aria"] in {"Expand", "Collapse"} for button in labelled), res
        assert "tokens" in str(res.get("text", "")).lower(), res
    finally:
        _request("DELETE", f"{api_url}/api/v1/chats/{chat_id}", None, 30.0)
