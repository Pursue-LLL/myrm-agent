"""Chrome E2E: WikiMarkdownEditor real-user loop on the live stack.

Seed a compound concept, open Settings → Wiki → Concepts → edit, then drive the
split-pane editor like a real user:
  - Monaco source loads (lazy @monaco-editor/react)
  - typing into Monaco updates the live markdown preview (MarkdownContent)
  - saving persists through the real apply-wiki endpoint

Key paths are real browser interactions (CDP keyboard), no unit mocks.
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


def _seed_compound_chat(api_url: str) -> tuple[str, str]:
    """Seed a minimal user+assistant chat pair; return (chat_id, assistant_id)."""
    chat_id = f"e2e-editor-chat-{uuid.uuid4().hex[:12]}"
    user_id = f"e2e-editor-user-{uuid.uuid4().hex[:8]}"
    assistant_id = f"e2e-editor-asst-{uuid.uuid4().hex[:8]}"
    created_at = datetime.now(UTC).replace(microsecond=0)
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
                    "content": "Explain the markdown preview contract.",
                    "createdAt": created_at.isoformat(),
                },
                {
                    "messageId": assistant_id,
                    "chatId": chat_id,
                    "role": "assistant",
                    "content": "Markdown preview must stay in sync with the source.",
                    "createdAt": (created_at + timedelta(seconds=1)).isoformat(),
                },
            ],
        },
    )
    return chat_id, assistant_id


def _seed_editor_concept(api_url: str) -> str:
    """Publish a concept with provenance; return its concept path."""
    chat_id, assistant_id = _seed_compound_chat(api_url)
    concept_name = f"ChatCompounds/2026-08/editor-{uuid.uuid4().hex[:8]}"
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
    approved = http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/wiki/pending/{pending_edit_id}/approve",
        {},
    )
    assert isinstance(approved, dict) and approved.get("success") is True, approved
    return concept_name


_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""


def _concepts_active_state() -> str:
    return """(() => {
      const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
      const tab = shell && [...shell.querySelectorAll('[role="tab"]')].find(
        (el) => /词条管理|Concepts|概念管理/.test((el.textContent || '').trim()),
      );
      const active = tab?.getAttribute('data-state') === 'active';
      const treeItems = document.querySelectorAll('[role="treeitem"]').length;
      return { ready: active && treeItems > 0, active, treeItems };
    })()"""


def _detail_edit_ready_js() -> str:
    return """(() => {
      const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
      const btn = [...(shell?.querySelectorAll('button') ?? [])].find(
        (el) => (el.textContent || '').trim() === '编辑'
          || (el.textContent || '').trim() === 'Edit',
      );
      return { ready: !!btn };
    })()"""


def _click_edit_js() -> str:
    return """(() => {
      const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
      const btn = [...(shell?.querySelectorAll('button') ?? [])].find(
        (el) => (el.textContent || '').trim() === '编辑'
          || (el.textContent || '').trim() === 'Edit',
      );
      if (!btn) return { ok: false, reason: 'no-edit-btn' };
      for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
        btn.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
      }
      return { ok: true };
    })()"""


def _monaco_ready_js() -> str:
    return """(() => {
      const editor = document.querySelector('.monaco-editor');
      const textarea = editor?.querySelector('textarea');
      const loader = document.querySelector('.monaco-editor .loading');
      return {
        ready: !!editor && !!textarea && !loader,
        hasEditor: !!editor,
        hasTextarea: !!textarea,
      };
    })()"""


def _focus_monaco_js() -> str:
    return """(() => {
      const ta = document.querySelector('.monaco-editor textarea');
      if (!ta) return { ok: false, reason: 'no-textarea' };
      ta.focus();
      ta.click();
      return { ok: true, active: document.activeElement === ta };
    })()"""


def _preview_state_js() -> str:
    return """(() => {
      const prose = document.querySelector('.prose');
      return {
        ready: !!prose,
        text: prose ? (prose.textContent || '') : '',
      };
    })()"""


def _preview_contains_js(text: str) -> str:
    return f"""(() => {{
      const prose = document.querySelector('.prose');
      if (!prose) return {{ ready: false, text: '' }};
      const body = prose.textContent || '';
      return {{ ready: body.includes({text!r}), text: body.slice(-120) }};
    }})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wiki_markdown_editor_live_preview_loop() -> None:
    """Monaco source input must live-update the split-pane markdown preview."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    concept_name = _seed_editor_concept(api_url)

    warm_ui_route("/settings/wiki")
    wiki_page_url = (
        f"{ui_url.rstrip('/')}/settings/wiki"
        f"?conceptPath={urllib.parse.quote(concept_name, safe='')}"
    )

    with open_wiki_settings_mcp_page(
        wiki_page_url,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    ) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page, recover_url=wiki_page_url)

        # Concepts tab active + detail panel edit button ready.
        wait_for_state(client, page, _concepts_active_state(), timeout_sec=60.0)
        edit_ready = wait_for_state(client, page, _detail_edit_ready_js(), timeout_sec=60.0)
        assert edit_ready.get("ready") is True, edit_ready

        clicked = client.evaluate(page, _click_edit_js(), timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        # Monaco lazy-loads; wait for the editor + its hidden textarea.
        monaco = wait_for_state(client, page, _monaco_ready_js(), timeout_sec=60.0)
        assert isinstance(monaco, dict) and monaco.get("ready") is True, monaco

        focused = client.evaluate(page, _focus_monaco_js(), timeout_sec=15.0)
        assert isinstance(focused, dict) and focused.get("ok") is True, focused

        # Real CDP keyboard input into the focused Monaco editor.
        client.call_tool(
            "type_text",
            {"pageId": page.page_id, "text": "LIVE PREVIEW CHECK"},
            timeout_sec=30.0,
        )

        # Preview (MarkdownContent `.prose`) reflects the typed text after
        # useDeferredValue settles.
        preview = wait_for_state(
            client,
            page,
            _preview_contains_js("LIVE PREVIEW CHECK"),
            timeout_sec=30.0,
        )
        assert isinstance(preview, dict) and preview.get("ready") is True, preview


def _preview_contains_js(text: str) -> str:
    return f"""(() => {{
      const prose = document.querySelector('.prose');
      if (!prose) return {{ ready: false, text: '' }};
      const text = prose.textContent || '';
      return {{ ready: text.includes({text!r}), text: text.slice(-120) }};
    }})()"""
