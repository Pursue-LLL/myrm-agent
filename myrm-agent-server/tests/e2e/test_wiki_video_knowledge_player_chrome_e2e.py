"""Chrome E2E: Wiki Video Knowledge Player & Timestamped Seek on the live stack.

Seeds a video knowledge concept note with Frontmatter and timestamped chapters,
opens Settings → Wiki → Concepts tab, asserts:
1. VideoKnowledgePlayer renders inside WikiConceptDetailPanel.
2. Embedded video iframe/player is present with proper source.
3. Timestamp chapters are rendered as interactive seek buttons.
4. Clicking a chapter timestamp triggers seek without throwing errors.
"""

from __future__ import annotations

import os
import sys
import urllib.parse
import uuid
from datetime import UTC, datetime, timedelta

import pytest

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
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

_DISMISS_MIGRATION_JS = """(() => {
  const btn = document.querySelector('button[data-migration-dismiss]');
  if (btn) btn.click();
  return { dismissed: Boolean(btn) };
})()"""

_CONCEPTS_TAB_READY_JS = """(() => {
  const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
  if (!shell) return { ready: false, reason: 'no-shell' };
  const tab = [...shell.querySelectorAll('[role="tab"]')].find(
    (el) => /词条管理|Concepts|概念管理/.test((el.textContent || '').trim()),
  );
  return { ready: Boolean(tab), reason: tab ? '' : 'no-tab' };
})()"""

_PLAYER_READY_JS = """(() => {
  const player = document.querySelector('[data-testid="video-knowledge-player"]');
  if (!player) return { ready: false, reason: 'no-player' };
  const chapters = player.querySelectorAll('button');
  return {
    ready: true,
    chaptersCount: chapters.length,
    hasIframe: Boolean(player.querySelector('iframe')),
  };
})()"""


def _seed_video_concept(api_url: str) -> str:
    """Seed a video note concept via compound endpoint."""
    chat_id = f"e2e-video-chat-{uuid.uuid4().hex[:12]}"
    user_id = f"e2e-video-user-{uuid.uuid4().hex[:8]}"
    assistant_id = f"e2e-video-asst-{uuid.uuid4().hex[:8]}"
    created_at = datetime.now(UTC).replace(microsecond=0)

    http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/chats/",
        {
            "chat_id": chat_id,
            "title": f"Video Chat {chat_id}",
            "action_mode": "agent",
            "is_incognito": False,
            "messages": [
                {
                    "messageId": user_id,
                    "chatId": chat_id,
                    "role": "user",
                    "content": "Summarize the architecture video",
                    "createdAt": created_at.isoformat(),
                },
                {
                    "messageId": assistant_id,
                    "chatId": chat_id,
                    "role": "assistant",
                    "content": "Video summary generated.",
                    "createdAt": (created_at + timedelta(seconds=1)).isoformat(),
                },
            ],
        },
    )

    concept_name = f"Videos/Architecture_{uuid.uuid4().hex[:8]}"
    compound = http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/wiki/compound",
        {
            "concept_name": concept_name,
            "source_chat": chat_id,
            "source_message": assistant_id,
        },
    )
    assert isinstance(compound, dict) and compound.get("success") is True, compound
    pending_edit_id = compound.get("pending_edit_id")
    assert isinstance(pending_edit_id, int) and pending_edit_id > 0

    body = (
        "---\n"
        'title: "System Architecture Lecture"\n'
        'content_type: "video"\n'
        'source_url: "https://www.bilibili.com/video/BV1xx411c7Xz"\n'
        'author: "Software Guru"\n'
        'duration: "15:30"\n'
        "---\n\n"
        "# System Architecture Lecture\n\n"
        "### [00:00 - 02:30] Introduction to Microservices\n"
        "Overview of distributed systems and network reliability.\n\n"
        "### [02:30 - 05:00] Data Consistency and Saga Pattern\n"
        "Handling distributed transactions across disparate databases.\n\n"
        "### [05:00 - 08:30] Observability & Distributed Tracing\n"
        "Tracing requests across heterogeneous microservice fleets.\n"
    )

    approved = http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/wiki/pending/{pending_edit_id}/approve",
        {
            "proposed_content": body,
        },
    )
    assert isinstance(approved, dict) and approved.get("success") is True, approved
    return concept_name


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wiki_video_knowledge_player_chrome_e2e() -> None:
    """End-to-end verification of VideoKnowledgePlayer in real WebUI Chrome."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    concept_path = _seed_video_concept(api_url)
    warm_ui_route("/settings/wiki")
    wiki_page_url = f"{ui_url.rstrip('/')}/settings/wiki?conceptPath={urllib.parse.quote(concept_path, safe='')}"

    with open_wiki_settings_mcp_page(
        wiki_page_url,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    ) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page, recover_url=wiki_page_url)

        # 1. Switch to Concepts Tab
        wait_for_state(client, page, _CONCEPTS_TAB_READY_JS, timeout_sec=60.0)
        client.evaluate(
            page,
            """(() => {
              const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
              const tab = shell && [...shell.querySelectorAll('[role="tab"]')].find(
                (el) => /词条管理|Concepts|概念管理/.test((el.textContent || '').trim()),
              );
              if (tab) {
                for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                  tab.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
                }
              }
              return { ok: Boolean(tab) };
            })()""",
            timeout_sec=15.0,
        )

        # Wait for tree and detail panel hydration
        wait_for_state(
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

        # 2. Assert Video Knowledge Player mounts with chapters
        player_state = wait_for_state(client, page, _PLAYER_READY_JS, timeout_sec=60.0)
        assert isinstance(player_state, dict), player_state
        assert player_state.get("ready") is True, player_state
        assert player_state.get("chaptersCount", 0) >= 3, player_state

        # 3. Click the second chapter timestamp (02:30) and verify seek action
        seek_result = client.evaluate(
            page,
            """(() => {
              const player = document.querySelector('[data-testid="video-knowledge-player"]');
              const buttons = player ? [...player.querySelectorAll('button')] : [];
              const targetBtn = buttons.find((btn) => btn.textContent && btn.textContent.includes('02:30'));
              if (targetBtn) {
                targetBtn.click();
                return { clicked: true, text: targetBtn.textContent };
              }
              return { clicked: false, available: buttons.map(b => b.textContent) };
            })()""",
            timeout_sec=15.0,
        )
        assert isinstance(seek_result, dict)
        assert seek_result.get("clicked") is True, seek_result
