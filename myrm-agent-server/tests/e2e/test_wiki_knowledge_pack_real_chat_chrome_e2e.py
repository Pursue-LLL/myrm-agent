"""Real Chrome E2E: a mounted knowledge base answers a real turn through the per-turn knowledge pack.

Full real-business-task loop with no mock on the critical path. A shared wiki vault is built through the harness
publish pipeline inside the private runtime's data directory, with a page named ``SKILL.md`` (a page name that
carries ``.md``) holding a random phrase. The knowledge base is mounted on one chat; a second chat of the same agent
stays unmounted. Both chats are asked, through the real page and the real model, for the phrase:

  unmounted chat -> the completed reply never contains the phrase (the model cannot know it)
  mounted chat   -> the completed reply contains it: the writer, the index, the selector and the turn pack agree on
                    the page's identity, so the snippet reached the model and nothing else could have carried it
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import wait_e2e_provider_ready  # noqa: E402
from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig  # noqa: E402
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure  # noqa: E402
from myrm_agent_harness.toolkits.wiki.pipeline.publication import (  # noqa: E402
    ArticlePublishOutcome,
    publish_concept_article,
)
from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer  # noqa: E402

from app.services.wiki.vault.resolver import sanitize_wiki_scope_id  # noqa: E402
from tests.support.bash_compressor_e2e import _backend_runtime_data_dir  # noqa: E402
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
from tests.support.chrome_skill_hooks_observe import completed_assistant_replies, stored_messages  # noqa: E402
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402

_PAGE_NAME = "SKILL.md"
_QUESTION = "What is the Orion handover phrase of the Meridian crew? Reply with the exact phrase."
_REPLY_WAIT_SEC = 240.0

_SEND_TURN_JS = """(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return {{ ok: false, err: 'no-sendChatMessage' }};
  bridge.setActionMode?.('agent');
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  const result = await bridge.sendChatMessage({prompt_json}, {{
    baselineUserCount: usersBefore,
    waitForStreamCompletion: false,
    preserveActionMode: true,
  }});
  return {{ ...result, usersBefore }};
}})()"""

_ATTACH_CHAT_PROBE = """(() => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  const store = window.__myrmChatStore?.getState?.();
  const attached =
    store?.chatId === {chat_id_json}
    && Boolean(store?.isMessagesLoaded)
    && !Boolean(store?.loadError)
    && !Boolean(store?.notFound);
  if (attached) return {{ ready: true, chatId: store?.chatId ?? null }};
  if (bridge?.attachToChat && !window.__MYRM_E2E_ATTACHING__) {{
    window.__MYRM_E2E_ATTACHING__ = true;
    bridge.attachToChat({chat_id_json}).catch(() => {{}}).finally(() => {{
      window.__MYRM_E2E_ATTACHING__ = false;
    }});
  }}
  return {{ ready: false, chatId: store?.chatId ?? null, err: !bridge ? 'no-bridge' : null }};
}})()"""


def _runtime_data_dir(api_url: str) -> Path:
    """The private backend's data directory: the vault is placed where that backend reads its shared vaults."""
    data_dir = _backend_runtime_data_dir(api_url)
    assert data_dir is not None, f"{api_url} is not an isolated runtime; refusing to write a vault into a shared stack"
    assert (data_dir / "data.db").is_file(), f"{data_dir} holds no backend database; it is not a runtime data dir"
    return data_dir


def _page(phrase: str) -> str:
    text = f"The Orion handover phrase of the Meridian crew is {phrase}. Quote it whenever the Orion handover phrase is asked."
    return f"---\ntype: concept\n---\n## Compiled Truth\n{text}\n"


def _publish_vault(vault_dir: Path, phrase: str) -> None:
    """Publish the target page and two unrelated ones the way the harness publishes every page."""
    pages = {
        _PAGE_NAME: _page(phrase),
        "Hotel Limits": "---\ntype: concept\n---\n## Compiled Truth\nHotel stays in Berlin are capped at 120 per night.\n",
        "Flight Rules": "---\ntype: concept\n---\n## Compiled Truth\nConference travel allows economy flights only.\n",
    }

    async def publish() -> None:
        structure = WikiStructure(vault_dir)
        structure.ensure_structure()
        indexer = WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))
        for name, page in pages.items():
            outcome = await publish_concept_article(structure, indexer, name, page)
            assert outcome is ArticlePublishOutcome.PUBLISHED, (name, outcome)

    asyncio.run(publish())


def _create_agent(api_url: str, suffix: str) -> str:
    response = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": f"Knowledge Pack Probe {suffix}",
            "description": "Knowledge pack e2e probe agent",
            "enabled_builtin_tools": ["memory"],
        },
    )
    assert isinstance(response, dict) and response.get("data", {}).get("id"), f"Create agent failed: {response}"
    return str(response["data"]["id"])


def _create_chat(api_url: str, chat_id: str, agent_id: str) -> None:
    response = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={"chat_id": chat_id, "title": "Knowledge Pack E2E", "agent_id": agent_id, "action_mode": "agent", "messages": []},
    )
    assert isinstance(response, dict) and response.get("success") is True, f"Create chat failed: {response}"


def _create_context(api_url: str, suffix: str) -> str:
    response = http_json(
        "POST",
        f"{api_url}/api/v1/memory/shared-contexts/",
        body={"name": f"Knowledge Pack Probe {suffix}", "description": "Knowledge pack e2e shared knowledge base"},
    )
    assert isinstance(response, dict) and response.get("id"), f"Create shared context failed: {response}"
    return str(response["id"])


def _send_turn(ui_url: str, chat_id: str, prompt: str) -> None:
    """Open the chat page in real Chrome, wait for attach, send one real turn."""
    chat_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=chat_url)
        bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
        assert bridge.get("ready") is True, json.dumps(bridge, ensure_ascii=False)
        attached = wait_for_state(
            client,
            page,
            _ATTACH_CHAT_PROBE.format(chat_id_json=json.dumps(chat_id)),
            timeout_sec=90.0,
            page_url=chat_url,
        )
        assert attached.get("ready") is True, json.dumps(attached, ensure_ascii=False)
        sent = client.evaluate(page, _SEND_TURN_JS.format(prompt_json=json.dumps(prompt)), timeout_sec=90.0)
        assert isinstance(sent, dict) and sent.get("ok") is True, (
            f"send turn failed for chat {chat_id}: {json.dumps(sent, ensure_ascii=False)[:600]}"
        )


def _turn_is_over(chat_id: str, api_url: str) -> bool:
    """The server holds no run and no approval card of the chat any more."""
    reply = http_json("GET", f"{api_url}/api/v1/agents/chat/{chat_id}/turn-state")
    state = reply.get("data") if isinstance(reply, dict) else None
    return isinstance(state, dict) and state.get("running") is False and state.get("awaitingApproval") is False


def _wait_final_reply(chat_id: str, api_url: str) -> str:
    """The words of the last non-empty assistant turn, once the run has ended.

    A run that calls tools first stores empty assistant steps before its answer, so the first completed assistant
    message is not the answer: waiting for the run to end is what makes an absence check mean something.
    """
    deadline = time.monotonic() + _REPLY_WAIT_SEC
    while time.monotonic() < deadline:
        replies = [reply for reply in completed_assistant_replies(stored_messages(chat_id, api_url)) if reply.strip()]
        if replies and _turn_is_over(chat_id, api_url):
            return replies[-1]
        time.sleep(2.0)
    pytest.fail(f"no final assistant reply for chat {chat_id} within {_REPLY_WAIT_SEC}s")


def _cleanup(api_url: str, chat_ids: tuple[str, ...], context_id: str | None, vault_dir: Path | None) -> None:
    gone = frozenset({200, 204, 404})
    for chat_id in chat_ids:
        http_json("DELETE", f"{api_url}/api/v1/chats/{chat_id}", expected_statuses=gone)
    if context_id is not None:
        http_json("DELETE", f"{api_url}/api/v1/memory/shared-contexts/{context_id}", expected_statuses=gone)
    if vault_dir is not None:
        shutil.rmtree(vault_dir, ignore_errors=True)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_mounted_knowledge_base_answers_through_the_turn_pack() -> None:
    """The phrase of a ``.md``-named page reaches the model only when its knowledge base is mounted."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    data_dir = _runtime_data_dir(api_url)

    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm-dev ready --chrome")

    suffix = uuid.uuid4().hex[:8]
    phrase = f"ORION-{uuid.uuid4().hex[:8].upper()}"
    unmounted_chat = f"e2ekpunmounted{suffix}"
    mounted_chat = f"e2ekpmounted{suffix}"
    context_id: str | None = None
    vault_dir: Path | None = None
    try:
        context_id = _create_context(api_url, suffix)
        vault_dir = data_dir / "harness" / "wiki" / "shared" / sanitize_wiki_scope_id(context_id)
        _publish_vault(vault_dir, phrase)

        agent_id = _create_agent(api_url, suffix)
        _create_chat(api_url, unmounted_chat, agent_id)
        _create_chat(api_url, mounted_chat, agent_id)
        http_json(
            "POST",
            f"{api_url}/api/v1/memory/shared-contexts/{context_id}/bindings",
            body={"target_type": "conversation", "target_id": mounted_chat},
        )

        _send_turn(ui_url, unmounted_chat, _QUESTION)
        unmounted_reply = _wait_final_reply(unmounted_chat, api_url)
        print(f"E2E_KP_UNMOUNTED_REPLY: {unmounted_reply[:300]}", flush=True)
        assert phrase not in unmounted_reply, f"the unmounted chat knew the phrase: {unmounted_reply[:300]}"

        _send_turn(ui_url, mounted_chat, _QUESTION)
        mounted_reply = _wait_final_reply(mounted_chat, api_url)
        print(f"E2E_KP_MOUNTED_REPLY: {mounted_reply[:300]}", flush=True)
        assert phrase in mounted_reply, f"the mounted chat's final reply lacks the phrase: {mounted_reply[:300]}"
    finally:
        _cleanup(api_url, (unmounted_chat, mounted_chat), context_id, vault_dir)
