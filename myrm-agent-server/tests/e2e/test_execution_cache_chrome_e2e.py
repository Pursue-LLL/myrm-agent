"""Chrome E2E: POOLED execution cache via real WebUI (CDP, not Playwright).

Sends two agent messages through the chat textarea + send button on :3000,
asserts same chat URL and two OK assistant replies.

Prerequisites:
  ./myrm ready --chrome
  WebUI default model configured (E2E Chrome profile DB)
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.request

import pytest

BASE_URL = "http://127.0.0.1:3000"
CHROME_CDP = "http://127.0.0.1:9333/json/list"
E2E_PROMPT = "只回复 OK"
CHAT_ID_RE = re.compile(
    r"^/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|c-[a-z0-9\-]+)$",
    re.IGNORECASE,
)


def _create_fresh_page_ws() -> str | None:
    """Open a new :3000 tab via CDP (fallback when no warm tab exists)."""
    import urllib.error

    req = urllib.request.Request(
        f"{CHROME_CDP.replace('/json/list', '/json/new')}?{BASE_URL}/",
        method="PUT",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        page = json.loads(resp.read())
    except urllib.error.URLError:
        return None
    ws = page.get("webSocketDebuggerUrl")
    return str(ws) if isinstance(ws, str) else None


def _chrome_page_ws() -> str | None:
    try:
        resp = urllib.request.urlopen(CHROME_CDP, timeout=5)
        pages = json.loads(resp.read())
    except Exception:
        return None
    target = next(
        (
            p
            for p in pages
            if "127.0.0.1:3000" in p.get("url", "")
            and p.get("type") == "page"
            and "/settings" not in p.get("url", "")
        ),
        None,
    )
    if target is not None:
        return target.get("webSocketDebuggerUrl")
    return _create_fresh_page_ws()


@pytest.fixture(scope="module", autouse=True)
def _chrome_client_hot() -> None:
    """Ensure Next client chunk is warm before CDP UI interaction."""
    from pathlib import Path
    import subprocess

    monorepo = Path(__file__).resolve().parents[4]
    myrm = monorepo / "scripts" / "dev" / "myrm"
    if not myrm.is_file():
        pytest.skip("myrm helper missing — run from open-perplexity monorepo")
    subprocess.run(
        ["bash", str(myrm), "ready", "--chrome"],
        cwd=str(monorepo),
        timeout=180,
        check=False,
    )


def _extract_chat_id(url: str) -> str | None:
    from urllib.parse import urlparse

    path = urlparse(url).path
    match = CHAT_ID_RE.match(path)
    return match.group(1) if match else None


@pytest.fixture
def chrome_ws(_chrome_client_hot: None) -> str:
    ws_url = _chrome_page_ws()
    if not ws_url:
        ws_url = _create_fresh_page_ws()
    if not ws_url:
        pytest.skip("Chrome E2E not available (port 9333 or :3000 page missing)")
    return ws_url


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(420)
@pytest.mark.asyncio
async def test_chrome_ui_same_chat_two_ok_messages(chrome_ws: str) -> None:
    """Real WebUI: two agent turns in one chat must both return OK."""
    import websockets

    async with websockets.connect(chrome_ws, max_size=10**7, open_timeout=10) as ws:
        mid = [0]

        async def ev(expr: str, *, await_promise: bool = True) -> object:
            mid[0] += 1
            await ws.send(
                json.dumps(
                    {
                        "id": mid[0],
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": expr,
                            "returnByValue": True,
                            "awaitPromise": await_promise,
                        },
                    }
                )
            )
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
                result = json.loads(raw)
                if result.get("id") != mid[0]:
                    continue
                if "exceptionDetails" in result:
                    raise AssertionError(f"CDP eval failed: {result['exceptionDetails']}")
                payload = result.get("result", {}).get("result", {})
                if "value" in payload:
                    return payload["value"]
                return payload.get("description")

        ready: dict[str, object] = {"hasInput": False}
        await ev(
            """(() => {
              sessionStorage.setItem('migration_discovery_dismissed', 'true');
              sessionStorage.setItem('competitor_migration_dismissed', 'true');
              return { ok: true };
            })()""",
            await_promise=False,
        )
        await ev(
            f"window.location.replace({json.dumps(BASE_URL + '/')}); 'nav'",
            await_promise=False,
        )
        for _ in range(90):
            ready = await ev(
                """(() => {
                  const input = document.querySelector('[data-chat-input]');
                  const bodyText = document.body.innerText || '';
                  const unconfigured = bodyText.includes('未配置');
                  const hasLayout = !!document.querySelector('[data-testid="app-layout"]');
                  const hasModelChip = /mimo|MiniMax|openai-like|gpt-/i.test(bodyText);
                  const path = location.pathname;
                  const onChatHome = path === '/' || /^\\/c-/.test(path);
                  const scanningMigration = bodyText.includes('正在扫描本地 AI 助手数据');
                  return {
                    hasInput: !!input,
                    unconfigured,
                    hasLayout,
                    hasModelChip,
                    path,
                    onChatHome,
                    scanningMigration,
                  };
                })()""",
                await_promise=False,
            )
            if (
                isinstance(ready, dict)
                and ready.get("hasInput")
                and ready.get("hasModelChip")
                and ready.get("onChatHome")
                and not ready.get("scanningMigration")
            ):
                break
            await asyncio.sleep(1)
        await asyncio.sleep(3)
        assert isinstance(ready, dict) and ready.get("hasInput"), f"Chat input missing: {ready}"
        if ready.get("unconfigured") or not ready.get("hasModelChip"):
            pytest.skip(
                "WebUI default model not configured in E2E Chrome profile — "
                "configure provider + default model at /settings/models"
            )

        await ev(
            """(() => {
              const dismiss = Array.from(document.querySelectorAll('button')).find((b) => {
                const text = (b.textContent || '').trim();
                return text.includes('稍后再说') || text.includes('Later') || text.includes('Skip for now');
              });
              dismiss?.click();
              const newBtn = Array.from(document.querySelectorAll('aside button'))
                .find((b) => {
                  const text = (b.textContent || '').trim();
                  return text.includes('新对话') || text.includes('New chat');
                });
              newBtn?.click();
              return { mode: 'new', clicked: !!newBtn, dismissed: !!dismiss, path: location.pathname };
            })()""",
            await_promise=False,
        )
        await asyncio.sleep(2)

        async def cdp(method: str, params: dict[str, object] | None = None) -> dict[str, object]:
            mid[0] += 1
            await ws.send(
                json.dumps({"id": mid[0], "method": method, "params": params or {}})
            )
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
                result = json.loads(raw)
                if result.get("id") != mid[0]:
                    continue
                if "error" in result:
                    raise AssertionError(f"CDP {method} failed: {result['error']}")
                payload = result.get("result")
                return payload if isinstance(payload, dict) else {}

        async def fill_chat_input(text: str) -> dict[str, object]:
            focus = await ev(
                """(() => {
                  const input = document.querySelector('[data-chat-input]');
                  if (!input) return { ok: false, err: 'no input' };
                  input.focus();
                  return { ok: true };
                })()""",
                await_promise=False,
            )
            assert isinstance(focus, dict) and focus.get("ok"), f"Focus input failed: {focus}"
            for event in (
                {"type": "keyDown", "key": "a", "code": "KeyA", "modifiers": 4},
                {"type": "keyUp", "key": "a", "code": "KeyA", "modifiers": 4},
                {"type": "keyDown", "key": "Backspace", "code": "Backspace"},
                {"type": "keyUp", "key": "Backspace", "code": "Backspace"},
            ):
                await cdp("Input.dispatchKeyEvent", event)
            await cdp("Input.insertText", {"text": text})
            return await ev(
                """(() => {
                  const input = document.querySelector('[data-chat-input]');
                  const btn = document.querySelector('.message-send-btn');
                  return {
                    ok: !!input && (input.value || '').trim().length > 0 && !btn?.disabled,
                    inputLen: (input?.value || '').length,
                    sendDisabled: !!btn?.disabled,
                  };
                })()""",
                await_promise=False,
            )

        async def dismiss_modals() -> None:
            await ev(
                """(() => {
                  sessionStorage.setItem('migration_discovery_dismissed', 'true');
                  Array.from(document.querySelectorAll('button')).forEach((b) => {
                    const text = (b.textContent || '').trim();
                    if (/稍后再说|Later|Skip for now|关闭|Dismiss|Not now/i.test(text)) {
                      b.click();
                    }
                  });
                  return { ok: true };
                })()""",
                await_promise=False,
            )
            await asyncio.sleep(0.5)

        async def send_via_ui(text: str = E2E_PROMPT) -> dict[str, object]:
            await dismiss_modals()
            sample = await ev(
                """(() => {
                  const sampleBtn = Array.from(document.querySelectorAll('main button'))
                    .find((b) => (b.textContent || '').trim().length > 8);
                  if (sampleBtn) {
                    sampleBtn.click();
                    return { ok: true, mode: 'sample', label: (sampleBtn.textContent || '').trim().slice(0, 40) };
                  }
                  return { ok: false, mode: 'none' };
                })()""",
                await_promise=False,
            )
            if isinstance(sample, dict) and sample.get("ok"):
                await asyncio.sleep(0.3)
                if text != E2E_PROMPT:
                    fill = await fill_chat_input(text)
                else:
                    fill = await ev(
                        """(() => {
                          const btn = document.querySelector('.message-send-btn');
                          return {
                            ok: !!btn && !btn.disabled,
                            mode: 'sample-only',
                            inputLen: (document.querySelector('[data-chat-input]')?.value || '').length,
                            sendDisabled: !!btn?.disabled,
                          };
                        })()""",
                        await_promise=False,
                    )
            else:
                fill = await fill_chat_input(text)
            assert isinstance(fill, dict) and fill.get("ok"), f"UI fill failed: {fill} sample={sample}"
            click = await ev(
                """(() => {
                  const btn =
                    document.querySelector('button[aria-label="发送"]') ||
                    document.querySelector('.message-send-btn');
                  if (!btn) return { ok: false, err: 'no send button' };
                  if (btn.disabled) return { ok: false, err: 'send disabled' };
                  btn.click();
                  return { ok: true };
                })()""",
                await_promise=False,
            )
            assert isinstance(click, dict) and click.get("ok"), f"UI send click failed: {click}"
            deadline = time.monotonic() + 20.0
            post: dict[str, object] = {}
            while time.monotonic() < deadline:
                post = await main_state()
                if post.get("sending") or int(post.get("userMsgs") or 0) > 0:
                    return {"ok": True, "url": str(post.get("url") or ""), "fill": fill}
                await asyncio.sleep(0.5)
            pytest.fail(f"UI send did not start stream: fill={fill} click={click} state={post}")
            return {"ok": False}

        async def main_state() -> dict[str, object]:
            result = await ev(
                """(() => {
                  const main = document.querySelector('main');
                  const text = main?.innerText || '';
                  const userMsgs = main?.querySelectorAll('[data-message-id]')?.length || 0;
                  const sending = !!main?.querySelector('button[aria-label="Stop"]');
                  return {
                    url: location.href,
                    path: location.pathname,
                    userMsgs,
                    sending,
                    hasUserPrompt: userMsgs > 0,
                    okInMain: userMsgs > 0 && (text.length > 40 || /\\bOK\\b/i.test(text)),
                    sample: text.slice(0, 500),
                  };
                })()""",
                await_promise=False,
            )
            assert isinstance(result, dict)
            return result

        async def wait_turn_done(timeout_s: float = 180.0) -> dict[str, object]:
            deadline = time.monotonic() + timeout_s
            last: dict[str, object] = {}
            while time.monotonic() < deadline:
                last = await main_state()
                if last.get("sending"):
                    await asyncio.sleep(1)
                    continue
                if last.get("hasUserPrompt") and last.get("okInMain"):
                    return last
                await asyncio.sleep(2)
            raise AssertionError(f"Timed out waiting for assistant OK in main: {last}")

        async def active_chat_href() -> str | None:
            href = await ev(
                """(() => {
                  const links = Array.from(document.querySelectorAll('aside a[href]'))
                    .map((a) => a.href)
                    .filter((h) => h.includes('127.0.0.1:3000/') && !h.endsWith('/') && !h.includes('/settings'));
                  return links[0] || location.href;
                })()""",
                await_promise=False,
            )
            return str(href) if href else None

        await send_via_ui()
        after_first = await wait_turn_done()
        if str(after_first.get("path", "")).startswith("/settings"):
            pytest.fail(f"Send redirected to settings — model not configured: {after_first}")
        url_after_first = str(after_first.get("url") or "")
        chat_id = _extract_chat_id(url_after_first)
        if not chat_id:
            sidebar_href = await active_chat_href()
            chat_id = _extract_chat_id(sidebar_href or "")
        assert chat_id, f"Expected chat id after first turn: {after_first}"

        first_user_msgs = int(after_first.get("userMsgs") or 0)

        await send_via_ui()
        after_second = await wait_turn_done(timeout_s=180.0)
        url_after_second = str(after_second.get("url") or "")
        chat_id_second = _extract_chat_id(url_after_second)
        if not chat_id_second:
            sidebar_href = await active_chat_href()
            chat_id_second = _extract_chat_id(sidebar_href or "")
        assert chat_id_second == chat_id, (
            f"Second turn changed chat id: {chat_id} -> {chat_id_second}"
        )
        assert int(after_second.get("userMsgs") or 0) >= first_user_msgs + 1, (
            f"Expected another user message in main: {after_first} -> {after_second}"
        )
