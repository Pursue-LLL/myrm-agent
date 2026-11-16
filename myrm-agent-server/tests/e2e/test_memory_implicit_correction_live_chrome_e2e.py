"""Chrome E2E: a spoken correction flows through the review queue and changes later answers.

Real business task flow, no mocks (real Chrome, real backend, real LLM, real vector store):

1. Chat A: the user states a distinctive fact ("I work at Zephyrion Labs"). Memory review is on
   by default, so the agent's own saves wait in the review queue; the user accepts them all.
2. Chat B: the user corrects it ("not there any more, now Quantara Systems"). The new fact is
   queued for review (HITL).
3. Review: the user accepts the queued proposal through the API the review dialog calls.
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
from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    prepare_e2e_ui_session,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers
from tests.support.retrieval_embedding import configured_retrieval_embedding

_MEMORY_API = "/api/v1/memory"
_OLD_EMPLOYER = "Zephyrion Labs"
_NEW_EMPLOYER = "Quantara Systems"
_WRITE_PROMPT = f"请记住:我目前在 {_OLD_EMPLOYER} 工作,职位是后端工程师。"
_CORRECTION_PROMPT = f"纠正一下:我已经不在 {_OLD_EMPLOYER} 了,现在改在 {_NEW_EMPLOYER} 工作。"
_RECALL_PROMPT = "我现在在哪家公司工作?只回答公司名。"
_PROPOSAL_WAIT_SEC = 180.0


def _pending_proposals(api_url: str) -> list[dict[str, object]]:
    pending = http_json("GET", f"{api_url}{_MEMORY_API}/pending")
    assert isinstance(pending, dict) and isinstance(pending.get("items"), list), pending
    return [item for item in pending["items"] if isinstance(item, dict)]


def _await_proposal(api_url: str, mentions: str) -> dict[str, object]:
    """Poll the review queue until a pending proposal mentions ``mentions``.

    The extraction that queues a proposal runs after the assistant reply, so an immediate read
    races it. The write path decides how a correction is routed: it may arrive as a targeted
    CORRECT/DELETE proposal or as a plain new-fact proposal. Either way the fact must wait for
    review.
    """
    deadline = time.monotonic() + _PROPOSAL_WAIT_SEC
    queued: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        queued = _pending_proposals(api_url)
        for proposal in queued:
            if mentions.lower() in str(proposal.get("content", "")).lower():
                return proposal
        time.sleep(3.0)
    pytest.fail(
        f"{mentions!r} never reached the review queue within {_PROPOSAL_WAIT_SEC}s; "
        f"pending={json.dumps(queued, ensure_ascii=False)[:600]}"
    )


def _approve(api_url: str, proposal: dict[str, object]) -> None:
    http_json("POST", f"{api_url}{_MEMORY_API}/pending/{proposal['id']}/approve", {})


def _approve_everything_queued(api_url: str) -> int:
    """Accept every proposal in the review queue, the way a user clears the review dialog."""
    queued = _pending_proposals(api_url)
    for proposal in queued:
        _approve(api_url, proposal)
    return len(queued)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_implicit_correction_live_approved_then_recalled() -> None:
    """Correct a stored fact in chat, approve the queued proposal, recall the new fact."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    with configured_retrieval_embedding(api_url):
        prepare_e2e_ui_session(api_url)
        seed_live_e2e_providers(api_url)
        if not wait_e2e_provider_ready(timeout_sec=90.0):
            pytest.fail("Provider not ready — run ./myrm-dev ready --chrome")

        suffix = uuid.uuid4().hex[:8]
        agent_id = _create_agent(api_url, f"Memory Correction Probe {suffix}")
        chats = {name: f"e2ecorrect{suffix}{name}" for name in ("a", "b", "c")}
        for name, chat_id in chats.items():
            _create_chat(api_url, chat_id, f"Memory Correction E2E {name}", agent_id)

        # Turn 1 — state the fact; the agent's save waits for review, and the user accepts it so the
        # correction in turn 2 changes a fact that is really stored.
        _open_chat_and_send(ui_url, chats["a"], _WRITE_PROMPT)
        _wait_assistant_reply(chats["a"], api_url, timeout_sec=120.0)
        _await_memory_write_ledger(api_url, chats["a"], timeout_sec=120.0)
        stated = _await_proposal(api_url, _OLD_EMPLOYER)
        print(f"E2E_STATED_FACT_ACCEPTED: proposals={_approve_everything_queued(api_url)}", flush=True)
        still_pending = _pending_proposals(api_url)
        assert all(item.get("id") != stated["id"] for item in still_pending), (
            f"the stated fact is still in the review queue after it was accepted; "
            f"pending={json.dumps(still_pending, ensure_ascii=False)[:600]}"
        )

        # Turn 2 — correct it in a fresh chat; the new fact must wait for the user's review.
        _open_chat_and_send(ui_url, chats["b"], _CORRECTION_PROMPT)
        _wait_assistant_reply(chats["b"], api_url, timeout_sec=120.0)
        proposal = _await_proposal(api_url, _NEW_EMPLOYER)
        proposal_text = str(proposal["content"])
        target_id = proposal.get("target_memory_id")
        print(
            f"E2E_CORRECTION_PROPOSAL: id={proposal['id']} action={proposal.get('resolution_action')} "
            f"target={target_id} content={proposal_text[:200]}",
            flush=True,
        )

        # Review — accept it like a real user. A targeted proposal also names what it supersedes.
        # The chat-side accept UI is covered end to end by the pending-dialog
        # node; here the live scenario accepts through the same API that UI calls
        # so extraction, correction routing and recall stay the focus.
        _approve(api_url, proposal)

        # Turn 3 — a context-free chat can only learn the employer from the approved memory.
        _open_chat_and_send(ui_url, chats["c"], _RECALL_PROMPT)
        reply = _wait_assistant_reply(chats["c"], api_url, timeout_sec=120.0)
        text = str(reply.get("content") or reply.get("message") or "")
        assert _NEW_EMPLOYER.split()[0].lower() in text.lower(), f"corrected employer missing from reply: {text[:400]}"
