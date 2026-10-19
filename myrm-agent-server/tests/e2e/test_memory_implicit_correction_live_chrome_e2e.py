"""Chrome E2E: a spoken correction flows through the review queue and changes later answers.

Real business task flow, no mocks (real Chrome, real backend, real LLM, real vector store):

1. Chat A: the user states a distinctive fact ("I work at Zephyrion Labs"); the memory
   system persists it.
2. Chat B: the user corrects it ("not there any more, now Quantara Systems"). The old
   memory is retired and the new fact is queued for review (HITL).
3. Memory settings: the user accepts the queued proposal through the real UI.
4. Chat C (fresh, no shared context): asked where the user works, the model must answer
   with the corrected employer — only the approved memory can supply it.

Declared PRIVATE because it writes to an exclusive, empty memory store.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest
from cdp_chat.support import wait_e2e_provider_ready  # noqa: E402  (path set by the recall module import)

from tests.e2e.test_memory_keyword_recall_live_chrome_e2e import (
    _await_memory_write_ledger,
    _create_agent,
    _create_chat,
    _open_chat_and_send,
    _wait_assistant_reply,
)
from tests.e2e.test_memory_pending_proposal_review_chrome_e2e import (
    _NETWORK_TAP_JS,
    _WILL_CORRECT,
    _WILL_DELETE,
    _accept_js,
    _card_gone_js,
    _card_script,
    _hint_probe_js,
)
from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers

_MEMORY_API = "/api/v1/memory"
_OLD_EMPLOYER = "Zephyrion Labs"
_NEW_EMPLOYER = "Quantara Systems"
_WRITE_PROMPT = f"请记住:我目前在 {_OLD_EMPLOYER} 工作,职位是后端工程师。"
_CORRECTION_PROMPT = f"纠正一下:我已经不在 {_OLD_EMPLOYER} 了,现在改在 {_NEW_EMPLOYER} 工作。"
_RECALL_PROMPT = "我现在在哪家公司工作?只回答公司名。"
_PROPOSAL_WAIT_SEC = 180.0


def _wait_with_reload(
    client: object,
    page: object,
    js: str,
    route_url: str,
    timeout_sec: float,
    *,
    attempts: int = 2,
) -> dict[str, object]:
    """wait_for_state, reloading the route once when the page stalled.

    The pending card depends on the memory store's fetch, which races page
    readiness under parallel load; a reload re-runs it instead of failing the
    run on a transient stall.
    """
    last: AssertionError | None = None
    for attempt in range(attempts):
        try:
            return wait_for_state(client, page, js, timeout_sec=timeout_sec)  # type: ignore[arg-type]
        except AssertionError as exc:  # wait_for_state raises on timeout
            last = exc
            if attempt + 1 >= attempts:
                break
            # The section itself is a next/dynamic chunk: a client-side
            # navigation can reuse the failed result from the router cache, so
            # retry with a full load at the subroute (fresh chunk requests) —
            # the deferred locale payload now has a real timeout, so the
            # namespaces arrive on that load too.
            reload_mcp_page(client, page, target_url=route_url, timeout_ms=120_000)  # type: ignore[arg-type]
            dismiss_blocking_modals(client, page, recover_url=route_url)  # type: ignore[arg-type]
    raise AssertionError(str(last))


def _semantic_memories(api_url: str) -> list[dict[str, object]]:
    listed = http_json("GET", f"{api_url}{_MEMORY_API}/?type=semantic&page_size=100")
    assert isinstance(listed, dict) and isinstance(listed.get("items"), list), listed
    return [item for item in listed["items"] if isinstance(item, dict)]


def _old_employer_memory_id(api_url: str) -> str:
    matches = [m for m in _semantic_memories(api_url) if _OLD_EMPLOYER.lower() in str(m.get("content", "")).lower()]
    assert matches, f"the stated fact was not persisted as a semantic memory: {_semantic_memories(api_url)}"
    return str(matches[0]["id"])


def _await_employer_proposal(api_url: str) -> dict[str, object]:
    """Poll the review queue until the corrected employer shows up as a pending proposal.

    The write path decides how the correction is routed: it may arrive as a targeted
    CORRECT/DELETE proposal or as a plain new-fact proposal while the old memory is
    already retired. Either way the user's new employer must wait for review.
    """
    deadline = time.monotonic() + _PROPOSAL_WAIT_SEC
    last: object = None
    while time.monotonic() < deadline:
        pending = http_json("GET", f"{api_url}{_MEMORY_API}/pending")
        assert isinstance(pending, dict) and isinstance(pending.get("items"), list), pending
        last = pending["items"]
        for item in pending["items"]:
            if isinstance(item, dict) and _NEW_EMPLOYER.lower() in str(item.get("content", "")).lower():
                return item
        time.sleep(3.0)
    pytest.fail(
        f"corrected employer never reached the review queue within {_PROPOSAL_WAIT_SEC}s; "
        f"pending={json.dumps(last, ensure_ascii=False)[:600]} memories={_semantic_memories(api_url)}"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_implicit_correction_live_approved_then_recalled() -> None:
    """Correct a stored fact in chat, approve the queued proposal in the UI, recall the new fact."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    suffix = uuid.uuid4().hex[:8]
    agent_id = _create_agent(api_url, f"Memory Correction Probe {suffix}")
    chats = {name: f"e2ecorrect{suffix}{name}" for name in ("a", "b", "c")}
    for name, chat_id in chats.items():
        _create_chat(api_url, chat_id, f"Memory Correction E2E {name}", agent_id)

    # Turn 1 — state the fact; wait for the extraction write before correcting it.
    _open_chat_and_send(ui_url, chats["a"], _WRITE_PROMPT)
    _wait_assistant_reply(chats["a"], api_url, timeout_sec=120.0)
    _await_memory_write_ledger(api_url, chats["a"], timeout_sec=120.0)
    _old_employer_memory_id(api_url)

    # Turn 2 — correct it in a fresh chat; the new fact must wait for the user's review.
    _open_chat_and_send(ui_url, chats["b"], _CORRECTION_PROMPT)
    _wait_assistant_reply(chats["b"], api_url, timeout_sec=120.0)
    proposal = _await_employer_proposal(api_url)
    proposal_text = str(proposal["content"])
    target_id = proposal.get("target_memory_id")
    print(
        f"E2E_CORRECTION_PROPOSAL: id={proposal['id']} action={proposal.get('resolution_action')} "
        f"target={target_id} content={proposal_text[:200]}",
        flush=True,
    )

    # Review — accept it like a real user. A targeted proposal also names what it supersedes.
    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page, recover_url=f"{ui_url.rstrip('/')}/settings")
        memory_route = f"{ui_url.rstrip('/')}/settings/memory"
        if target_id:
            probe = _wait_with_reload(client, page, _hint_probe_js(proposal_text), memory_route, 90.0)
            label = _WILL_CORRECT if proposal.get("resolution_action") == "correct" else _WILL_DELETE
            assert label.search(str(probe.get("hint") or "")), probe
        else:
            try:
                _wait_with_reload(
                    client,
                    page,
                    _card_script(proposal_text, "return { ready: !!card };"),
                    memory_route,
                    90.0,
                )
            except AssertionError as exc:
                # Distinguish "card rendered with different text" from "no cards
                # at all": dump the tab state, the card count and the page text.
                diag = client.evaluate(  # type: ignore[attr-defined]
                    page,
                    """(() => {
                      const cards = Array.from(document.querySelectorAll('[data-testid="memory-card"]'));
                      const tabs = Array.from(document.querySelectorAll('[role="tab"]')).map((el) => ({
                        text: (el.textContent || '').trim().slice(0, 16),
                        state: el.getAttribute('data-state'),
                      }));
                      const text = (document.body?.innerText || '').replace(/\\s+/g, ' ');
                      return {
                        cardCount: cards.length,
                        visibleCards: cards.filter((el) => el.getClientRects().length > 0).length,
                        cardTexts: cards.slice(0, 4).map((el) => (el.textContent || '').trim().slice(0, 120)),
                        tabs,
                        pageText: text.slice(0, 700),
                      };
                    })()""",
                )
                raise AssertionError(f"{exc} | diag: {diag}") from exc
        client.evaluate(page, _NETWORK_TAP_JS, timeout_sec=15.0)
        clicked = wait_for_state(client, page, _accept_js(proposal_text), timeout_sec=30.0)
        assert clicked.get("clicked") is True, clicked
        gone = wait_for_state(client, page, _card_gone_js(proposal_text), timeout_sec=60.0)
        assert gone.get("ready") is True, gone

    # Turn 3 — a context-free chat can only learn the employer from the approved memory.
    _open_chat_and_send(ui_url, chats["c"], _RECALL_PROMPT)
    reply = _wait_assistant_reply(chats["c"], api_url, timeout_sec=120.0)
    text = str(reply.get("content") or reply.get("message") or "")
    assert _NEW_EMPLOYER.split()[0].lower() in text.lower(), f"corrected employer missing from reply: {text[:400]}"
