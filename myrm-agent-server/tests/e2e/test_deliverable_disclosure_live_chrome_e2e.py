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
  const store = window.__myrmChatStore?.getState?.();
  const msgs = Array.isArray(store?.messages) ? store.messages : [];
  const assistant = [...msgs].reverse().find((m) => m?.role === 'assistant');
  return {
    ready: Boolean(badge) && Boolean(assistant?.deliverableTier) && !store?.loading,
    testid: badge ? badge.getAttribute('data-testid') : null,
    text: badge ? (badge.textContent || '').trim() : '',
    storeMessageCount: msgs.length,
    assistantId: assistant?.messageId ?? null,
    storeTier: assistant?.deliverableTier?.tier ?? null,
    loading: Boolean(store?.loading),
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


def _approve_cards_until_tier(
    client: object,
    page: object,
    chat_id: str,
    api_url: str,
    *,
    timeout_sec: float = 420.0,
) -> dict[str, object]:
    """Approve every tool-approval card the run parks behind until its tier is stored.

    The persisted tier is the anchor that proves the turn finished (message_end
    carries it) and that the harness published the disclosure for this turn.
    """
    deadline = time.monotonic() + timeout_sec
    clicks = 0
    passes = 0
    last_metadata: object = None
    last_content = ""
    while time.monotonic() < deadline:
        passes += 1
        try:
            messages = fetch_chat_messages(chat_id, api_url=api_url)
        except OSError:
            messages = []
        assistants = [m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"]
        for candidate in reversed(assistants):
            metadata = candidate.get("metadata")
            last_metadata = metadata
            if isinstance(metadata, dict) and isinstance(metadata.get("deliverableTier"), dict):
                content = str(candidate.get("content") or candidate.get("message") or "")
                return {"metadata": metadata, "content": content}
        if assistants:
            last_content = str(assistants[-1].get("content") or assistants[-1].get("message") or "")
        # Probe the card every third pass: each CDP round trip competes with parallel E2E load.
        card = None
        if passes % 3 == 1:
            card = client.evaluate(page, _APPROVAL_VISIBLE_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
        if isinstance(card, dict) and card.get("ready") is True and clicks < _APPROVAL_CLICK_BUDGET:
            clicks += 1
            print(f"E2E_APPROVE_CLICK: n={clicks} chat={chat_id}", flush=True)
            try:
                click_approve(client, page)  # type: ignore[arg-type]
            except AssertionError:
                # The card was consumed between the probe and the click.
                pass
            time.sleep(1.0)
            continue
        time.sleep(3.0)
    keys = sorted(last_metadata.keys()) if isinstance(last_metadata, dict) else None
    pytest.fail(
        f"deliverableTier never landed within {timeout_sec}s for chat {chat_id} (approval clicks={clicks}); "
        f"metadata_keys={keys} content={last_content[:200]!r}"
    )


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

        # 1. Approve the cards the run parks behind until its disclosure tier is stored.
        disclosed = _approve_cards_until_tier(client, page, chat_id, api_url)

        # 2. The real turn actually wrote the file through its tools.
        if not _workspace_file_present(api_url, workspace_dir, _PROBE_FILENAME):
            page_state = client.evaluate(page, _PAGE_SAMPLE_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
            pytest.fail(
                f"agent did not write {_PROBE_FILENAME}; reply={_reply_excerpt(disclosed.get('content'))!r} "
                f"page={json.dumps(page_state, ensure_ascii=False)[:700]}"
            )

        # 3. The persisted assistant message carries the harness disclosure payload.
        api_messages = fetch_chat_messages(chat_id, api_url=api_url)
        api_assistant = next(
            (m for m in reversed(api_messages) if isinstance(m, dict) and m.get("role") == "assistant"),
            None,
        )
        print(
            "E2E_API_ASSISTANT: "
            + json.dumps(
                {
                    "chat_id": chat_id,
                    "assistant_id": (api_assistant or {}).get("messageId"),
                    "metadata_keys": sorted(((api_assistant or {}).get("metadata") or {}).keys()),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        tier = str(disclosed["metadata"]["deliverableTier"].get("tier"))  # type: ignore[index]
        assert tier in {"ARTIFACT", "VERIFIED"}, disclosed["metadata"]
        assert str(disclosed["content"]).strip(), "assistant answer was empty"

        # 4. The badge renders for the turn. The bridge-created local placeholder carries a
        #    client id, so check the persisted view a returning user sees (reload + attach).
        live = client.evaluate(page, _BADGE_READY_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
        if isinstance(live, dict) and live.get("ready") is not True:
            print(f"E2E_LIVE_BADGE_PENDING: {json.dumps(live, ensure_ascii=False)}", flush=True)
        client.navigate(page, target_url, timeout_ms=90_000)  # type: ignore[attr-defined]
        wait_for_react_e2e_bridge(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            timeout_sec=120.0,
            page_url=target_url,
        )
        reattached = client.evaluate(  # type: ignore[attr-defined]
            page,
            _ATTACH_CHAT_JS_TEMPLATE % (chat_id_json, chat_id_json),
            timeout_sec=60.0,
        )
        assert isinstance(reattached, dict) and reattached.get("ok") is True, reattached

        badge_state = wait_for_state(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            _BADGE_READY_JS,
            timeout_sec=120.0,
            page_url=target_url,
        )
        assert badge_state.get("ready") is True, json.dumps(badge_state, ensure_ascii=False)
        assert str(badge_state.get("testid", "")).startswith("deliverable-tier-badge-"), badge_state

        # 5. The live store agrees with the persisted metadata.
        store_state = wait_for_state(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            _TIER_READY_JS,
            timeout_sec=60.0,
            page_url=target_url,
        )
        assert store_state.get("tier") == tier, json.dumps(store_state, ensure_ascii=False)


_IDLE_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  return { ready: store?.loading !== true, loading: Boolean(store?.loading) };
})()"""


def _wait_turn_complete(
    client: object,
    page: object,
    chat_id: str,
    api_url: str,
    *,
    timeout_sec: float = 420.0,
) -> dict[str, object]:
    """Approve HITL cards until the turn stops streaming and its answer is stored."""
    deadline = time.monotonic() + timeout_sec
    clicks = 0
    passes = 0
    last_content = ""
    while time.monotonic() < deadline:
        passes += 1
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
            if last_content.strip():
                idle = client.evaluate(page, _IDLE_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
                if isinstance(idle, dict) and idle.get("ready") is True:
                    return assistant
        card = None
        if passes % 3 == 1:
            card = client.evaluate(page, _APPROVAL_VISIBLE_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
        if isinstance(card, dict) and card.get("ready") is True and clicks < _APPROVAL_CLICK_BUDGET:
            clicks += 1
            print(f"E2E_APPROVE_CLICK: n={clicks} chat={chat_id}", flush=True)
            try:
                click_approve(client, page)  # type: ignore[arg-type]
            except AssertionError:
                pass
            time.sleep(1.0)
            continue
        time.sleep(3.0)
    pytest.fail(f"turn did not finish within {timeout_sec}s for chat {chat_id} (clicks={clicks}) content={last_content[:200]!r}")


def _seed_chat(api_url: str) -> tuple[str, str]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-rich-media-preview-fixture",
    )
    assert isinstance(seeded, dict), seeded
    chat_id = str(seeded.get("chat_id") or "")
    workspace_dir = str(seeded.get("workspace_dir") or "")
    assert chat_id.startswith("e2ermd"), seeded
    assert workspace_dir, seeded
    return chat_id, workspace_dir


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_plain_chat_shows_no_tier_badge_live_chrome_e2e() -> None:
    """Small talk stays clean: no completion claim means no tier badge and no metadata."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")
    pin_and_verify_hitl_mode(api_url)

    chat_id, _workspace_dir = _seed_chat(api_url)
    target_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route("/")
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(target_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
        wait_for_react_e2e_bridge(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            timeout_sec=120.0,
            page_url=target_url,
        )
        chat_id_json = json.dumps(chat_id)
        attached = client.evaluate(  # type: ignore[attr-defined]
            page,
            _ATTACH_CHAT_JS_TEMPLATE % (chat_id_json, chat_id_json),
            timeout_sec=60.0,
        )
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        sent = client.evaluate(  # type: ignore[attr-defined]
            page,
            _SEND_TURN_JS_TEMPLATE % json.dumps("你好，请用一句话介绍一下你自己。"),
            timeout_sec=60.0,
        )
        assert isinstance(sent, dict) and sent.get("ok") is not False, sent

        reply = _wait_turn_complete(client, page, chat_id, api_url)
        assert str(reply.get("content") or "").strip(), "assistant answer was empty"
        metadata = reply.get("metadata")
        assert not (isinstance(metadata, dict) and metadata.get("deliverableTier")), metadata

        client.navigate(page, target_url, timeout_ms=90_000)  # type: ignore[attr-defined]
        wait_for_react_e2e_bridge(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            timeout_sec=120.0,
            page_url=target_url,
        )
        reattached = client.evaluate(  # type: ignore[attr-defined]
            page,
            _ATTACH_CHAT_JS_TEMPLATE % (chat_id_json, chat_id_json),
            timeout_sec=60.0,
        )
        assert isinstance(reattached, dict) and reattached.get("ok") is True, reattached

        store_state = client.evaluate(page, _TIER_READY_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
        assert isinstance(store_state, dict) and store_state.get("tier") is None, store_state
        badge_state = client.evaluate(page, _BADGE_READY_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
        assert isinstance(badge_state, dict) and badge_state.get("badgeTestid") is None, badge_state
