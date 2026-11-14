"""Chrome E2E: a changed reply-style preference replaces the stale one in every chat, new or already open.

Real business task flow, no mocks (real Chrome, real backend, real LLM, real vector store):

1. Chat A: the user asks for a signature line on every reply. The agent and the background
   extractor file proposals; the user accepts everything in the real review dialog.
2. Chat B (fresh, no shared context): a neutral question comes back signed the old way, so the
   stored memories demonstrably steer replies before the change.
3. Chat C: the user switches to a different signature. Whatever the agent and the extractor file
   for the change (a newer rule, a profile attribute, a fact) is accepted in the dialog.
4. Chat D (fresh): the same neutral question comes back signed the new way and not the old way.
5. Chats B (open before the change) and C (where the change was made) take one more turn each: both follow
   the new signature, and each is given a memory block different from the one its first turn had.

Runs once for a custom agent and once for the built-in general agent that the WebUI chats with by default.
What the agent stores lives in its own scope, which the memory page (it lists the default agent's) does not
show, so the stored state is judged by the memory block each reply was given and by what the replies do.

Declared PRIVATE because it writes to an exclusive, empty memory store.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable

import pytest
from cdp_chat.support import fetch_chat_messages, wait_e2e_provider_ready

from tests.e2e.test_memory_keyword_recall_live_chrome_e2e import (
    _create_agent,
    _create_chat,
    _open_chat_and_send,
    _wait_assistant_reply,
)
from tests.e2e.test_memory_pending_dialog_chrome_e2e import _attach, _open_chat_page, _press
from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers
from tests.support.retrieval_embedding import configured_retrieval_embedding

_MEMORY_API = "/api/v1/memory"
_OLD_SIGNATURE = "Quill"
_NEW_SIGNATURE = "Pip"
_SET_PROMPT = f"请记住我的回复偏好:以后你的每条回答最后一行都只写署名「—— {_OLD_SIGNATURE}」。"
_CHANGE_PROMPT = f"改一下我的回复偏好:不要再署名 {_OLD_SIGNATURE} 了,以后每条回答最后一行改成「—— {_NEW_SIGNATURE}」。"
_QUESTION = "多喝水对身体有什么好处?"
_ACCEPT = re.compile(r"^(Accept|接受)$")
_MAX_REVIEWS = 8
# The extractor files its proposals some seconds after the reply; the queue counts as drained once nothing arrived for this long.
_QUIET_SEC = 30.0
_EXTRACTION_WAIT_SEC = 90.0
# How long the pending badge may stay absent while the queue holds proposals before the page is reloaded.
_BADGE_WAIT_SEC = 20.0
# The general agent the WebUI chats with unless the user picks another one.
_BUILTIN_AGENT_ID = "builtin-general"
_OPEN_DIALOG_JS = """(() => {
  if (document.querySelector('[role="dialog"]')) return { ready: true };
  const badge = document.querySelector('[data-testid="pending-memory-badge"]');
  if (badge) badge.click();
  return { ready: false, badge: !!badge };
})()"""
_DIALOG_TEXT_JS = "(() => (document.querySelector('[role=\"dialog\"]')?.textContent || '').trim().slice(0, 500))()"


def _poll[T](read: Callable[[], T | None], *, timeout_sec: float, failure: Callable[[], str]) -> T:
    """Return the first non-None ``read()``; fail with ``failure()`` once the deadline passes."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        found = read()
        if found is not None:
            return found
        time.sleep(3.0)
    pytest.fail(failure())


def _items(api_url: str, path: str) -> list[dict[str, object]]:
    payload = http_json("GET", f"{api_url}{_MEMORY_API}{path}")
    assert isinstance(payload, dict) and isinstance(payload.get("items"), list), payload
    return [item for item in payload["items"] if isinstance(item, dict)]


def _rules(api_url: str) -> list[dict[str, object]]:
    return _items(api_url, "/?type=procedural&page_size=100")


def _visible_stored(api_url: str) -> list[dict[str, object]]:
    """The accepted rules and profile attributes the memory page lists: those of the default agent and the global scope."""
    return [*_rules(api_url), *_items(api_url, "/?type=profile&page_size=100")]


def _pending(api_url: str) -> list[dict[str, object]]:
    return _items(api_url, "/pending")


def _queued_ids(api_url: str) -> set[str]:
    return {str(item.get("id")) for item in _pending(api_url)}


def _snapshot(items: list[dict[str, object]]) -> str:
    """One line per item, for the run log."""
    return (
        " | ".join(f"{item.get('id')} [{item.get('memory_type')}]: {str(item.get('content'))[:160]}" for item in items)
        or "(none)"
    )


def _report(api_url: str, chat_id: str, reply: dict[str, object]) -> None:
    """Log how the turn that produced ``reply`` used memory: what was injected, which tools ran, what the ledger holds.

    The reply message carries the turn's memory budget and injection status (rules configured vs injected).
    """
    payload = http_json("GET", f"{api_url}/api/v1/statistics/session/{chat_id}/trace")
    trace = payload.get("data") if isinstance(payload, dict) else None
    assert isinstance(trace, dict), payload
    tools = [call.get("tool_name") for call in trace.get("tool_calls", []) if isinstance(call, dict)]
    ledger = " | ".join(
        f"{event.get('kind')}/{event.get('status')} {event.get('title')}: {str(event.get('summary'))[:100]}"
        for event in trace.get("memory_events", [])
        if isinstance(event, dict)
    )
    metadata = reply.get("metadata")
    memory = {key: value for key, value in metadata.items() if key.startswith("memory")} if isinstance(metadata, dict) else {}
    print(
        f"E2E_TURN[{chat_id}]: tools={tools} brief={_brief_id(reply)} "
        f"memory={json.dumps(memory, ensure_ascii=False, default=str)[:800]} "
        f"metadata_keys={sorted(metadata) if isinstance(metadata, dict) else metadata!r}",
        flush=True,
    )
    print(f"E2E_LEDGER[{chat_id}]: {ledger or '(none)'}", flush=True)


def _await_one_left(api_url: str, queued: set[str]) -> None:
    """Wait until at least one of the ``queued`` proposals left the queue (new arrivals do not count)."""
    _poll(
        lambda: True if queued - _queued_ids(api_url) else None,
        timeout_sec=60.0,
        failure=lambda: f"accepting in the dialog did not take a proposal off the queue: {_snapshot(_pending(api_url))}",
    )


def _open_review_dialog(client: ChromeMcpClient, page: McpPage, chat_url: str, chat_id: str) -> None:
    """Open the review dialog from the pending badge.

    The badge hears of proposals the extractor files after the page loaded only on the next load, so a page that
    shows nothing is reloaded once, as a user coming back to the chat would.
    """
    try:
        wait_for_state(client, page, _OPEN_DIALOG_JS, timeout_sec=_BADGE_WAIT_SEC)
    except AssertionError:
        reload_mcp_page(client, page, target_url=chat_url, timeout_ms=120_000)
        _attach(client, page, chat_url, chat_id)
        wait_for_state(client, page, _OPEN_DIALOG_JS, timeout_sec=90.0)


def _accept_everything(ui_url: str, api_url: str, chat_id: str) -> None:
    """Accept proposals in the chat window's review dialog, as a user would, until none arrives for a while."""
    chat_url, page_ctx = _open_chat_page(ui_url, chat_id)
    started = time.monotonic()
    with page_ctx as (client, page):
        _attach(client, page, chat_url, chat_id)
        reviews = 0
        quiet_since = time.monotonic()
        while time.monotonic() - quiet_since < _QUIET_SEC:
            queued = _queued_ids(api_url)
            if not queued:
                time.sleep(2.0)
                continue
            assert reviews < _MAX_REVIEWS, f"more than {_MAX_REVIEWS} proposals: {_snapshot(_pending(api_url))}"
            print(f"E2E_QUEUE: t={time.monotonic() - started:.0f}s size={len(queued)}", flush=True)
            _open_review_dialog(client, page, chat_url, chat_id)
            print(f"E2E_REVIEW_DIALOG: {client.evaluate(page, _DIALOG_TEXT_JS, timeout_sec=30.0)}", flush=True)
            _press(client, page, _ACCEPT)
            _await_one_left(api_url, queued)
            reviews += 1
            quiet_since = time.monotonic()
    assert not _pending(api_url), f"review queue still not empty: {_snapshot(_pending(api_url))}"


def _review_what_was_filed(ui_url: str, api_url: str, chat_id: str) -> None:
    """Give the background extractor time to file what it learned from the turn, then accept everything queued.

    The agent's own writes that need no approval never reach the queue, so an empty queue is no failure here: what
    the stored memories do to a fresh chat is what the replies are checked on.
    """
    deadline = time.monotonic() + _EXTRACTION_WAIT_SEC
    while time.monotonic() < deadline and not _queued_ids(api_url):
        time.sleep(3.0)
    print(f"E2E_PENDING[{chat_id}]: {_snapshot(_pending(api_url))}", flush=True)
    _accept_everything(ui_url, api_url, chat_id)
    print(f"E2E_VISIBLE_STORED[{chat_id}]: {_snapshot(_visible_stored(api_url))}", flush=True)


def _brief_id(reply: dict[str, object]) -> str | None:
    """Digest of the memory block the turn's prompt carried; equal digests mean equal blocks."""
    metadata = reply.get("metadata")
    brief_id = metadata.get("memoryBriefSnapshotId") if isinstance(metadata, dict) else None
    return brief_id if isinstance(brief_id, str) else None


def _reply_text(reply: dict[str, object]) -> str:
    return str(reply.get("content") or reply.get("message") or "")


def _ask(ui_url: str, api_url: str, chat_id: str, prompt: str) -> dict[str, object]:
    _open_chat_and_send(ui_url, chat_id, prompt)
    return _wait_assistant_reply(chat_id, api_url, timeout_sec=150.0)


def _answered(api_url: str, chat_id: str) -> list[dict[str, object]]:
    """The assistant replies of ``chat_id`` that carry text, oldest first."""
    messages = fetch_chat_messages(chat_id, api_url=api_url)
    return [m for m in messages if isinstance(m, dict) and m.get("role") == "assistant" and _reply_text(m).strip()]


def _ask_again(ui_url: str, api_url: str, chat_id: str, prompt: str) -> dict[str, object]:
    """Send one more turn in a chat that already holds replies and return the new reply, never an earlier one."""
    earlier = len(_answered(api_url, chat_id))
    _open_chat_and_send(ui_url, chat_id, prompt)
    return _poll(
        lambda: replies[-1] if len(replies := _answered(api_url, chat_id)) > earlier else None,
        timeout_sec=150.0,
        failure=lambda: f"chat {chat_id} got no new reply within 150s",
    )


def _signature_problems(label: str, reply: str, *, stale_anywhere: bool) -> list[str]:
    """What is wrong with a reply that has to carry the new signature on its last line and not the old one.

    A chat with earlier turns may quote the old signature in the body, so only a fresh chat is held to "nowhere".
    """
    stale = reply if stale_anywhere else _tail(reply)
    problems = []
    if _NEW_SIGNATURE.lower() not in _tail(reply).lower():
        problems.append(f"{label}: the new preference is missing from the reply: {reply[:300]}")
    if _OLD_SIGNATURE.lower() in stale.lower():
        problems.append(f"{label}: the stale preference is still in the reply: {reply[:300]}")
    return problems


def _tail(text: str) -> str:
    """The last two non-empty lines: where a signature line has to land."""
    return "\n".join([line for line in text.strip().splitlines() if line.strip()][-2:])


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.parametrize("agent_kind", ["custom_agent", "builtin_general_agent"])
def test_memory_rule_preference_change_live_new_preference_wins(agent_kind: str) -> None:
    """State a signature preference, change it, and a fresh chat follows only the new one."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    with configured_retrieval_embedding(api_url):
        prepare_e2e_ui_session(api_url)
        seed_live_e2e_providers(api_url)
        if not wait_e2e_provider_ready(timeout_sec=90.0):
            pytest.fail("Provider not ready — run ./myrm-dev ready --chrome")

        suffix = uuid.uuid4().hex[:8]
        agent_id = (
            _create_agent(api_url, f"Rule Preference Probe {suffix}") if agent_kind == "custom_agent" else _BUILTIN_AGENT_ID
        )
        chats = {name: f"e2erulepref{suffix}{name}" for name in ("a", "b", "c", "d")}
        for name, chat_id in chats.items():
            _create_chat(api_url, chat_id, f"Rule Preference E2E {name}", agent_id)

        # Chat A — state the preference; every proposal is accepted in the real dialog. Nothing is stored yet, so the
        # memory block of this turn is the empty one.
        reply_a = _ask(ui_url, api_url, chats["a"], _SET_PROMPT)
        _report(api_url, chats["a"], reply_a)
        _review_what_was_filed(ui_url, api_url, chats["a"])

        # Chat B — a context-free chat is steered by the stored memories alone.
        reply_b = _ask(ui_url, api_url, chats["b"], _QUESTION)
        _report(api_url, chats["b"], reply_b)

        # Chat C — change the preference; the stale rules must give way.
        reply_c = _ask(ui_url, api_url, chats["c"], _CHANGE_PROMPT)
        _report(api_url, chats["c"], reply_c)
        _review_what_was_filed(ui_url, api_url, chats["c"])

        # Chat D — a context-free chat follows the new preference and not the stale one.
        reply_d = _ask(ui_url, api_url, chats["d"], _QUESTION)
        _report(api_url, chats["d"], reply_d)

        # Chats B and C again — B was open before the change, C is where the change was made. Both keep chatting and
        # must follow the new preference, not the memory block their first turn was given.
        reply_b2 = _ask_again(ui_url, api_url, chats["b"], _QUESTION)
        _report(api_url, chats["b"], reply_b2)
        reply_c2 = _ask_again(ui_url, api_url, chats["c"], _QUESTION)
        _report(api_url, chats["c"], reply_c2)

        before, after = _reply_text(reply_b), _reply_text(reply_d)
        tails = {
            name: _tail(_reply_text(reply))
            for name, reply in {"b": reply_b, "d": reply_d, "b2": reply_b2, "c2": reply_c2}.items()
        }
        print(f"E2E_TAILS[{agent_kind}]: {tails!r}", flush=True)
        failures = []
        if _brief_id(reply_b) == _brief_id(reply_a):
            failures.append("chat B was given the same memory block as chat A before anything was stored: nothing reached it")
        if _OLD_SIGNATURE.lower() not in _tail(before).lower():
            failures.append(f"before the change the stored memories did not steer the reply: {before[:300]}")
        failures += _signature_problems("fresh chat D", after, stale_anywhere=True)
        for label, again, first in (("chat B", reply_b2, reply_b), ("chat C", reply_c2, reply_c)):
            if _brief_id(again) == _brief_id(first):
                failures.append(
                    f"{label} was given the same memory block on its next turn as on its first, though the stored rules changed"
                )
            failures += _signature_problems(f"{label}, next turn", _reply_text(again), stale_anywhere=False)
        assert not failures, "\n".join(failures)
