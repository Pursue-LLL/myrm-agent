"""Chrome E2E: wiki concept detail panel source-chat provenance jump via real UI.

Full loop on the live stack, then drive the real WebUI like a user:
compound a chat message → approve → concept published with provenance →
open Settings → Wiki → Concepts tab → select the concept → assert the
"Source conversation" link renders with the expected deep-link href.
"""

from __future__ import annotations

import os
import sys
import urllib.parse
import uuid
from datetime import UTC, datetime, timedelta

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_wiki_settings_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)


def _seed_compound_chat(
    api_url: str,
) -> tuple[str, str, str]:
    chat_id = f"e2e-jump-chat-{uuid.uuid4().hex[:12]}"
    user_id = f"e2e-jump-user-{uuid.uuid4().hex[:8]}"
    assistant_id = f"e2e-jump-asst-{uuid.uuid4().hex[:8]}"
    created_at = datetime.now(UTC).replace(microsecond=0)
    user_created = created_at.isoformat()
    assistant_created = (created_at + timedelta(seconds=1)).isoformat()

    http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/chats/",
        {
            "chat_id": chat_id,
            "title": f"CI chat {chat_id}",
            "action_mode": "agent",
            "is_incognito": False,
            "messages": [
                {
                    "messageId": user_id,
                    "chatId": chat_id,
                    "role": "user",
                    "content": "What is continuous integration?",
                    "createdAt": user_created,
                },
                {
                    "messageId": assistant_id,
                    "chatId": chat_id,
                    "role": "assistant",
                    "content": ("Continuous integration automates testing on every change."),
                    "createdAt": assistant_created,
                },
            ],
        },
    )
    return chat_id, user_id, assistant_id


def _compound_post(api_url: str, *, chat_id: str, message_id: str, concept_name: str) -> dict[str, object]:
    payload = http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/wiki/compound",
        {
            "concept_name": concept_name,
            "source_chat": chat_id,
            "source_message": message_id,
        },
    )
    assert isinstance(payload, dict), payload
    return payload


def _seed_provenance_concept(api_url: str) -> tuple[str, str]:
    """Publish a concept with provenance; return (concept_name, source_chat)."""
    chat_id, _user_id, assistant_id = _seed_compound_chat(api_url)
    concept_name = f"ChatCompounds/2026-08/jump-{uuid.uuid4().hex[:8]}"

    compound = _compound_post(
        api_url,
        chat_id=chat_id,
        message_id=assistant_id,
        concept_name=concept_name,
    )
    assert compound.get("success") is True
    pending_edit_id = compound.get("pending_edit_id")
    assert isinstance(pending_edit_id, int) and pending_edit_id > 0

    approved = http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/wiki/pending/{pending_edit_id}/approve",
        {},
    )
    assert approved.get("success") is True
    return concept_name, chat_id


_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_CONCEPTS_TAB_READY_JS = """(() => {
  const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
  if (!shell) {
    return { ready: false, reason: 'no-shell', pathname: location.pathname };
  }
  const tabs = [...shell.querySelectorAll('[role="tab"]')].map(
    (el) => (el.textContent || '').trim(),
  );
  return {
    ready: tabs.some((t) => /词条管理|Concepts|概念管理/.test(t)),
    pathname: location.pathname,
    tabs,
  };
})()"""

_PROVENANCE_LINK_JS = """(() => {
  // i18n: locale may be zh (来源对话 / 來源對話) or en (Source conversation).
  const srcLabels = ['Source conversation', '来源对话', '來源對話'];
  const panel = [...document.querySelectorAll('a')].find((a) => {
    const text = (a.textContent || '').trim();
    return srcLabels.some((label) => text === label);
  });
  if (panel) {
    return { ready: true, ok: true, href: panel.getAttribute('href') };
  }
  const titleEl = [...document.querySelectorAll('span')].find(
    (el) => (el.textContent || '').startsWith('chatcompounds/'),
  );
  const treeLeaves = [...document.querySelectorAll('[role="treeitem"]')]
    .filter((el) => !el.querySelector('[role="treeitem"]'))
    .map((el) => (el.textContent || '').trim().slice(0, 30));
  const allText = document.body?.innerText || '';
  const headerText = (() => {
    // WikiConceptDetailPanel header sits near the concept title span.
    const titleSpan = [...document.querySelectorAll('span')].find(
      (el) => (el.textContent || '').startsWith('chatcompounds/'),
    );
    return titleSpan?.parentElement?.parentElement?.innerText?.slice(0, 200) ?? null;
  })();
  const allLinks = [...document.querySelectorAll('a')]
    .map((a) => (a.textContent || '').trim().slice(0, 40))
    .filter(Boolean)
    .slice(0, 20);
  const proseLen = [...document.querySelectorAll('.prose')].length;
  return {
    ok: false,
    reason: 'no-source-chat-link',
    conceptTitle: titleEl ? titleEl.textContent?.slice(0, 60) ?? null : null,
    headerText,
    treeLeaves,
    proseLen,
    allLinks,
    bodyLen: allText.length,
    tail: allText.slice(-700),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wiki_concept_detail_source_jump() -> None:
    """Concept detail panel must render a working source-chat deep link."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    concept_name, source_chat = _seed_provenance_concept(api_url)

    warm_ui_route("/settings/wiki")
    wiki_page_url = f"{ui_url.rstrip('/')}/settings/wiki?conceptPath={urllib.parse.quote(concept_name, safe='')}"

    with open_wiki_settings_mcp_page(
        wiki_page_url,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    ) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page, recover_url=wiki_page_url)

        tabs_state = wait_for_state(
            client,
            page,
            _CONCEPTS_TAB_READY_JS,
            timeout_sec=60.0,
        )
        assert isinstance(tabs_state, dict)
        assert tabs_state.get("ready") is True, tabs_state

        clicked = client.evaluate(
            page,
            """(() => {
              const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
              if (!shell) return { ok: false, reason: 'no-shell' };
              const tab = [...shell.querySelectorAll('[role="tab"]')].find(
                (el) => /词条管理|Concepts|概念管理/.test((el.textContent || '').trim()),
              );
              if (!tab) return { ok: false, reason: 'no-tab' };
              // Radix Tabs triggers need the full pointer sequence under
              // real-browser hydration; a bare .click() can be swallowed.
              for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                tab.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
              }
              return { ok: true, active: tab.getAttribute('data-state') === 'active' };
            })()""",
            timeout_sec=15.0,
        )
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        # Wait for the concepts tab to be truly active and the tree to mount.
        concepts_state = wait_for_state(
            client,
            page,
            """(() => {
              const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
              const tab = shell && [...shell.querySelectorAll('[role="tab"]')].find(
                (el) => /词条管理|Concepts|概念管理/.test((el.textContent || '').trim()),
              );
              const active = tab?.getAttribute('data-state') === 'active';
              const treeItems = document.querySelectorAll('[role="treeitem"]').length;
              return { ready: active && treeItems > 0, active, treeItems };
            })()""",
            timeout_sec=60.0,
        )
        assert isinstance(concepts_state, dict), concepts_state
        assert concepts_state.get("ready") is True, concepts_state

        # The concept is deep-linked via ?conceptPath, so the concepts tree auto
        # expands the ancestor folders and loads the detail panel. Wait for the
        # detail panel (Source conversation link) instead of locating the leaf in
        # the collapsed tree DOM.
        link_state = wait_for_state(
            client,
            page,
            _PROVENANCE_LINK_JS,
            timeout_sec=60.0,
        )
        assert isinstance(link_state, dict), link_state
        assert link_state.get("ok") is True, link_state
        href = str(link_state.get("href") or "")
        assert href.startswith(f"/{source_chat}"), f"expected deep link under /{source_chat}, got {href!r}"
        assert "highlight=" in href, f"expected message-level ?highlight, got {href!r}"
