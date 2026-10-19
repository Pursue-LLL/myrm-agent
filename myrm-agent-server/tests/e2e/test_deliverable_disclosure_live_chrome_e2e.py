"""Chrome E2E (LIVE lane): a real agent turn discloses the delivery evidence tier.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: Chrome MCP CDP test infrastructure)
- cdp_chat.support::fetch_chat_messages, wait_e2e_provider_ready (POS: live chat + provider readiness)
- tests.support.e2e_provider_seed::seed_live_e2e_providers (POS: live provider seeding)
- app/api/chats/test_fixtures/rich_media_preview (POS: workspace + chat seed route)

[OUTPUT]
- test_deliverable_disclosure_live_chrome_e2e: a real model turn writes a file into the
  workspace, the completion guard publishes the evidence tier, the server persists it as
  message metadata, and the WebUI renders the tier badge for that answer

[POS]
LIVE lane Chrome E2E for topic_03 #32 (execution-claim grounding + per-turn disclosure):
covers the real user flow of asking the agent for a file and seeing what the delivery is
backed by.
"""

from __future__ import annotations

import json
import os
import sys
import time
from urllib.parse import urlencode

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from cdp_chat.support import (  # noqa: E402
    fetch_chat_messages,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)
from tests.support.chrome_skill_hooks_approval import click_approve  # noqa: E402
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402
from tests.support.hitl_live_e2e import pin_and_verify_hitl_mode  # noqa: E402

_PROBE_FILENAME = "tier_probe.md"
_PROBE_PROMPT = "请在我的工作区创建一个文件，文件名为 tier_probe.md，内容为一行：# tier probe ok。请直接执行，不要询问确认。"

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_ATTACH_CHAT_JS_TEMPLATE = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {
    return { ok: false, err: 'no-bridge' };
  }
  await bridge.attachToChat(%s);
  const domDeadline = Date.now() + 30_000;
  while (Date.now() < domDeadline) {
    if (
      document.querySelector('[data-message-end]')
      || document.querySelector('[data-chat-input]')
    ) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  const snap = bridge.turnSnapshot?.() ?? {};
  return { ok: snap.chatId === %s, snap };
})()"""

_SEND_TURN_JS_TEMPLATE = """(async () => {
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return { ok: false, err: 'no-sendChatMessage' };
  bridge.setActionMode?.('agent');
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  const result = await bridge.sendChatMessage(%s, {
    baselineUserCount: usersBefore,
    waitForStreamCompletion: false,
    preserveActionMode: true,
  });
  return { ...result, usersBefore };
})()"""

_BADGE_READY_JS = """(() => {
  const badge = document.querySelector('[data-testid^="deliverable-tier-badge-"]');
  return {
    ready: Boolean(badge),
    testid: badge ? badge.getAttribute('data-testid') : null,
    text: badge ? (badge.textContent || '').trim() : '',
  };
})()"""

_TIER_READY_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = Array.isArray(store?.messages) ? store.messages : [];
  const assistant = [...msgs].reverse().find((m) => m?.role === 'assistant');
  return {
    ready: Boolean(assistant?.deliverableTier?.tier),
    tier: assistant?.deliverableTier?.tier ?? null,
    stagedCount: Array.isArray(assistant?.stagedArtifacts) ? assistant.stagedArtifacts.length : 0,
    loading: Boolean(store?.loading),
  };
})()"""


_PAGE_SAMPLE_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = Array.isArray(store?.messages) ? store.messages : [];
  const assistant = [...msgs].reverse().find((m) => m?.role === 'assistant');
  return {
    ready: true,
    loading: Boolean(store?.loading),
    assistantContent: assistant?.content ? String(assistant.content).slice(0, 400) : null,
    bodySample: (document.body?.innerText || '').slice(0, 400),
  };
})()"""


def _reply_excerpt(content: object) -> str:
    text = str(content or "").strip().replace("\n", " ")
    return text[:400]


_APPROVAL_VISIBLE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.toolApprovalSnapshot?.() ?? {};
  const queueLen = Number(snap.queueLen ?? 0);
  const buttons = Array.from(document.querySelectorAll('button'));
  const hasApprove = buttons.some((btn) => /Approve|批准/.test((btn.textContent || '').trim()));
  return { ready: hasApprove && queueLen > 0, queueLen, hasApprove };
})()"""

_APPROVAL_CLICK_BUDGET = 20


def _approve_cards_until_reply(
    client: object,
    page: object,
    chat_id: str,
    api_url: str,
    *,
    timeout_sec: float = 420.0,
) -> dict[str, object]:
    """Approve every tool-approval card the run parks behind, as the user would."""
    deadline = time.monotonic() + timeout_sec
    clicks = 0
    while time.monotonic() < deadline:
        try:
            messages = fetch_chat_messages(chat_id, api_url=api_url)
        except OSError:
            messages = []
        assistant = next(
            (m for m in reversed(messages) if isinstance(m, dict) and m.get("role") == "assistant"),
            None,
        )
        if isinstance(assistant, dict) and str(assistant.get("content") or "").strip():
            return assistant
        card = client.evaluate(page, _APPROVAL_VISIBLE_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
        if isinstance(card, dict) and card.get("ready") is True and clicks < _APPROVAL_CLICK_BUDGET:
            clicks += 1
            print(f"E2E_APPROVE_CLICK: n={clicks} chat={chat_id}", flush=True)
            click_approve(client, page)  # type: ignore[arg-type]
            time.sleep(1.0)
            continue
        time.sleep(4.0)
    pytest.fail(f"assistant reply not received within {timeout_sec}s for chat {chat_id} (approval clicks={clicks})")


def _entries_from_listing(listing: object) -> list[object]:
    if not isinstance(listing, dict):
        return []
    payload = listing.get("data")
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        return payload["entries"]
    if isinstance(listing.get("entries"), list):
        return listing["entries"]
    return []


def _workspace_file_present(api_url: str, workspace_dir: str, filename: str) -> bool:
    query = urlencode({"path": workspace_dir, "depth": "2"})
    try:
        listing = http_json("GET", f"{api_url}/api/v1/files/browse/files?{query}")
    except Exception:  # noqa: BLE001 - transient listing failures keep the wait loop alive
        return False
    entries = _entries_from_listing(listing)
    if not entries:
        return False

    def _walk(items: list[object]) -> bool:
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("name") == filename:
                return True
            children = item.get("children")
            if isinstance(children, list) and _walk(children):
                return True
        return False

    return _walk(entries)


def _wait_for_probe_file(api_url: str, workspace_dir: str, timeout_sec: float = 240.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last_listing: object = None
    query = urlencode({"path": workspace_dir, "depth": "2"})
    while time.monotonic() < deadline:
        if _workspace_file_present(api_url, workspace_dir, _PROBE_FILENAME):
            return
        try:
            last_listing = http_json("GET", f"{api_url}/api/v1/files/browse/files?{query}")
        except Exception as exc:  # noqa: BLE001 - surface the last failure in the final assert
            last_listing = str(exc)
        time.sleep(3.0)
    pytest.fail(
        f"agent did not write {_PROBE_FILENAME} within {timeout_sec}s; "
        f"last listing={json.dumps(last_listing, ensure_ascii=False)[:600]}"
    )


_DIAG_SAMPLE_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = Array.isArray(store?.messages) ? store.messages : [];
  const assistant = [...msgs].reverse().find((m) => m?.role === 'assistant');
  const badge = document.querySelector('[data-testid^="deliverable-tier-badge-"]');
  return {
    ready: true,
    storeTier: assistant?.deliverableTier?.tier ?? null,
    storeStaged: Array.isArray(assistant?.stagedArtifacts) ? assistant.stagedArtifacts.length : 0,
    badgeTestid: badge ? badge.getAttribute('data-testid') : null,
    loading: Boolean(store?.loading),
  };
})()"""


def _wait_assistant_disclosure(
    chat_id: str,
    api_url: str,
    *,
    timeout_sec: float = 240.0,
) -> dict[str, object]:
    """Poll the persisted messages until the assistant turn carries the disclosure tier."""
    deadline = time.monotonic() + timeout_sec
    last_metadata: object = None
    last_content = ""
    while time.monotonic() < deadline:
        try:
            messages = fetch_chat_messages(chat_id, api_url=api_url)
        except OSError:
            messages = []
        assistant = next(
            (m for m in reversed(messages) if isinstance(m, dict) and m.get("role") == "assistant"),
            None,
        )
        if isinstance(assistant, dict):
            last_content = str(assistant.get("content") or assistant.get("message") or "")
            metadata = assistant.get("metadata")
            last_metadata = metadata
            if isinstance(metadata, dict) and isinstance(metadata.get("deliverableTier"), dict):
                tier = metadata["deliverableTier"].get("tier")
                if isinstance(tier, str) and tier.strip():
                    return {"metadata": metadata, "content": last_content}
        time.sleep(3.0)
    keys = sorted(last_metadata.keys()) if isinstance(last_metadata, dict) else None
    pytest.fail(
        "assistant turn never carried deliverableTier within "
        f"{timeout_sec}s for chat {chat_id}; metadata_keys={keys} "
        f"metadata={json.dumps(last_metadata, ensure_ascii=False)[:400]} content={last_content[:200]}"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_deliverable_disclosure_live_chrome_e2e() -> None:
    """Real model task -> file write -> persisted evidence tier -> WebUI badge."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")
    pin_and_verify_hitl_mode(api_url)

    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-rich-media-preview-fixture",
    )
    assert isinstance(seeded, dict), seeded
    chat_id = str(seeded.get("chat_id") or "")
    workspace_dir = str(seeded.get("workspace_dir") or "")
    assert chat_id.startswith("e2ermd"), seeded
    assert workspace_dir, seeded

    target_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route("/")
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(target_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)  # type: ignore[attr-defined]

        bridge_ready = wait_for_react_e2e_bridge(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            timeout_sec=120.0,
            page_url=target_url,
        )
        assert bridge_ready.get("ready") is True, json.dumps(bridge_ready, ensure_ascii=False)

        chat_id_json = json.dumps(chat_id)
        attached = client.evaluate(  # type: ignore[attr-defined]
            page,
            _ATTACH_CHAT_JS_TEMPLATE % (chat_id_json, chat_id_json),
            timeout_sec=60.0,
        )
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        sent = client.evaluate(  # type: ignore[attr-defined]
            page,
            _SEND_TURN_JS_TEMPLATE % json.dumps(_PROBE_PROMPT),
            timeout_sec=60.0,
        )
        assert isinstance(sent, dict) and sent.get("ok") is not False, sent

        # 1. The live model answered the turn.
        reply = _approve_cards_until_reply(client, page, chat_id, api_url)

        # 2. The real turn actually writes the file through its tools.
        if not _workspace_file_present(api_url, workspace_dir, _PROBE_FILENAME):
            page_state = client.evaluate(page, _PAGE_SAMPLE_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
            pytest.fail(
                f"agent did not write {_PROBE_FILENAME}; reply={_reply_excerpt(reply.get('content'))!r} "
                f"page={json.dumps(page_state, ensure_ascii=False)[:700]}"
            )
        _wait_for_probe_file(api_url, workspace_dir, timeout_sec=120.0)

        # 3. The persisted assistant message carries the harness disclosure payload.
        try:
            disclosed = _wait_assistant_disclosure(chat_id, api_url)
        except BaseException:
            diag = client.evaluate(page, _DIAG_SAMPLE_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
            print(f"E2E_DISCLOSURE_DIAG: {json.dumps(diag, ensure_ascii=False)}", flush=True)
            raise
        tier = str(disclosed["metadata"]["deliverableTier"].get("tier"))  # type: ignore[index]
        assert tier in {"ARTIFACT", "VERIFIED"}, disclosed["metadata"]
        assert str(disclosed["content"]).strip(), "assistant answer was empty"

        # 4. The WebUI renders the tier badge for that answer.
        badge_state = wait_for_state(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            _BADGE_READY_JS,
            timeout_sec=90.0,
            page_url=target_url,
        )
        assert badge_state.get("ready") is True, json.dumps(badge_state, ensure_ascii=False)
        assert str(badge_state.get("testid", "")).startswith("deliverable-tier-badge-")

        # 5. The live store agrees with the persisted metadata.
        store_state = wait_for_state(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            _TIER_READY_JS,
            timeout_sec=60.0,
            page_url=target_url,
        )
        assert store_state.get("tier") == tier, json.dumps(store_state, ensure_ascii=False)
