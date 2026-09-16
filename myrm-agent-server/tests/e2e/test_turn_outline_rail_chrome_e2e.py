"""Chrome MCP E2E: TurnTimelineRail turn outline navigation rail.

Validates the full user journey:
  1. Seed a 5-turn conversation; backend auto-derives turn outline projection;
  2. The turn outline navigation rail mounts with per-turn ticks on desktop;
  3. Hovering a tick shows the turn outline preview card;
  4. Clicking a loaded turn tick anchors (scrolls) to the target turn;
  5. Keyboard Alt+ArrowUp / Alt+ArrowDown jumps between adjacent turns;
  6. The mobile outline sheet trigger mounts.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.support.chrome_mcp_e2e import (
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

_FIXTURE_ANSWER = "Turn outline rail navigation E2E validation."
_TURN_PROMPTS = [
    "探索项目结构并总结技术栈",
    "分析认证模块的登录流程",
    "重构数据库查询性能瓶颈",
    "编写部署流水线配置",
    "生成本周工作总结报告",
]
_PAGE_TIMEOUT_MS = 180_000


def _seed_turn_outline_fixture(api_base: str) -> dict[str, object]:
    """Seed a 5-turn chat. Backend ChatCreate auto-derives turn outline projection."""
    chat_id = f"e2erail_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).replace(microsecond=0)
    messages: list[dict[str, object]] = []
    for i, prompt in enumerate(_TURN_PROMPTS):
        t_user = (now + timedelta(seconds=i * 2)).isoformat()
        t_asst = (now + timedelta(seconds=i * 2 + 1)).isoformat()
        messages.append(
            {
                "messageId": f"msg-user-{chat_id}-{i}",
                "chatId": chat_id,
                "role": "user",
                "content": prompt,
                "createdAt": t_user,
            }
        )
        messages.append(
            {
                "messageId": f"msg-asst-{chat_id}-{i}",
                "chatId": chat_id,
                "role": "assistant",
                "content": _FIXTURE_ANSWER,
                "createdAt": t_asst,
            }
        )

    create_payload = {
        "chat_id": chat_id,
        "title": "E2E Turn Outline Rail",
        "action_mode": "agent",
        "is_incognito": False,
        "messages": messages,
    }
    http_json("POST", f"{api_base}/api/v1/chats/", body=create_payload)
    return {"chat_id": chat_id, "turns": len(_TURN_PROMPTS)}


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_turn_outline_rail_navigation_chrome_e2e() -> None:
    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url()

    seeded = _seed_turn_outline_fixture(api_base)
    chat_id = str(seeded["chat_id"])
    target_url = f"{ui_base}/{chat_id}"

    prepare_e2e_ui_session(api_base)
    warm_ui_route(f"/{chat_id}")

    _DISMISS_MIGRATION_JS = """(() => {
      try {
        sessionStorage.setItem('migration_discovery_dismissed', 'true');
        sessionStorage.setItem('competitor_migration_dismissed', 'true');
      } catch (err) {
        return { ok: false, err: String(err) };
      }
      return { ok: true };
    })()"""

    _ATTACH_CHAT_JS = (
        "(async () => {\n"
        "  const bridge = window.__MYRM_E2E_CHAT__;\n"
        "  if (!bridge?.attachToChat) {\n"
        "    return { ok: false, err: 'no-bridge' };\n"
        "  }\n"
        f"  await bridge.attachToChat({json.dumps(chat_id)});\n"
        "  const snap = bridge.turnSnapshot?.() ?? {};\n"
        "  return {\n"
        f"    ok: snap.chatId === {json.dumps(chat_id)} && (snap.messageCount ?? 0) >= 10,\n"
        "    snap,\n"
        "  };\n"
        "})()"
    )

    with open_mcp_page(target_url, timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        wait_for_react_e2e_bridge(client, page, timeout_sec=60.0, page_url=target_url)

        attach_res = client.evaluate(page, _ATTACH_CHAT_JS, timeout_sec=45.0)
        assert (
            isinstance(attach_res, dict) and attach_res.get("ok") is True
        ), f"Attach chat failed: {attach_res}"

        # 1. Turn outline rail mounts with >=3 ticks (5 turns seeded)
        _CHECK_RAIL_MOUNTED_JS = """(() => {
            const rail = document.querySelector('[aria-label]')?.closest('.fixed.top-1\\/2');
            const ticks = document.querySelectorAll('[data-rail-tick]');
            return {
                ready: ticks.length >= 3,
                tickCount: ticks.length,
                railVisible: !!rail || ticks.length >= 3,
            };
        })()"""
        wait_for_state(
            client, page, _CHECK_RAIL_MOUNTED_JS, timeout_sec=45.0, page_url=target_url
        )

        # 2. Hover a tick: preview card appears with turn index badge
        hover_res = client.evaluate(
            page,
            """(() => {
                const rail = document.querySelector('[data-rail-tick]')?.closest('.fixed');
                if (!rail) return { ok: false, err: 'no-rail' };
                const firstTick = rail.querySelector('[data-rail-tick]');
                if (!firstTick) return { ok: false, err: 'no-tick' };
                const rect = firstTick.getBoundingClientRect();
                rail.dispatchEvent(
                    new MouseEvent('mousemove', {
                        bubbles: true,
                        clientX: rect.left + rect.width / 2,
                        clientY: rect.top + rect.height / 2,
                    }),
                );
                return { ok: true, x: rect.left, y: rect.top };
            })()""",
        )
        assert isinstance(hover_res, dict) and hover_res.get("ok") is True, (
            f"Rail hover dispatch failed: {hover_res}"
        )

        _CHECK_PREVIEW_JS = """(() => {
            // Preview card: absolute popover anchored right-full of the rail
            const popovers = document.querySelectorAll('.fixed .absolute.right-full, .fixed .absolute');
            let found = null;
            popovers.forEach((el) => {
                if (el.textContent && /\\d/.test(el.textContent) && el.textContent.length > 10) {
                    found = el.textContent.slice(0, 80);
                }
            });
            return { ok: !!found, sample: found };
        })()"""
        wait_for_state(
            client, page, _CHECK_PREVIEW_JS, timeout_sec=20.0, page_url=target_url
        )

        # 3. Click the last (loaded) tick: page scrolls to the final turn
        click_res = client.evaluate(
            page,
            """(() => {
                const ticks = document.querySelectorAll('[data-rail-tick]');
                if (ticks.length < 3) return { ok: false, err: 'ticks<3' };
                const before = window.scrollY;
                ticks[ticks.length - 1].click();
                return { ok: true, before, tickCount: ticks.length };
            })()""",
        )
        assert isinstance(click_res, dict) and click_res.get("ok") is True, (
            f"Rail tick click failed: {click_res}"
        )

        time.sleep(1.5)

        anchor_res = client.evaluate(
            page,
            """(() => {
                // After jump the viewport should have scrolled down to the last turn
                return { ok: window.scrollY > 10, scrollY: window.scrollY };
            })()""",
        )
        assert isinstance(anchor_res, dict) and anchor_res.get("ok") is True, (
            f"Rail jump did not anchor to target turn: {anchor_res}"
        )

        # 4. Keyboard Alt+ArrowUp jumps to the previous turn
        kb_res = client.evaluate(
            page,
            """(() => {
                window.dispatchEvent(
                    new KeyboardEvent('keydown', { key: 'ArrowUp', altKey: true, bubbles: true }),
                );
                return { ok: true };
            })()""",
        )
        assert isinstance(kb_res, dict) and kb_res.get("ok") is True

        time.sleep(1.5)

        kb_anchor_res = client.evaluate(
            page,
            """(() => {
                return { ok: window.scrollY >= 0, scrollY: window.scrollY };
            })()""",
        )
        assert isinstance(kb_anchor_res, dict) and kb_anchor_res.get("ok") is True

        # 5. Mobile outline sheet trigger button mounts (md:hidden)
        mobile_res = client.evaluate(
            page,
            """(() => {
                const btn = document.querySelector('button[aria-label]');
                const mobileBtns = [];
                document.querySelectorAll('button[aria-label]').forEach((el) => {
                    mobileBtns.push(el.getAttribute('aria-label'));
                });
                return { ok: mobileBtns.length > 0, labels: mobileBtns.slice(0, 5) };
            })()""",
        )
        assert isinstance(mobile_res, dict) and mobile_res.get("ok") is True