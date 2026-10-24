"""Real Chrome MCP E2E: cross-session Working State badge and Settings copy.

The working state is a profile-level note injected into the memory context. This
test seeds one through the public API, verifies the chat badge exposes the full
content through its disclosure control, and verifies Settings explains that the
note is cross-session and not read in incognito.

Declared PRIVATE because it writes the instance-wide working-state profile.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_WORKING_STATE = (
    "E2E cross-session release check. "
    "Release note: https://example.com/releases/"
    + "a" * 220
)
_BADGE_JS = """(() => {
  const summary = Array.from(document.querySelectorAll('summary')).find(
    (el) => (el.textContent || '').includes('Working State') || (el.textContent || '').includes('工作状态'),
  );
  if (!summary) return { ready: false, reason: 'summary-missing' };
  const details = summary.closest('details');
  const chevron = summary.querySelector('svg');
  const body = details ? details.querySelector('p') : null;
  if (!details || !chevron || !body) {
    return { ready: false, reason: 'disclosure-missing', hasDetails: !!details, hasChevron: !!chevron, hasBody: !!body };
  }
  if (!details.open) {
    details.open = true;
    return { ready: false, reason: 'opening-disclosure' };
  }
  const style = getComputedStyle(body);
  return {
    ready: true,
    text: body.textContent || '',
    hasChevron: true,
    overflowWrap: style.overflowWrap,
    scrollWidth: body.scrollWidth,
    clientWidth: body.clientWidth,
  };
})()"""
_SETTINGS_JS = """(() => {
  const all = Array.from(document.querySelectorAll('span, p, div'));
  const title = all.find((el) => {
    const value = (el.textContent || '').trim();
    return value === 'Working State' || value === '工作状态';
  });
  const card = title ? title.closest('.rounded-xl') : null;
  const text = card ? card.innerText : (document.body ? document.body.innerText : '');
  return {
    ready: Boolean(card) && text.includes(title ? title.textContent.trim() : ''),
    hasCrossSession: /cross-session|跨会话/i.test(text),
    hasIncognitoBoundary: /incognito|隐身/i.test(text),
    hasLegacyTitle: /Working Memory|工作记忆/.test(text),
    cardText: text.slice(0, 300),
  };
})()"""

_ADD_STATE_JS = """(() => {
  const card = (() => {
    const title = Array.from(document.querySelectorAll('span, p, div')).find((el) => {
      const value = (el.textContent || '').trim();
      return value === 'Working State' || value === '工作状态';
    });
    return title ? title.closest('.rounded-xl') : null;
  })();
  if (!card) return { ok: false, reason: 'card-missing' };
  const add = Array.from(card.querySelectorAll('button')).find((el) => {
    const label = (el.textContent || '').trim();
    return ['Add', '添加', '新增', '追加'].includes(label);
  });
  if (!add) return { ok: false, reason: 'add-missing' };
  add.click();
  return { ok: true };
})()"""
_FILL_STATE_JS = """(() => {
  const card = (() => {
    const title = Array.from(document.querySelectorAll('span, p, div')).find((el) => {
      const value = (el.textContent || '').trim();
      return value === 'Working State' || value === '工作状态';
    });
    return title ? title.closest('.rounded-xl') : null;
  })();
  const textarea = card ? card.querySelector('textarea') : null;
  if (!textarea) return { ok: false, reason: 'textarea-missing' };
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
  if (!setter) return { ok: false, reason: 'setter-missing' };
  setter.call(textarea, %s);
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  return { ok: true };
})()"""
_SAVE_STATE_JS = """(() => {
  const card = (() => {
    const title = Array.from(document.querySelectorAll('span, p, div')).find((el) => {
      const value = (el.textContent || '').trim();
      return value === 'Working State' || value === '工作状态';
    });
    return title ? title.closest('.rounded-xl') : null;
  })();
  const save = card ? Array.from(card.querySelectorAll('button')).find((el) => {
    const label = (el.textContent || '').trim();
    return ['Save', '保存', '儲存'].includes(label);
  }) : null;
  if (!save) return { ok: false, reason: 'save-missing' };
  if (save.disabled) return { ok: false, reason: 'save-disabled' };
  save.click();
  return { ok: true };
})()"""
_STATE_SAVED_JS = """(() => {
  const text = document.body ? document.body.innerText : '';
  return { ready: text.includes('E2E cross-session release check.') };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_working_state_badge_and_settings_chrome_e2e() -> None:
    """Seed a working state, open the real badge, and verify the Settings contract."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url().rstrip("/")
    chat_id = f"e2e_working_state_{uuid.uuid4().hex[:8]}"
    seeded = False
    try:
        http_json(
            "POST",
            f"{api_url}/api/v1/chats/",
            body={
                "chat_id": chat_id,
                "title": "E2E Working State Badge",
                "action_mode": "agent",
                "is_incognito": False,
                "messages": [
                    {
                        "messageId": f"e2e-user-{uuid.uuid4().hex[:8]}",
                        "chatId": chat_id,
                        "role": "user",
                        "content": "E2E working state badge seed.",
                        "createdAt": datetime.now(UTC).isoformat(),
                    }
                ],
            },
        )
        seeded = True

        prepare_e2e_ui_session(api_url)
        chat_url = f"{ui_url}/{chat_id}"
        warm_ui_route("/settings/memory")
        with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)
            settings = wait_for_state(client, page, _SETTINGS_JS, timeout_sec=90.0)
            assert settings.get("ready") is True, settings
            assert settings.get("hasCrossSession") is True, settings
            assert settings.get("hasIncognitoBoundary") is True, settings
            assert settings.get("hasLegacyTitle") is False, settings

            add = client.evaluate(page, _ADD_STATE_JS, timeout_sec=15.0)
            assert isinstance(add, dict) and add.get("ok") is True, add
            textarea_ready = wait_for_state(
                client,
                page,
                """(() => {
                  const card = (() => {
                    const title = Array.from(document.querySelectorAll('span, p, div')).find((el) => {
                      const value = (el.textContent || '').trim();
                      return value === 'Working State' || value === '工作状态';
                    });
                    return title ? title.closest('.rounded-xl') : null;
                  })();
                  return { ready: Boolean(card && card.querySelector('textarea')) };
                })()""",
                timeout_sec=30.0,
            )
            assert textarea_ready.get("ready") is True, textarea_ready
            filled = client.evaluate(page, _FILL_STATE_JS % repr(_WORKING_STATE), timeout_sec=15.0)
            assert isinstance(filled, dict) and filled.get("ok") is True, filled
            save_ready = wait_for_state(
                client,
                page,
                """(() => {
                  const card = (() => {
                    const title = Array.from(document.querySelectorAll('span, p, div')).find((el) => {
                      const value = (el.textContent || '').trim();
                      return value === 'Working State' || value === '工作状态';
                    });
                    return title ? title.closest('.rounded-xl') : null;
                  })();
                  const save = card ? Array.from(card.querySelectorAll('button')).find((el) => {
                    const label = (el.textContent || '').trim();
                    return ['Save', '保存', '儲存'].includes(label);
                  }) : null;
                  return { ready: Boolean(save && !save.disabled) };
                })()""",
                timeout_sec=30.0,
            )
            assert save_ready.get("ready") is True, save_ready
            saved = client.evaluate(page, _SAVE_STATE_JS, timeout_sec=15.0)
            assert isinstance(saved, dict) and saved.get("ok") is True, saved
            state_saved = wait_for_state(client, page, _STATE_SAVED_JS, timeout_sec=30.0)
            assert state_saved.get("ready") is True, state_saved

        warm_ui_route(f"/{chat_id}")
        with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)
            wait_for_react_e2e_bridge(client, page, timeout_sec=60.0, page_url=chat_url)
            badge = wait_for_state(client, page, _BADGE_JS, timeout_sec=90.0)
            assert badge.get("ready") is True, badge
            assert badge.get("hasChevron") is True, badge
            assert _WORKING_STATE in str(badge.get("text", "")), badge
            assert str(badge.get("overflowWrap", "")).lower() in {"break-word", "anywhere"}, badge

    finally:
        if seeded:
            try:
                http_json(
                    "DELETE",
                    f"{api_url}/api/v1/memory/working-state",
                    expected_statuses=frozenset({200, 204}),
                )
            except Exception:
                pass
            try:
                http_json(
                    "DELETE",
                    f"{api_url}/api/v1/chats/{chat_id}",
                    expected_statuses=frozenset({200, 204}),
                )
            except Exception:
                pass
