"""Real Chrome MCP E2E: batch review of memory suggestions in Settings → Memory.

Real-user flow on /settings/memory (the Pending tab is the default):

1. Three suggestions are waiting: two valid corrections and one whose target memory the user
   edited after the suggestion was queued.
2. The user ticks the three cards and presses "Accept All". The valid corrections are applied
   (each demotes its old memory and stores a linked correction); the out-of-date suggestion is
   reported as not approved, stays queued and leaves the edited memory untouched.
3. Later the user ticks two further deletion suggestions and presses "Reject All": both leave the
   queue and the memories they pointed at stay active.

Only the selected cards are acted on, so the test is independent of other suggestions that may
already sit in the runtime's queue. No LLM runs: proposals are queued through
``MemoryManager.submit_pending`` like implicit-correction propagation does, and targets are created
through the public memory API so embeddings come from the real configured provider.
"""

from __future__ import annotations

import json
import re
from uuid import uuid4

import pytest

from tests.e2e.test_memory_pending_proposal_review_chrome_e2e import (
    _MEMORY_API,
    _NETWORK_TAP_JS,
    _card_gone_js,
    _card_script,
    _create_semantic_memory,
    _hint_probe_js,
    _pending_ids,
    _queue_proposal,
    _semantic_memories,
    _trashed_ids,
)
from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)
from tests.support.retrieval_embedding import configured_retrieval_embedding

_RUN_TAG = uuid4().hex[:8]
_ACCEPT_ALL = re.compile(r"^(Accept All|批量接受)$")
_REJECT_ALL = re.compile(r"^(Reject All|批量拒绝)$")
_PARTIAL_NOTICE = re.compile(r"Approved 2\.|已批准 2 条")
_REJECT_NOTICE = re.compile(r"Successfully rejected 2 memories|已成功拒绝 2 条记忆")


def _select_card_js(proposal: str) -> str:
    """Tick the selection control of the card showing ``proposal`` (idempotent per call site)."""
    return _card_script(
        proposal,
        """const tick = card ? card.querySelector('button.rounded-full') : null;
  if (!tick) return { ready: false, found: !!card };
  tick.click();
  return { ready: true, clicked: true };""",
    )


def _click_toolbar_button_js(label: re.Pattern[str]) -> str:
    return f"""(() => {{
  const wanted = new RegExp({json.dumps(label.pattern)});
  const button = Array.from(document.querySelectorAll('button')).find(
    (el) => el.getClientRects().length > 0 && wanted.test((el.textContent || '').trim()),
  );
  if (!button) return {{ ready: false }};
  button.click();
  return {{ ready: true, clicked: true }};
}})()"""


def _toast_js(notice: re.Pattern[str]) -> str:
    return f"""(() => {{
  const wanted = new RegExp({json.dumps(notice.pattern)});
  const toast = Array.from(document.querySelectorAll('[role="status"], [data-sonner-toast]')).find((el) =>
    wanted.test(el.textContent || ''),
  );
  return {{ ready: !!toast, text: toast ? (toast.textContent || '').trim().slice(0, 200) : null }};
}})()"""


def _select_and_batch(
    client: ChromeMcpClient,
    page: McpPage,
    proposals: list[str],
    button: re.Pattern[str],
) -> None:
    for proposal in proposals:
        wait_for_state(client, page, _hint_probe_js(proposal), timeout_sec=90.0)
        ticked = wait_for_state(client, page, _select_card_js(proposal), timeout_sec=30.0)
        assert ticked.get("clicked") is True, ticked
    clicked = wait_for_state(client, page, _click_toolbar_button_js(button), timeout_sec=30.0)
    assert clicked.get("clicked") is True, clicked


# exclusive_backend reason: configured_retrieval_embedding mutates global /api/v1/config/retrieval and batch actions operate on the instance-wide /api/v1/memory/pending queue.
@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_pending_batch_accept_reports_stale_and_reject_all_chrome_e2e() -> None:
    """Accept All applies valid suggestions, keeps the stale one queued; Reject All leaves targets intact."""
    api_url = get_e2e_api_url()
    seed = f"E2E batch {_RUN_TAG}"
    targets = {
        "first": f"{seed} - user works at ByteDance",
        "second": f"{seed} - user drives a Toyota",
        "stale": f"{seed} - user studies physics",
        "keep_a": f"{seed} - user lives in Berlin",
        "keep_b": f"{seed} - user owns a bicycle",
    }
    proposals = {
        "first": f"{seed} - user now works at Google",
        "second": f"{seed} - user now drives a Honda",
        "stale": f"{seed} - user now studies chemistry",
        "keep_a": f"{seed} - user no longer lives in Berlin",
        "keep_b": f"{seed} - user no longer owns a bicycle",
    }
    stale_edit = f"{seed} - user studies mathematics"

    with configured_retrieval_embedding(api_url):
        prepare_e2e_ui_session(api_url)
        target_ids = {name: _create_semantic_memory(api_url, text) for name, text in targets.items()}
        pending_ids = {
            name: _queue_proposal(api_url, proposals[name], "delete" if name.startswith("keep") else "correct", target_ids[name])
            for name in targets
        }
        http_json("PUT", f"{api_url}{_MEMORY_API}/semantic/{target_ids['stale']}", body={"content": stale_edit})

        warm_ui_route("/settings/memory")
        with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (client, page):
            ensure_desktop_viewport(client, page)
            dismiss_blocking_modals(client, page, recover_url=f"{get_e2e_ui_url().rstrip('/')}/settings")
            client.evaluate(page, _NETWORK_TAP_JS, timeout_sec=15.0)

            _select_and_batch(client, page, [proposals["first"], proposals["second"], proposals["stale"]], _ACCEPT_ALL)
            partial = wait_for_state(client, page, _toast_js(_PARTIAL_NOTICE), timeout_sec=60.0)
            assert partial.get("ready") is True, partial
            for name in ("first", "second"):
                gone = wait_for_state(client, page, _card_gone_js(proposals[name]), timeout_sec=45.0)
                assert gone.get("ready") is True, gone
            stale_card = client.evaluate(page, _card_script(proposals["stale"], "return { ready: !!card };"), timeout_sec=15.0)
            assert stale_card.get("ready") is True, stale_card

            _select_and_batch(client, page, [proposals["keep_a"], proposals["keep_b"]], _REJECT_ALL)
            rejected = wait_for_state(client, page, _toast_js(_REJECT_NOTICE), timeout_sec=60.0)
            assert rejected.get("ready") is True, rejected
            for name in ("keep_a", "keep_b"):
                gone = wait_for_state(client, page, _card_gone_js(proposals[name]), timeout_sec=45.0)
                assert gone.get("ready") is True, gone

        memories = _semantic_memories(api_url)
        for name, correct_to in (("first", "Google"), ("second", "Honda")):
            corrections = [item for item in memories.values() if item.get("correction_of") == target_ids[name]]
            assert len(corrections) == 1, (name, memories)
            assert correct_to in str(corrections[0]["content"]), corrections
        assert str(memories[target_ids["stale"]]["content"]) == stale_edit, memories
        assert not [item for item in memories.values() if item.get("correction_of") == target_ids["stale"]], memories
        for name in ("keep_a", "keep_b"):
            assert str(memories[target_ids[name]]["content"]) == targets[name], memories
        assert not {target_ids["keep_a"], target_ids["keep_b"]} & _trashed_ids(api_url)

        still_pending = _pending_ids(api_url)
        assert pending_ids["stale"] in still_pending
        assert not {pending_ids[name] for name in ("first", "second", "keep_a", "keep_b")} & still_pending
