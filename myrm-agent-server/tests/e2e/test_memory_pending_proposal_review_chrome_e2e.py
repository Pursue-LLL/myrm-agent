"""Real Chrome MCP E2E: reviewing implicit-correction proposals in the Memory pending tab.

Real-user flow on /settings/memory (the Pending tab is the default):

1. The user already has a memory that is now outdated ("works at ByteDance") and one
   that is now wrong ("lives in Berlin").
2. Implicit-correction propagation queued two proposals against them: a CORRECT
   ("now works at Google") and a DELETE ("no longer lives in Berlin").
3. Each review card discloses which existing memory it corrects or removes.
4. Accepting the correction demotes the old memory and stores a linked correction;
   accepting the deletion removes the old memory. Both cards leave the queue.
5. When the targeted memory is edited after the proposal was queued, accepting the card is
   refused (HTTP 409): the user sees a neutral "out of date" notice, the proposal stays
   queued, and the edited memory is untouched.

Targets are created through the public memory API, so the embeddings come from the
real provider a user configures (the ``.env.test`` account). No LLM runs: proposals
are queued through ``MemoryManager.submit_pending``, the call implicit-correction
propagation makes after its detection and planning stages.

Declared PRIVATE because it asserts workspace backend behaviour (resolution-aware
approval dispatch) against an empty, exclusive memory store.
"""

from __future__ import annotations

import json
import re

import pytest

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

_MEMORY_API = "/api/v1/memory"
_CORRECT_TARGET = "E2E review seed - user works at ByteDance"
_CORRECT_PROPOSAL = "E2E review seed - user now works at Google"
_DELETE_TARGET = "E2E review seed - user lives in Berlin"
_DELETE_PROPOSAL = "E2E review seed - user no longer lives in Berlin"
_WILL_CORRECT = re.compile(r"Corrects an existing memory|将纠正已有记忆")
_STALE_NOTICE = re.compile(r"This suggestion is out of date|这条建议已过期")
_WILL_DELETE = re.compile(r"Moves an existing memory to the trash|将已有记忆移入回收站")

# The settings layout keeps previously visited tabs mounted (hidden), so a card can exist twice;
# only the rendered copy is what the user sees and clicks.
_FIND_CARD_JS = """const card = Array.from(document.querySelectorAll('[data-testid="memory-card"]')).find(
    (el) => el.getClientRects().length > 0 && (el.textContent || '').includes(%s),
  );"""


def _card_script(proposal: str, body: str) -> str:
    """JS expression evaluated against the pending card that shows ``proposal``."""
    return "(() => {\n  " + _FIND_CARD_JS % json.dumps(proposal) + "\n  " + body + "\n})()"


def _hint_probe_js(proposal: str) -> str:
    return _card_script(
        proposal,
        """const hint = card ? card.querySelector('[data-testid="pending-target-hint"]') : null;
  return { ready: !!hint, found: !!card, hint: hint ? hint.textContent.trim() : null };""",
    )


def _accept_js(proposal: str) -> str:
    return _card_script(
        proposal,
        """const accept = card
    ? Array.from(card.querySelectorAll('button')).find((el) => /^(Accept|接受)$/.test((el.textContent || '').trim()))
    : null;
  if (!accept) return { ready: false, clicked: false, found: !!card };
  accept.click();
  return { ready: true, clicked: true };""",
    )


def _card_gone_js(proposal: str) -> str:
    return _card_script(proposal, "return { ready: !card };")


# Records every memory API call the page makes so a failed review can be attributed to the
# HTTP layer (approval rejected) or to the UI (approval accepted, card not refreshed).
_NETWORK_TAP_JS = """(() => {
  if (window.__e2eMemoryTap) return true;
  window.__e2eMemoryTap = [];
  const original = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = String(typeof input === 'string' ? input : input.url || input);
    const entry = { url: url.split('/api/v1')[1] || url, method: (init && init.method) || 'GET' };
    if (entry.url.startsWith('/memory')) window.__e2eMemoryTap.push(entry);
    try {
      const response = await original(input, init);
      entry.status = response.status;
      return response;
    } catch (error) {
      entry.error = String(error);
      throw error;
    }
  };
  return true;
})()"""

_FORENSICS_JS = """(() => ({
  href: location.href,
  toasts: Array.from(document.querySelectorAll('[role="status"], [data-sonner-toast]'))
    .map((el) => (el.textContent || '').trim().slice(0, 200))
    .filter(Boolean),
  cards: Array.from(document.querySelectorAll('[data-testid="memory-card"]')).map((el) => ({
    text: (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 140),
    visible: el.getClientRects().length > 0,
  })),
  requests: window.__e2eMemoryTap || [],
}))()"""


def _create_semantic_memory(api_url: str, content: str) -> str:
    created = http_json(
        "POST",
        f"{api_url}{_MEMORY_API}/",
        body={"memory_type": "semantic", "content": content, "importance": 0.8},
    )
    assert isinstance(created, dict) and created.get("id"), created
    return str(created["id"])


def _queue_proposal(api_url: str, content: str, action: str, target_memory_id: str) -> str:
    queued = http_json(
        "POST",
        f"{api_url}{_MEMORY_API}/test/seed-pending-proposal",
        body={"content": content, "resolution_action": action, "target_memory_id": target_memory_id},
    )
    assert isinstance(queued, dict) and queued.get("pending_id"), queued
    return str(queued["pending_id"])


def _semantic_memories(api_url: str) -> dict[str, dict[str, object]]:
    listed = http_json("GET", f"{api_url}{_MEMORY_API}/?type=semantic&page_size=100")
    assert isinstance(listed, dict) and isinstance(listed.get("items"), list), listed
    return {str(item["id"]): item for item in listed["items"]}


def _trashed_ids(api_url: str) -> set[str]:
    trashed = http_json("GET", f"{api_url}{_MEMORY_API}/trash?type=semantic&page_size=100")
    assert isinstance(trashed, dict) and isinstance(trashed.get("items"), list), trashed
    return {str(item["id"]) for item in trashed["items"]}


def _pending_ids(api_url: str) -> set[str]:
    pending = http_json("GET", f"{api_url}{_MEMORY_API}/pending")
    assert isinstance(pending, dict) and isinstance(pending.get("items"), list), pending
    return {str(item["id"]) for item in pending["items"]}


def _review_and_accept(
    client: ChromeMcpClient,
    page: McpPage,
    api_url: str,
    proposal: str,
    pending_id: str,
    label: re.Pattern[str],
    target: str,
) -> None:
    """Assert the card names its target memory, accept it, and wait for it to leave the queue."""
    probe = wait_for_state(client, page, _hint_probe_js(proposal), timeout_sec=90.0)
    hint = str(probe.get("hint") or "")
    assert label.search(hint), probe
    assert target in hint, probe

    client.evaluate(page, _NETWORK_TAP_JS, timeout_sec=15.0)
    clicked = wait_for_state(client, page, _accept_js(proposal), timeout_sec=30.0)
    assert clicked.get("clicked") is True, clicked

    try:
        gone = wait_for_state(client, page, _card_gone_js(proposal), timeout_sec=45.0)
    except AssertionError as exc:
        snapshot = client.evaluate(page, _FORENSICS_JS, timeout_sec=15.0)
        still_pending = sorted(_pending_ids(api_url))
        contents = sorted(str(item["content"]) for item in _semantic_memories(api_url).values())
        raise AssertionError(
            f"{exc} | pending_id={pending_id} still_pending={still_pending} memories={contents} ui={snapshot}"
        ) from exc
    assert gone.get("ready") is True, gone


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_pending_proposal_review_chrome_e2e() -> None:
    """Accepting CORRECT and DELETE proposals in the WebUI rewrites the targeted memories."""
    api_url = get_e2e_api_url()

    with configured_retrieval_embedding(api_url):
        prepare_e2e_ui_session(api_url)
        correct_target_id = _create_semantic_memory(api_url, _CORRECT_TARGET)
        delete_target_id = _create_semantic_memory(api_url, _DELETE_TARGET)
        correct_pending_id = _queue_proposal(api_url, _CORRECT_PROPOSAL, "correct", correct_target_id)
        delete_pending_id = _queue_proposal(api_url, _DELETE_PROPOSAL, "delete", delete_target_id)
        assert {correct_pending_id, delete_pending_id} <= _pending_ids(api_url)

        warm_ui_route("/settings/memory")
        with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (client, page):
            ensure_desktop_viewport(client, page)
            dismiss_blocking_modals(client, page, recover_url=f"{get_e2e_ui_url().rstrip('/')}/settings")

            _review_and_accept(client, page, api_url, _CORRECT_PROPOSAL, correct_pending_id, _WILL_CORRECT, "ByteDance")
            _review_and_accept(client, page, api_url, _DELETE_PROPOSAL, delete_pending_id, _WILL_DELETE, "Berlin")

        memories = _semantic_memories(api_url)
        corrections = [item for item in memories.values() if item.get("correction_of") == correct_target_id]
        assert len(corrections) == 1, memories
        assert "Google" in str(corrections[0]["content"]), corrections
        assert delete_target_id not in memories, memories
        # Approving a forget proposal retires the memory to the trash (restorable), not a hard delete.
        assert delete_target_id in _trashed_ids(api_url)
        assert not {correct_pending_id, delete_pending_id} & _pending_ids(api_url)


_STALE_TARGET = "E2E stale seed - user works at ByteDance"
_STALE_PROPOSAL = "E2E stale seed - user now works at Google"
_STALE_EDIT = "E2E stale seed - user works at Meta"


def _stale_refusal_probe_js() -> str:
    """Ready once the UI shows the neutral notice and the approve call was answered with 409."""
    return f"""(() => {{
  const notice = new RegExp({json.dumps(_STALE_NOTICE.pattern)});
  const toast = Array.from(document.querySelectorAll('[role="status"], [data-sonner-toast]')).find((el) =>
    notice.test(el.textContent || ''),
  );
  const approvals = (window.__e2eMemoryTap || []).filter((entry) => /\\/approve$/.test(entry.url));
  const refused = approvals.some((entry) => entry.status === 409);
  return {{ ready: !!toast && refused, toast: !!toast, approvals }};
}})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_pending_stale_target_refused_chrome_e2e() -> None:
    """Accepting a proposal whose target was edited meanwhile is refused with a neutral notice."""
    api_url = get_e2e_api_url()

    with configured_retrieval_embedding(api_url):
        prepare_e2e_ui_session(api_url)
        target_id = _create_semantic_memory(api_url, _STALE_TARGET)
        pending_id = _queue_proposal(api_url, _STALE_PROPOSAL, "correct", target_id)
        http_json("PUT", f"{api_url}{_MEMORY_API}/semantic/{target_id}", body={"content": _STALE_EDIT})

        warm_ui_route("/settings/memory")
        with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (client, page):
            ensure_desktop_viewport(client, page)
            dismiss_blocking_modals(client, page, recover_url=f"{get_e2e_ui_url().rstrip('/')}/settings")

            wait_for_state(client, page, _hint_probe_js(_STALE_PROPOSAL), timeout_sec=90.0)
            client.evaluate(page, _NETWORK_TAP_JS, timeout_sec=15.0)
            clicked = wait_for_state(client, page, _accept_js(_STALE_PROPOSAL), timeout_sec=30.0)
            assert clicked.get("clicked") is True, clicked

            try:
                wait_for_state(client, page, _stale_refusal_probe_js(), timeout_sec=45.0)
            except AssertionError as exc:
                snapshot = client.evaluate(page, _FORENSICS_JS, timeout_sec=15.0)
                raise AssertionError(f"{exc} | pending_id={pending_id} ui={snapshot}") from exc

            # The refused proposal must still be reviewable: its card is still on screen.
            still_listed = client.evaluate(page, _card_script(_STALE_PROPOSAL, "return { ready: !!card };"), timeout_sec=15.0)
            assert still_listed.get("ready") is True, still_listed

        memories = _semantic_memories(api_url)
        assert str(memories[target_id]["content"]) == _STALE_EDIT, memories
        assert not [item for item in memories.values() if item.get("correction_of") == target_id], memories
        assert pending_id in _pending_ids(api_url)
