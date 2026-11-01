"""Building blocks of the knowledge-pack Chrome E2E: vaults placed in a private runtime, the picker, one real turn.

[INPUT]
- tests.support.bash_compressor_e2e::_backend_runtime_data_dir (POS: data dir of an isolated runtime; None for a shared stack)
- tests.support.chrome_mcp_e2e (POS: real Chrome page and loopback API helpers)
- tests.support.chrome_skill_hooks_observe (POS: the stored chat and the replies the server marked complete)
- tests.support.e2e_provider_seed::seed_live_e2e_providers (POS: the live model of the private runtime)
- myrm_agent_harness.toolkits.wiki (POS: the pipeline that writes pages and their index rows)

[OUTPUT]
- start_live_session: The private runtime's API and UI base, with its live provider seeded and ready.
- KnowledgeBase / create_knowledge_base: A shared context (what the picker lists) and the vault directory its pages live in.
- build_indexed_vault / build_plain_vault: A vault the harness wrote (pages and index rows), or a folder of plain notes.
- agent_vault_dir / index_state / downgrade_index_to_legacy: An agent's vault, what its index holds, and an index left as
  an older version wrote it.
- create_agent / create_chat / discard: The probe agent, its chats and the removal of what a test created.
- send_turn: Open the chat in real Chrome, mount knowledge bases through the picker, send one real turn; an incognito
  chat mounts them for the turn only, as the picker never stores a binding for it.
- completed_reply_count / wait_final_reply: The words of a run's final answer, read once the run has ended.
- assert_stayed_out_of_the_thread: A phrase is in the model's answers only, in no user message and no tool result.

[POS]
Shared by tests/e2e/test_wiki_knowledge_pack_real_chat_chrome_e2e.py and test_wiki_index_migration_chrome_e2e.py. Nothing but the vault files goes around the
product: the knowledge base is mounted the way a user mounts it, with the composer's picker, and the question goes
through the page's own send.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import sys
import time
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
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
    ChromeMcpClient,
    McpPage,
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

_OPEN_PICKER_JS = """(() => {
  const toggle = document.querySelector('[data-testid="knowledge-picker-toggle"]');
  if (!toggle) return { ok: false, err: 'no-picker-toggle' };
  toggle.click();
  return { ok: true };
})()"""

# The picker's switch is labelled with the knowledge base's name; a click that lands before the list has loaded is lost.
_CLICK_SWITCH_JS = """(() => {{
  const row = document.querySelector('[role="dialog"] [role="switch"][aria-label={name_json}]');
  if (!row) return {{ ready: false }};
  if (row.getAttribute('aria-checked') !== 'true') row.click();
  return {{ ready: true }};
}})()"""

# A stored incognito chat sets the page's incognito mode when it loads.
_INCOGNITO_PROBE_JS = """(() => ({ ready: window.__myrmChatStore?.getState?.().incognitoMode === true }))()"""

_MOUNTED_CHIP_JS = """(() => {{
  const strip = document.querySelector('[data-testid="composer-context-chip-strip"]');
  const chip = Array.from(strip?.querySelectorAll('[data-context-chip-id]') ?? []).find(
    (el) => el.getAttribute('data-context-chip-id')?.startsWith('knowledge-') && el.textContent?.includes({name_json}),
  );
  return {{ ready: Boolean(chip), chipText: chip?.textContent ?? null }};
}})()"""


@dataclass(frozen=True)
class KnowledgeBase:
    """A shared context, which is what the composer's picker lists, and the vault its pages are read from."""

    context_id: str
    name: str
    vault_dir: Path


def start_live_session() -> tuple[str, str]:
    """The private runtime's API and UI base, with its live provider seeded and ready."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm-dev ready --chrome")
    return api_url, get_e2e_ui_url()


def _wiki_root(api_url: str) -> Path:
    """The wiki root of the private runtime; a shared stack is refused, as a vault is written straight into the disk."""
    data_dir = _backend_runtime_data_dir(api_url)
    assert data_dir is not None, f"{api_url} is not an isolated runtime; refusing to write a vault into a shared stack"
    assert (data_dir / "data.db").is_file(), f"{data_dir} holds no backend database; it is not a runtime data dir"
    return data_dir / "harness" / "wiki"


def agent_vault_dir(api_url: str, agent_id: str) -> Path:
    """The writable vault the private backend opens for an agent."""
    return _wiki_root(api_url) / "agents" / sanitize_wiki_scope_id(agent_id)


def create_knowledge_base(api_url: str, label: str) -> KnowledgeBase:
    """Create the shared context and name the vault directory the private backend reads for it."""
    wiki_root = _wiki_root(api_url)
    name = f"Knowledge Pack Probe {label}"
    response = http_json(
        "POST",
        f"{api_url}/api/v1/memory/shared-contexts/",
        body={"name": name, "description": "Knowledge pack e2e shared knowledge base"},
    )
    assert isinstance(response, dict) and response.get("id"), f"Create shared context failed: {response}"
    context_id = str(response["id"])
    return KnowledgeBase(context_id, name, wiki_root / "shared" / sanitize_wiki_scope_id(context_id))


def _page(text: str, status: str | None = None) -> str:
    status_line = f"publish_status: {status}\n" if status else ""
    return f"---\ntype: concept\n{status_line}---\n## Compiled Truth\n{text}\n"


def build_indexed_vault(vault_dir: Path, published: Mapping[str, str], drafts: Mapping[str, str] | None = None) -> None:
    """Write a vault the way the harness does: published pages through the publish pipeline, drafts as drafts.

    Every page lands where ``get_concept_file_path`` puts it and in the index under the key the pipeline gives it.
    """

    async def build() -> None:
        structure = WikiStructure(vault_dir)
        structure.ensure_structure()
        indexer = WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))
        for name, text in published.items():
            outcome = await publish_concept_article(structure, indexer, name, _page(text))
            assert outcome is ArticlePublishOutcome.PUBLISHED, (name, outcome)
        for name, text in (drafts or {}).items():
            draft = _page(text, status="draft")
            structure.get_concept_file_path(name).write_text(draft, encoding="utf-8")
            await indexer.upsert(name, draft)

    asyncio.run(build())


def build_plain_vault(vault_dir: Path, notes: Mapping[str, str], *, unreadable_index: bool = False) -> None:
    """A folder of plain markdown notes, the vault of a team that mounts its notes as they are.

    With ``unreadable_index`` the folder also holds an index file no SQLite can open.
    """
    vault_dir.mkdir(parents=True, exist_ok=True)
    for name, text in notes.items():
        (vault_dir / f"{name}.md").write_text(f"# {name}\n\n{text}\n", encoding="utf-8")
    if unreadable_index:
        (vault_dir / ".wiki_index.db").write_bytes(b"this is not a sqlite database " * 8)


def index_state(vault_dir: Path) -> tuple[frozenset[str], int]:
    """The concept names the vault's index holds and its ``PRAGMA user_version``."""
    with closing(sqlite3.connect(vault_dir / ".wiki_index.db")) as conn:
        names = frozenset(str(row[0]) for row in conn.execute("SELECT concept_name FROM wiki_index_meta"))
        return names, int(conn.execute("PRAGMA user_version").fetchone()[0])


def downgrade_index_to_legacy(vault_dir: Path, legacy_names: Mapping[str, str]) -> None:
    """Leave the index as one written before the current page identity rule: legacy names as keys, an old version."""
    with closing(sqlite3.connect(vault_dir / ".wiki_index.db")) as conn:
        for key, legacy in legacy_names.items():
            for table in ("wiki_fts", "wiki_index_meta"):
                conn.execute(f"UPDATE {table} SET concept_name = ? WHERE concept_name = ?", (legacy, key))
        conn.execute("PRAGMA user_version = 3")
        conn.commit()


def create_agent(api_url: str, label: str) -> str:
    """An agent that enables the memory tool only; ``assert_stayed_out_of_the_thread`` shows what a tool never read."""
    response = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": f"Knowledge Pack Probe {label}",
            "description": "Knowledge pack e2e probe agent",
            "enabled_builtin_tools": ["memory"],
        },
    )
    assert isinstance(response, dict) and response.get("data", {}).get("id"), f"Create agent failed: {response}"
    return str(response["data"]["id"])


def create_chat(api_url: str, chat_id: str, agent_id: str, *, incognito: bool = False) -> None:
    response = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "Knowledge Pack E2E",
            "agent_id": agent_id,
            "action_mode": "agent",
            "is_incognito": incognito,
            "messages": [],
        },
    )
    assert isinstance(response, dict) and response.get("success") is True, f"Create chat failed: {response}"


def _mount_through_picker(
    client: ChromeMcpClient, page: McpPage, knowledge_bases: Sequence[KnowledgeBase], page_url: str
) -> None:
    """Toggle each knowledge base on in the composer's picker, as a user does, and wait for its chip."""
    opened = client.evaluate(page, _OPEN_PICKER_JS, timeout_sec=15.0)
    assert isinstance(opened, dict) and opened.get("ok") is True, opened
    for kb in knowledge_bases:
        name_json = json.dumps(kb.name)
        clicked = wait_for_state(client, page, _CLICK_SWITCH_JS.format(name_json=name_json), timeout_sec=60.0, page_url=page_url)
        assert clicked.get("ready") is True, clicked
        chip = wait_for_state(client, page, _MOUNTED_CHIP_JS.format(name_json=name_json), timeout_sec=60.0, page_url=page_url)
        assert chip.get("ready") is True, chip


def _assert_binding_on_server(chat_id: str, knowledge_bases: Sequence[KnowledgeBase], *, bound: bool) -> None:
    """The picker's toggle writes the conversation binding the turn is resolved from, except in an incognito chat."""
    response = http_json("GET", f"{get_e2e_api_url()}/api/v1/memory/shared-contexts/bindings/targets/conversation/{chat_id}")
    items = response.get("items") if isinstance(response, dict) else None
    held = {str(item.get("context_id")) for item in items or [] if isinstance(item, dict)}
    wanted = {kb.context_id for kb in knowledge_bases}
    if bound:
        assert wanted <= held, f"chat {chat_id} is bound to {sorted(held)}, expected {sorted(wanted)}"
    else:
        assert not wanted & held, f"incognito chat {chat_id} got a stored binding: {sorted(wanted & held)}"


def send_turn(ui_url: str, chat_id: str, prompt: str, *, mount: Sequence[KnowledgeBase] = (), incognito: bool = False) -> None:
    """Open the chat in real Chrome, wait for attach, mount the knowledge bases through the picker, send one real turn."""
    chat_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=chat_url)
        bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
        assert bridge.get("ready") is True, json.dumps(bridge, ensure_ascii=False)
        attached = wait_for_state(
            client, page, _ATTACH_CHAT_PROBE.format(chat_id_json=json.dumps(chat_id)), timeout_sec=90.0, page_url=chat_url
        )
        assert attached.get("ready") is True, json.dumps(attached, ensure_ascii=False)
        if incognito:
            mode = wait_for_state(client, page, _INCOGNITO_PROBE_JS, timeout_sec=30.0, page_url=chat_url)
            assert mode.get("ready") is True, mode
        if mount:
            _mount_through_picker(client, page, mount, chat_url)
            _assert_binding_on_server(chat_id, mount, bound=not incognito)
        sent = client.evaluate(page, _SEND_TURN_JS.format(prompt_json=json.dumps(prompt)), timeout_sec=90.0)
        assert isinstance(sent, dict) and sent.get("ok") is True, (
            f"send turn failed for chat {chat_id}: {json.dumps(sent, ensure_ascii=False)[:600]}"
        )


def _final_replies(chat_id: str, api_url: str) -> list[str]:
    return [reply for reply in completed_assistant_replies(stored_messages(chat_id, api_url)) if reply.strip()]


def completed_reply_count(chat_id: str, api_url: str) -> int:
    """How many answers the chat holds; the ``after`` of the wait for the next one."""
    return len(_final_replies(chat_id, api_url))


def _turn_is_over(chat_id: str, api_url: str) -> bool:
    """The server holds no run and no approval card of the chat any more."""
    reply = http_json("GET", f"{api_url}/api/v1/agents/chat/{chat_id}/turn-state")
    state = reply.get("data") if isinstance(reply, dict) else None
    return isinstance(state, dict) and state.get("running") is False and state.get("awaitingApproval") is False


def wait_final_reply(chat_id: str, api_url: str, *, after: int = 0) -> str:
    """The words of the newest non-empty answer beyond the first ``after``, once the run has ended.

    A run that calls tools first stores empty assistant steps before its answer, so the first completed assistant
    message is not the answer: waiting for the run to end is what makes an absence check mean something.
    """
    deadline = time.monotonic() + _REPLY_WAIT_SEC
    while time.monotonic() < deadline:
        replies = _final_replies(chat_id, api_url)
        if len(replies) > after and _turn_is_over(chat_id, api_url):
            return replies[-1]
        time.sleep(2.0)
    pytest.fail(f"no final assistant reply beyond {after} for chat {chat_id} within {_REPLY_WAIT_SEC}s")


def assert_stayed_out_of_the_thread(chat_id: str, api_url: str, *phrases: str) -> None:
    """Each phrase is in no stored user message and no stored tool result.

    The pack is appended to the model's input of one turn and stored nowhere, so a phrase the model quotes can only
    have come through it when the user's own message and every tool result are free of it.
    """
    for message in stored_messages(chat_id, api_url):
        if message.get("role") == "assistant":
            continue
        text = json.dumps(message, ensure_ascii=False, default=str)
        for phrase in phrases:
            assert phrase not in text, f"{phrase} is in a stored {message.get('role')} message of chat {chat_id}: {text[:300]}"


def discard(api_url: str, chat_ids: Sequence[str], knowledge_bases: Sequence[KnowledgeBase]) -> None:
    """Remove the chats, the shared contexts and their vault directories a test created."""
    gone = frozenset({200, 204, 404})
    for chat_id in chat_ids:
        http_json("DELETE", f"{api_url}/api/v1/chats/{chat_id}", expected_statuses=gone)
    for kb in knowledge_bases:
        http_json("DELETE", f"{api_url}/api/v1/memory/shared-contexts/{kb.context_id}", expected_statuses=gone)
        shutil.rmtree(kb.vault_dir, ignore_errors=True)
