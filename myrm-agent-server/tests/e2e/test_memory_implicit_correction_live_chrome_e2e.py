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
import re
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
from tests.e2e.test_memory_pending_dialog_chrome_e2e import (
    _dialog_button_js,
    _dialog_left_proposal_js,
    _open_review_dialog,
)
from tests.e2e.test_memory_pending_proposal_review_chrome_e2e import (
    _NETWORK_TAP_JS,
)
from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers
from tests.support.retrieval_embedding import configured_retrieval_embedding

_ACCEPT_LABEL = re.compile(r"^(Accept|接受)$")
_MEMORY_API = "/api/v1/memory"
_OLD_EMPLOYER = "Zephyrion Labs"
_NEW_EMPLOYER = "Quantara Systems"
_WRITE_PROMPT = f"请记住:我目前在 {_OLD_EMPLOYER} 工作,职位是后端工程师。"
_CORRECTION_PROMPT = f"纠正一下:我已经不在 {_OLD_EMPLOYER} 了,现在改在 {_NEW_EMPLOYER} 工作。"
_RECALL_PROMPT = "我现在在哪家公司工作?只回答公司名。"
_PROPOSAL_WAIT_SEC = 180.0


def _semantic_memories(api_url: str) -> list[dict[str, object]]:
    listed = http_json("GET", f"{api_url}{_MEMORY_API}/?type=semantic&page_size=100")
    assert isinstance(listed, dict) and isinstance(listed.get("items"), list), listed
    return [item for item in listed["items"] if isinstance(item, dict)]


def _old_employer_memory_id(api_url: str, *, timeout_sec: float = 120.0) -> str:
    """Wait for the background extraction to persist the stated employer fact.

    The assistant reply lands first; the memory extraction that stores the fact
    is asynchronous, so an immediate read races it (observed: an empty list).
    """
    deadline = time.monotonic() + timeout_sec
    last: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        last = _semantic_memories(api_url)
        matches = [m for m in last if _OLD_EMPLOYER.lower() in str(m.get("content", "")).lower()]
        if matches:
            return str(matches[0]["id"])
        time.sleep(2.0)
    raise AssertionError(f"the stated fact was not persisted as a semantic memory: {last}")


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

    with configured_retrieval_embedding(api_url):

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
        # Review the proposal in the chat that raised it. The settings pane mounts
        # its section through next/dynamic and intermittently stays blank in the
        # dev lane, while the chat-side pending dialog is the primary user path.
        chat_url = f"{ui_url.rstrip('/')}/{chats['b']}"
        warm_ui_route(f"/{chats['b']}")
        with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
            ensure_desktop_viewport(client, page)
            dismiss_blocking_modals(client, page, recover_url=chat_url)
            wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
            _open_review_dialog(client, page, proposal_text, chat_url=chat_url)
            client.evaluate(page, _NETWORK_TAP_JS, timeout_sec=15.0)
            accepted = client.evaluate(page, _dialog_button_js(_ACCEPT_LABEL))
            assert accepted.get("ready") is True, accepted
            gone = wait_for_state(client, page, _dialog_left_proposal_js(proposal_text), timeout_sec=60.0)
            assert gone.get("ready") is True, gone

        # Turn 3 — a context-free chat can only learn the employer from the approved memory.
        _open_chat_and_send(ui_url, chats["c"], _RECALL_PROMPT)
        reply = _wait_assistant_reply(chats["c"], api_url, timeout_sec=120.0)
        text = str(reply.get("content") or reply.get("message") or "")
        assert _NEW_EMPLOYER.split()[0].lower() in text.lower(), f"corrected employer missing from reply: {text[:400]}"
