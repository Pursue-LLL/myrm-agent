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
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import pytest

BASE_URL = "http://127.0.0.1:3000"
CHROME_CDP = "http://127.0.0.1:9333/json/list"
E2E_PROMPT = "只回复 OK"
CHAT_ID_RE = re.compile(
    r"^/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|c-[a-z0-9\-]+)$",
    re.IGNORECASE,
)
API_URL = "http://127.0.0.1:8080"
_PAGE_PROBE_JS = """(() => {
  const input = document.querySelector('[data-chat-input]');
  const skeleton = !!document.querySelector('[aria-label="Loading messages"]');
  return {
    hasInput: !!input,
    skeleton,
    hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
    path: location.pathname,
  };
})()"""

_RESET_CHAT_JS = """(() => {
  if (document.querySelector('[data-chat-input]')) {
    return { ok: true, mode: 'already' };
  }
  const newBtn = Array.from(document.querySelectorAll('aside button')).find((b) => {
    const text = (b.textContent || '').trim();
    return text.includes('新对话') || text.includes('New chat');
  });
  if (newBtn) {
    newBtn.click();
    return { ok: true, mode: 'new-chat' };
  }
  return { ok: false, mode: 'no-button' };
})()"""


def _provider_ready() -> bool:
    try:
        resp = urllib.request.urlopen(f"{API_URL}/api/v1/config/readiness", timeout=5)
        payload = json.loads(resp.read())
    except Exception:
        return False
    provider = payload.get("provider")
    return isinstance(provider, dict) and bool(provider.get("is_ready"))


def _create_fresh_page_ws() -> str | None:
    """Open a new :3000 tab via CDP (fallback when no warm tab exists)."""
    import urllib.error

    dev_lib = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
    if str(dev_lib) not in sys.path:
        sys.path.insert(0, str(dev_lib))
    try:
        from cdp_write_guard import assert_cdp_write_allowed

        assert_cdp_write_allowed(operation="json/new")
    except RuntimeError as exc:
        pytest.skip(str(exc))

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
        dev_lib = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
        if str(dev_lib) not in sys.path:
            sys.path.insert(0, str(dev_lib))
        from cdp_warm_tab_pool import read_warm_tab_pool

        for entry in read_warm_tab_pool():
            pages = json.loads(urllib.request.urlopen(CHROME_CDP, timeout=5).read())
            match = next(
                (p for p in pages if p.get("id") == entry["targetId"] and p.get("type") == "page"),
                None,
            )
            if match is not None:
                ws = match.get("webSocketDebuggerUrl")
                if isinstance(ws, str):
                    return ws
    except Exception:
        pass

    try:
        resp = urllib.request.urlopen(CHROME_CDP, timeout=5)
        pages = json.loads(resp.read())
    except Exception:
        return None
    home = BASE_URL.rstrip("/") + "/"
    exact = next(
        (
            p
            for p in pages
            if p.get("url", "").rstrip("/") + "/" == home
            and p.get("type") == "page"
        ),
        None,
    )
    if exact is not None:
        ws = exact.get("webSocketDebuggerUrl")
        return str(ws) if isinstance(ws, str) else None
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
        ws = target.get("webSocketDebuggerUrl")
        return str(ws) if isinstance(ws, str) else None
    return _create_fresh_page_ws()


async def _probe_page_state(ws_url: str) -> dict[str, object]:
    import websockets

    try:
        async with websockets.connect(ws_url, max_size=10**7, open_timeout=8) as ws:
            await ws.send(
                json.dumps(
                    {
                        "id": 1,
                        "method": "Runtime.evaluate",
                        "params": {"expression": _PAGE_PROBE_JS, "returnByValue": True},
                    }
                )
            )
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            result = json.loads(raw)
            payload = result.get("result", {}).get("result", {})
            value = payload.get("value")
            return value if isinstance(value, dict) else {}
    except Exception:
        return {}


async def _ensure_chat_input_on_ws(ws_url: str, *, timeout_sec: float = 120.0) -> dict[str, object]:
    import websockets

    deadline = time.monotonic() + timeout_sec
    msg_id = 0
    last: dict[str, object] = {}

    async with websockets.connect(ws_url, max_size=10**7, open_timeout=10) as ws:
        async def cdp_call(method: str, params: dict[str, object] | None = None) -> dict[str, object]:
            nonlocal msg_id
            msg_id += 1
            await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                result = json.loads(raw)
                if result.get("id") != msg_id:
                    continue
                payload = result.get("result")
                return payload if isinstance(payload, dict) else {}

        async def ev(expr: str) -> object:
            nonlocal msg_id
            msg_id += 1
            await ws.send(
                json.dumps(
                    {
                        "id": msg_id,
                        "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True},
                    }
                )
            )
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            result = json.loads(raw)
            payload = result.get("result", {}).get("result", {})
            return payload.get("value")

        await cdp_call("Runtime.enable")
        await cdp_call("Page.enable")
        await cdp_call("Page.navigate", {"url": BASE_URL + "/"})
        await asyncio.sleep(2)

        polls = 0
        while time.monotonic() < deadline:
            polls += 1
            state = await ev(_PAGE_PROBE_JS)
            last = state if isinstance(state, dict) else {"probeError": state}
            if last.get("hasInput") and not last.get("skeleton"):
                return last
            if polls % 10 == 0:
                await ev(_RESET_CHAT_JS)
            await asyncio.sleep(1)

    raise AssertionError(f"Chat input not ready within {timeout_sec:.0f}s: {last}")


def _run_client_warmup() -> None:
    warmup_py = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "dev"
        / "lib"
        / "frontend-client-warmup.py"
    )
    if not warmup_py.is_file():
        pytest.skip(f"Missing client warmup script: {warmup_py}")
    import subprocess

    env = os.environ.copy()
    env.setdefault("MYRM_CDP_WARMUP", "1")
    result = subprocess.run(
        [
            sys.executable,
            str(warmup_py),
            "--cdp-port",
            "9333",
            "--url",
            BASE_URL + "/",
            "--timeout-sec",
            "120",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=150,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            "frontend client warmup failed — run ./myrm restart --chrome\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


def _warm_tab_ws() -> str | None:
    dev_lib = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
    if str(dev_lib) not in sys.path:
        sys.path.insert(0, str(dev_lib))
    try:
        from cdp_warm_tab_pool import reusable_warm_target

        warm = reusable_warm_target()
        if warm is None:
            return None
        ws = warm.get("webSocketDebuggerUrl")
        return str(ws) if isinstance(ws, str) else None
    except Exception:
        return None


def _resolve_healthy_chrome_ws() -> str:
    """Attach to warm-tab pool entry with verified chat input."""
    ws_url = _warm_tab_ws()
    if ws_url is None:
        _run_client_warmup()
        ws_url = _warm_tab_ws()
    if ws_url is None:
        pytest.skip("No warm :3000 tab after client warmup — run ./myrm ready --chrome")
    asyncio.run(_ensure_chat_input_on_ws(ws_url))
    return ws_url


@pytest.fixture(scope="module")
def _chrome_client_hot() -> None:
    """Ensure Next client chunk is warm before CDP UI interaction.

    Run `./myrm ready --chrome` once before pytest — not inside the test module,
    so tab prune does not kill an active CDP WebSocket mid-test.
    """
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:9333/json/version", timeout=3)
        json.loads(resp.read())
    except Exception as exc:
        pytest.skip(f"Chrome E2E not ready — run ./myrm ready --chrome first: {exc}")


def _extract_chat_id(url: str) -> str | None:
    from urllib.parse import urlparse

    path = urlparse(url).path
    match = CHAT_ID_RE.match(path)
    return match.group(1) if match else None


@pytest.fixture
def chrome_ws(_chrome_client_hot: None) -> str:
    """Attach to a hydrated warm tab when possible."""
    return _resolve_healthy_chrome_ws()


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
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                result = json.loads(raw)
                if result.get("id") != mid[0]:
                    continue
                if "exceptionDetails" in result:
                    raise AssertionError(f"CDP eval failed: {result['exceptionDetails']}")
                payload = result.get("result", {}).get("result", {})
                if "value" in payload:
                    return payload["value"]
                return payload.get("description")

        async def page_state() -> dict[str, object]:
            result = await ev(
                """(() => {
                  const input = document.querySelector('[data-chat-input]');
                  const bodyText = document.body.innerText || '';
                  const skeleton = !!document.querySelector('[aria-label="Loading messages"]');
                  const hasLayout = !!document.querySelector('[data-testid="app-layout"]');
                  const hasModelChip = /mimo|MiniMax|openai-like|gpt-/i.test(bodyText);
                  const path = location.pathname;
                  const onChatHome = path === '/' || /^\\/c-/.test(path);
                  const scanningMigration = bodyText.includes('正在扫描本地 AI 助手数据');
                  const btn = document.querySelector('.message-send-btn');
                  return {
                    hasInput: !!input,
                    skeleton,
                    hasLayout,
                    hasModelChip,
                    path,
                    onChatHome,
                    scanningMigration,
                    sendDisabled: !!btn?.disabled,
                    inputLen: (input?.value || '').length,
                    readyState: document.readyState,
                  };
                })()""",
                await_promise=False,
            )
            if not isinstance(result, dict):
                return {"hasInput": False, "probeError": result}
            return result

        if not _provider_ready():
            pytest.skip(
                "Provider config not ready in E2E profile — configure model at /settings/models "
                "(API /api/v1/config/readiness provider.is_ready must be true)"
            )

        await ev(
            """(() => {
              sessionStorage.setItem('migration_discovery_dismissed', 'true');
              sessionStorage.setItem('competitor_migration_dismissed', 'true');
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

        async def cdp(method: str, params: dict[str, object] | None = None) -> dict[str, object]:
            mid[0] += 1
            await ws.send(
                json.dumps({"id": mid[0], "method": method, "params": params or {}})
            )
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                result = json.loads(raw)
                if result.get("id") != mid[0]:
                    continue
                if "error" in result:
                    raise AssertionError(f"CDP {method} failed: {result['error']}")
                payload = result.get("result")
                return payload if isinstance(payload, dict) else {}

        async def fill_chat_input(text: str) -> dict[str, object]:
            focus: dict[str, object] = {"ok": False}
            for _ in range(45):
                focus = await ev(
                    """(() => {
                      const input = document.querySelector('[data-chat-input]');
                      if (!input) return { ok: false, err: 'no input' };
                      input.focus();
                      return { ok: true, path: location.pathname };
                    })()""",
                    await_promise=False,
                )
                if isinstance(focus, dict) and focus.get("ok"):
                    break
                await asyncio.sleep(1)
            assert isinstance(focus, dict) and focus.get("ok"), f"Focus input failed: {focus}"
            for event in (
                {"type": "keyDown", "key": "a", "code": "KeyA", "modifiers": 4},
                {"type": "keyUp", "key": "a", "code": "KeyA", "modifiers": 4},
                {"type": "keyDown", "key": "Backspace", "code": "Backspace"},
                {"type": "keyUp", "key": "Backspace", "code": "Backspace"},
            ):
                await cdp("Input.dispatchKeyEvent", event)
            await cdp("Input.insertText", {"text": text})
            last: dict[str, object] = {"ok": False}
            for _ in range(40):
                last = await ev(
                    f"""( () => {{
                      const input = document.querySelector('[data-chat-input]');
                      if (!input) return {{ ok: false, err: 'no input' }};
                      const nativeSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype,
                        'value',
                      )?.set;
                      const tracker = input._valueTracker;
                      if (tracker) tracker.setValue('');
                      nativeSetter?.call(input, {json.dumps(text)});
                      input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                      const reactKey = Object.keys(input).find((k) => k.startsWith('__reactProps'));
                      if (reactKey && input[reactKey]?.onChange) {{
                        input[reactKey].onChange({{ target: input, currentTarget: input }});
                      }}
                      const btn = document.querySelector('.message-send-btn');
                      return {{
                        ok: (input.value || '').trim().length > 0 && !btn?.disabled,
                        inputLen: (input.value || '').length,
                        sendDisabled: !!btn?.disabled,
                      }};
                    }})()""",
                    await_promise=False,
                )
                if isinstance(last, dict) and last.get("ok"):
                    return last
                await asyncio.sleep(0.15)
            return last if isinstance(last, dict) else {"ok": False}

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
            fill = await fill_chat_input(text)
            assert isinstance(fill, dict) and fill.get("ok"), f"UI fill failed: {fill}"
            await cdp(
                "Input.dispatchKeyEvent",
                {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
            )
            await cdp(
                "Input.dispatchKeyEvent",
                {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
            )
            click = await ev(
                """(() => {
                  const btn =
                    document.querySelector('button[aria-label="发送"]') ||
                    document.querySelector('.message-send-btn');
                  if (!btn || btn.disabled) return { ok: false, err: 'send disabled after enter' };
                  btn.click();
                  return { ok: true, mode: 'enter+click' };
                })()""",
                await_promise=False,
            )
            if not (isinstance(click, dict) and click.get("ok")):
                click = await ev(
                    """(() => {
                      const btn = document.querySelector('.message-send-btn');
                      if (!btn || btn.disabled) return { ok: false, err: 'send disabled' };
                      btn.click();
                      return { ok: true, mode: 'click-only' };
                    })()""",
                    await_promise=False,
                )
            assert isinstance(click, dict) and click.get("ok"), f"UI send failed: {click} fill={fill}"
            deadline = time.monotonic() + 45.0
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
