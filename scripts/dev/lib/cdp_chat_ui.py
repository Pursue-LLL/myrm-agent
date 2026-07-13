"""CDP helpers for WebUI chat E2E (controlled input + submit + turn wait)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Protocol

PAGE_PROBE_JS = """
(() => {
  const input = document.querySelector('[data-chat-input]');
  const skeleton = !!document.querySelector('[aria-label="Loading messages"]');
  return {
    hasInput: !!input,
    skeleton,
    hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
    path: location.pathname,
  };
})()
""".strip()

RESET_CHAT_JS = """
(() => {
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
})()
""".strip()

DISMISS_MODALS_JS = """
(() => {
  sessionStorage.setItem('migration_discovery_dismissed', 'true');
  sessionStorage.setItem('competitor_migration_dismissed', 'true');
  Array.from(document.querySelectorAll('button')).forEach((b) => {
    const text = (b.textContent || '').trim();
    if (/稍后再说|Later|Skip for now|关闭|Dismiss|Not now/i.test(text)) {
      b.click();
    }
  });
  return { ok: true };
})()
""".strip()


class CdpSocket(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...


class CdpChatSession:
    """Single WebSocket CDP session for chat UI automation."""

    def __init__(self, ws: CdpSocket, *, mid: list[int] | None = None) -> None:
        self._ws = ws
        self._mid = mid if mid is not None else [0]

    async def evaluate(self, expression: str, *, await_promise: bool = True) -> object:
        self._mid[0] += 1
        await self._ws.send(
            json.dumps(
                {
                    "id": self._mid[0],
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": True,
                        "awaitPromise": await_promise,
                    },
                }
            )
        )
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=30)
            result = json.loads(raw)
            if result.get("id") != self._mid[0]:
                continue
            if "exceptionDetails" in result:
                raise RuntimeError(f"CDP eval failed: {result['exceptionDetails']}")
            payload = result.get("result", {}).get("result", {})
            if "value" in payload:
                return payload["value"]
            return payload.get("description")

    async def cdp(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        recv_timeout: float = 30.0,
    ) -> dict[str, object]:
        self._mid[0] += 1
        await self._ws.send(
            json.dumps({"id": self._mid[0], "method": method, "params": params or {}})
        )
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=recv_timeout)
            result = json.loads(raw)
            if result.get("id") != self._mid[0]:
                continue
            if "error" in result:
                raise RuntimeError(f"CDP {method} failed: {result['error']}")
            payload = result.get("result")
            return payload if isinstance(payload, dict) else {}

    async def bootstrap(self, base_url: str, *, timeout_sec: float = 180.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        await self.cdp("Runtime.enable")
        await self.cdp("Page.enable")
        await self.cdp(
            "Page.navigate",
            {"url": base_url.rstrip("/") + "/"},
            recv_timeout=90.0,
        )
        await asyncio.sleep(2)
        polls = 0
        while time.monotonic() < deadline:
            polls += 1
            state = await self.evaluate(PAGE_PROBE_JS, await_promise=False)
            last = state if isinstance(state, dict) else {"probeError": state}
            if last.get("hasInput") and not last.get("skeleton"):
                return last
            if isinstance(last, dict) and last.get("hasLayout") is False and polls % 15 == 0:
                await self.cdp("Page.reload", {"ignoreCache": True})
                await asyncio.sleep(3)
            if polls % 10 == 0:
                await self.evaluate(RESET_CHAT_JS, await_promise=False)
            await asyncio.sleep(1)
        raise TimeoutError(f"Chat input not ready within {timeout_sec:.0f}s: {last}")

    async def dismiss_modals(self) -> None:
        await self.evaluate(DISMISS_MODALS_JS, await_promise=False)
        await asyncio.sleep(0.5)

    async def send_state(self) -> dict[str, object]:
        result = await self.evaluate(
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
        return result if isinstance(result, dict) else {"ok": False, "probeError": result}

    async def fill_input(self, text: str) -> dict[str, object]:
        for _ in range(45):
            focus = await self.evaluate(
                """(() => {
                  const input = document.querySelector('[data-chat-input]');
                  if (!input) return { ok: false, err: 'no input' };
                  input.focus();
                  input.click();
                  return { ok: true, path: location.pathname };
                })()""",
                await_promise=False,
            )
            if isinstance(focus, dict) and focus.get("ok"):
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError(f"Focus input failed: {focus}")

        react_fill = await self.evaluate(
            f"""( () => {{
              const input = document.querySelector('[data-chat-input]');
              if (!input) return {{ ok: false, err: 'no input' }};
              const text = {json.dumps(text)};
              input.focus();
              input.click();
              const fire = (el, value) => {{
                const propsKey = Object.keys(el).find((k) => k.startsWith('__reactProps$'));
                const apply = (onChange) => {{
                  const tracker = el._valueTracker;
                  if (tracker) tracker.setValue('');
                  el.value = value;
                  onChange({{ target: el, currentTarget: el }});
                }};
                if (propsKey && el[propsKey]?.onChange) {{
                  apply(el[propsKey].onChange);
                  return true;
                }}
                const fiberKey = Object.keys(el).find((k) => k.startsWith('__reactFiber$'));
                if (fiberKey) {{
                  let fiber = el[fiberKey];
                  while (fiber) {{
                    const onChange = fiber.memoizedProps?.onChange;
                    if (typeof onChange === 'function') {{
                      apply(onChange);
                      return true;
                    }}
                    fiber = fiber.return;
                  }}
                }}
                return false;
              }};
              const synced = fire(input, text);
              return new Promise((resolve) => {{
                requestAnimationFrame(() => {{
                  requestAnimationFrame(() => {{
                    const btn = document.querySelector('.message-send-btn');
                    resolve({{
                      ok: synced && (input.value || '').trim().length > 0 && !btn?.disabled,
                      inputLen: (input.value || '').length,
                      sendDisabled: !!btn?.disabled,
                      mode: synced ? 'react-onChange' : 'react-miss',
                    }});
                  }});
                }});
              }});
            }})()""",
            await_promise=True,
        )
        if isinstance(react_fill, dict) and react_fill.get("ok"):
            return react_fill

        await self.cdp("DOM.enable")
        mod_bit = 4 if sys.platform == "darwin" else 2
        await self.cdp(
            "Input.dispatchKeyEvent",
            {"type": "keyDown", "key": "a", "code": "KeyA", "modifiers": mod_bit},
        )
        await self.cdp(
            "Input.dispatchKeyEvent",
            {"type": "keyUp", "key": "a", "code": "KeyA", "modifiers": mod_bit},
        )
        await self.cdp("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace", "code": "Backspace"})
        await self.cdp("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace"})
        for ch in text:
            await self.cdp("Input.insertText", {"text": ch})
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.15)
        last = await self.send_state()
        if last.get("ok"):
            return last

        exec_fill = await self.evaluate(
            f"""( () => {{
              const input = document.querySelector('[data-chat-input]');
              if (!input) return {{ ok: false, err: 'no input' }};
              input.focus();
              input.click();
              const text = {json.dumps(text)};
              input.select();
              const inserted = document.execCommand('insertText', false, text);
              return new Promise((resolve) => {{
                requestAnimationFrame(() => {{
                  requestAnimationFrame(() => {{
                    const btn = document.querySelector('.message-send-btn');
                    resolve({{
                      ok: inserted && (input.value || '').trim().length > 0 && !btn?.disabled,
                      inputLen: (input.value || '').length,
                      sendDisabled: !!btn?.disabled,
                      mode: 'execCommand',
                    }});
                  }});
                }});
              }});
            }})()""",
            await_promise=True,
        )
        if isinstance(exec_fill, dict):
            return exec_fill
        return {"ok": False, "probeError": exec_fill}

    async def submit(self) -> dict[str, object]:
        react_click = await self.evaluate(
            """(() => {
              const btn = document.querySelector('.message-send-btn');
              if (!btn || btn.disabled) return { ok: false, err: 'send disabled or missing' };
              const propsKey = Object.keys(btn).find((k) => k.startsWith('__reactProps$'));
              if (propsKey && btn[propsKey]?.onClick) {
                btn[propsKey].onClick({ preventDefault() {}, stopPropagation() {} });
                return { ok: true, mode: 'react-onClick' };
              }
              const fiberKey = Object.keys(btn).find((k) => k.startsWith('__reactFiber$'));
              if (fiberKey) {
                let fiber = btn[fiberKey];
                while (fiber) {
                  const onClick = fiber.memoizedProps?.onClick;
                  if (typeof onClick === 'function') {
                    onClick({ preventDefault() {}, stopPropagation() {} });
                    return { ok: true, mode: 'fiber-onClick' };
                  }
                  fiber = fiber.return;
                }
              }
              return { ok: false, err: 'no react handler' };
            })()""",
            await_promise=False,
        )
        if isinstance(react_click, dict) and react_click.get("ok"):
            await asyncio.sleep(1.0)
            probe = await self.send_state()
            if int(probe.get("inputLen") or 0) == 0:
                return react_click

        click = await self.evaluate(
            """(() => {
              const input = document.querySelector('[data-chat-input]');
              const form = input?.closest('form');
              if (form && typeof form.requestSubmit === 'function') {
                form.requestSubmit();
                return { ok: true, mode: 'requestSubmit' };
              }
              const btn =
                document.querySelector('button[aria-label="发送"]') ||
                document.querySelector('button[aria-label="Send"]') ||
                document.querySelector('.message-send-btn');
              if (!btn) return { ok: false, err: 'no send button' };
              if (btn.disabled) return { ok: false, err: 'send disabled' };
              btn.dispatchEvent(
                new MouseEvent('click', { bubbles: true, cancelable: true, view: window }),
              );
              return { ok: true, mode: 'dispatchClick' };
            })()""",
            await_promise=False,
        )
        await asyncio.sleep(1.0)
        probe = await self.send_state()
        if int(probe.get("inputLen") or 0) == 0:
            return click if isinstance(click, dict) else {"ok": True, "mode": "cleared"}

        await self.cdp("DOM.enable")
        doc = await self.cdp("DOM.getDocument")
        root_id = doc.get("root", {}).get("nodeId")
        query = await self.cdp(
            "DOM.querySelector",
            {"nodeId": root_id, "selector": ".message-send-btn:not([disabled])"},
        )
        node_id = query.get("nodeId")
        if isinstance(node_id, int) and node_id > 0:
            try:
                box = await self.cdp("DOM.getBoxModel", {"nodeId": node_id})
                content = box.get("model", {}).get("content") if isinstance(box.get("model"), dict) else None
                if isinstance(content, list) and len(content) >= 6:
                    cx = (content[0] + content[2]) / 2
                    cy = (content[1] + content[5]) / 2
                    await self.cdp(
                        "Input.dispatchMouseEvent",
                        {
                            "type": "mousePressed",
                            "x": cx,
                            "y": cy,
                            "button": "left",
                            "clickCount": 1,
                        },
                    )
                    await self.cdp(
                        "Input.dispatchMouseEvent",
                        {
                            "type": "mouseReleased",
                            "x": cx,
                            "y": cy,
                            "button": "left",
                            "clickCount": 1,
                        },
                    )
                    return {"ok": True, "mode": "cdpMouseSend"}
            except RuntimeError:
                pass

        await self.cdp(
            "Input.dispatchKeyEvent",
            {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
        )
        await self.cdp(
            "Input.dispatchKeyEvent",
            {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
        )
        return {"ok": True, "mode": "enterKeyFallback"}

    async def main_state(self, prompt: str) -> dict[str, object]:
        result = await self.evaluate(
            f"""( () => {{
              const main = document.querySelector('main');
              const text = main?.innerText || '';
              const userMsgs = main?.querySelectorAll('[data-message-id]')?.length || 0;
              const sending = !!main?.querySelector('button[aria-label="Stop"]');
              const hasUserPrompt = userMsgs > 0 || text.includes({json.dumps(prompt)});
              const okInMain =
                hasUserPrompt &&
                (/\\bOK\\b/i.test(text) || (text.includes('OK') && text.length > 20));
              return {{
                url: location.href,
                path: location.pathname,
                userMsgs,
                sending,
                hasUserPrompt,
                okInMain,
                sample: text.slice(0, 500),
              }};
            }})()""",
            await_promise=False,
        )
        return result if isinstance(result, dict) else {"hasUserPrompt": False, "okInMain": False}

    async def wait_stream_started(self, prompt: str, *, timeout_sec: float = 120.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            last = await self.main_state(prompt)
            if (
                last.get("sending")
                or last.get("hasUserPrompt")
                or int(last.get("userMsgs") or 0) > 0
            ):
                return last
            await asyncio.sleep(0.5)
        raise TimeoutError(f"UI send did not start stream: {last}")

    async def wait_turn_done(self, prompt: str, *, timeout_sec: float = 180.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            last = await self.main_state(prompt)
            if last.get("sending"):
                await asyncio.sleep(1)
                continue
            if last.get("hasUserPrompt") and last.get("okInMain"):
                return last
            await asyncio.sleep(2)
        raise TimeoutError(f"Timed out waiting for assistant OK: {last}")

    async def wait_input_empty(self, *, timeout_sec: float = 60.0) -> None:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            probe = await self.send_state()
            last = probe
            if not probe.get("sendDisabled") and int(probe.get("inputLen") or 0) == 0:
                return
            await asyncio.sleep(1)
        raise TimeoutError(f"Chat input not ready for send: {last}")

    async def send_message(self, text: str, prompt_for_wait: str) -> dict[str, object]:
        await self.dismiss_modals()
        fill = await self.fill_input(text)
        if not fill.get("ok"):
            raise RuntimeError(f"UI fill failed: {fill}")
        submit = await self.submit()
        if not submit.get("ok"):
            raise RuntimeError(f"UI submit failed: {submit} fill={fill}")
        started = await self.wait_stream_started(prompt_for_wait)
        return {"fill": fill, "submit": submit, "started": started}


def create_fresh_page_ws(base_url: str, *, cdp_port: int = 9333) -> str:
    os.environ.setdefault("MYRM_CDP_WARMUP", "1")
    encoded = urllib.request.quote(base_url.rstrip("/") + "/", safe="")
    req = urllib.request.Request(
        f"http://127.0.0.1:{cdp_port}/json/new?{encoded}",
        method="PUT",
    )
    payload = json.loads(urllib.request.urlopen(req, timeout=15).read())
    ws = payload.get("webSocketDebuggerUrl")
    if not isinstance(ws, str) or not ws.startswith("ws://"):
        raise RuntimeError(f"CDP json/new missing webSocketDebuggerUrl: {payload!r}")
    return ws


def backend_log_path() -> Path:
    override = os.getenv("MYRM_BACKEND_LOG", "").strip()
    if override:
        return Path(override)
    state_dir = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    if state_dir:
        return Path(state_dir) / "backend.log"
    default = Path.home() / ".local/state/myrm-dev/backend.log"
    if default.is_file():
        return default
    server_root = Path(__file__).resolve().parents[3] / "myrm-agent-server"
    return server_root / ".myrm-dev-backend.log"


def snapshot_backend_log_offset() -> int:
    path = backend_log_path()
    if not path.is_file():
        return 0
    return path.stat().st_size


def count_execution_cache_in_log(*, since_offset: int) -> tuple[int, int]:
    path = backend_log_path()
    if not path.is_file():
        return 0, 0
    with path.open("rb") as handle:
        handle.seek(since_offset)
        chunk = handle.read()
    text = chunk.decode("utf-8", errors="replace")
    created = text.count("execution_cache_created")
    reused = text.count("execution_cache_reuse")
    return created, reused
