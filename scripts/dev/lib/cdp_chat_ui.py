"""CDP helpers for WebUI chat E2E (controlled input + submit + turn wait)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cdp_transient_targets import close_exact_target, register_target, unregister_target
from cdp_write_guard import assert_cdp_write_allowed

API_URL = "http://127.0.0.1:8080"
_OK_REPLY_RE = re.compile(r"\bOK\b", re.IGNORECASE)
_CHAT_ID_PATH_RE = re.compile(
    r"^/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|c-[a-z0-9\-]+)$",
    re.IGNORECASE,
)

PAGE_PROBE_JS = """
(() => {
  const input = document.querySelector('[data-chat-input]');
  const skeleton = !!document.querySelector('[aria-label="Loading messages"]');
  const fiberKey = input
    ? Object.keys(input).find((k) => k.startsWith('__reactFiber$'))
    : null;
  return {
    hasInput: !!input,
    clientHydrated: !!fiberKey || !!(window.__MYRM_E2E_CHAT__?.setInputMessage),
    hasBridge: !!window.__MYRM_E2E_CHAT__,
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
    if (/稍后再说|Later|Skip for now|关闭|Dismiss|Not now|打开迁移向导/i.test(text)) {
      b.click();
    }
  });
  return { ok: true };
})()
""".strip()

E2E_BRIDGE_INSTALL_JS = """
(() => {
  const host = location.hostname;
  if (host !== '127.0.0.1' && host !== 'localhost') {
    return { ok: false, err: 'not-localhost' };
  }
  const syncInput = (message) => {
    const input = document.querySelector('[data-chat-input]');
    if (!input) return false;
    const text = String(message);
    const applyOnChange = (onChange) => {
      const tracker = input._valueTracker;
      if (tracker) tracker.setValue('');
      input.value = text;
      onChange({ target: input, currentTarget: input });
    };
    const propsKey = Object.keys(input).find((k) => k.startsWith('__reactProps$'));
    if (propsKey && input[propsKey]?.onChange) {
      applyOnChange(input[propsKey].onChange);
      return true;
    }
    const fiberKey = Object.keys(input).find((k) => k.startsWith('__reactFiber$'));
    if (fiberKey) {
      let fiber = input[fiberKey];
      while (fiber) {
        const onChange = fiber.memoizedProps?.onChange;
        if (typeof onChange === 'function') {
          applyOnChange(onChange);
          return true;
        }
        fiber = fiber.return;
      }
    }
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
    if (setter) setter.call(input, text);
    else input.value = text;
    input.dispatchEvent(new InputEvent('input', { bubbles: true, data: text, inputType: 'insertText' }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  };
  const install = () => {
    const existing = window.__MYRM_E2E_CHAT__;
    if (existing?.setInputMessage && existing?.handleSubmit && !existing.__e2eFallback) {
      return { ok: true, mode: 'react-bridge' };
    }
    window.__MYRM_E2E_CHAT__ = {
      __e2eFallback: true,
      setInputMessage: (message) => { syncInput(message); },
      handleSubmit: () => {
        const btn = document.querySelector('.message-send-btn');
        if (!btn) return;
        const fiberKey = Object.keys(btn).find((k) => k.startsWith('__reactFiber$'));
        if (fiberKey) {
          let fiber = btn[fiberKey];
          while (fiber) {
            const onClick = fiber.memoizedProps?.onClick;
            if (typeof onClick === 'function') {
              onClick({ preventDefault() {}, stopPropagation() {} });
              return;
            }
            fiber = fiber.return;
          }
        }
        const propsKey = Object.keys(btn).find((k) => k.startsWith('__reactProps$'));
        if (propsKey && btn[propsKey]?.onClick) {
          btn[propsKey].onClick({ preventDefault() {}, stopPropagation() {} });
          return;
        }
        if (!btn.disabled) btn.click();
      },
      getInputMessage: () => {
        const input = document.querySelector('[data-chat-input]');
        return (input?.value || '').trim();
      },
    };
    return { ok: true, mode: 'installed-fallback' };
  };
  if (window.__MYRM_E2E_CHAT__?.setInputMessage && window.__MYRM_E2E_CHAT__?.handleSubmit) {
    if (!window.__MYRM_E2E_CHAT__.__e2eFallback) {
      return { ok: true, mode: 'existing-react' };
    }
    return { ok: true, mode: 'existing-fallback' };
  }
  return install();
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

    async def evaluate(
        self,
        expression: str,
        *,
        await_promise: bool = True,
        recv_timeout: float = 60.0,
    ) -> object:
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
            raw = await asyncio.wait_for(self._ws.recv(), timeout=recv_timeout)
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

    async def bootstrap(
        self,
        base_url: str,
        *,
        timeout_sec: float = 180.0,
        navigate: bool = False,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        await self.cdp("Runtime.enable")
        await self.cdp("Page.enable")
        if navigate:
            probe = await self.evaluate(PAGE_PROBE_JS, await_promise=False)
            if not (isinstance(probe, dict) and probe.get("hasInput") and not probe.get("skeleton")):
                await self.cdp(
                    "Page.navigate",
                    {"url": base_url.rstrip("/") + "/"},
                    recv_timeout=120.0,
                )
                await asyncio.sleep(2)
        else:
            await asyncio.sleep(2)
        polls = 0
        shell_ready = False
        while time.monotonic() < deadline:
            polls += 1
            try:
                state = await self.evaluate(PAGE_PROBE_JS, await_promise=False)
            except TimeoutError:
                state = {"probeError": "evaluate_timeout"}
            last = state if isinstance(state, dict) else {"probeError": state}
            if last.get("hasInput") and not last.get("skeleton"):
                shell_ready = True
                break
            if (
                not navigate
                and polls == 20
                and not last.get("hasInput")
            ):
                await self.cdp(
                    "Page.navigate",
                    {"url": base_url.rstrip("/") + "/"},
                    recv_timeout=120.0,
                )
                await asyncio.sleep(3)
            if isinstance(last, dict) and last.get("hasLayout") is False and polls % 15 == 0:
                await self.cdp("Page.reload", {"ignoreCache": True}, recv_timeout=120.0)
                await asyncio.sleep(3)
            if polls % 10 == 0:
                await self.evaluate(RESET_CHAT_JS, await_promise=False)
            await asyncio.sleep(1)
        if not shell_ready:
            raise TimeoutError(f"Chat shell not ready within {timeout_sec:.0f}s: {last}")

        bridge_timeout = max(0.0, deadline - time.monotonic())
        if bridge_timeout > 0:
            await self.ensure_dev_bridge(timeout_sec=min(bridge_timeout, 90.0))
            hydrate_timeout = max(0.0, deadline - time.monotonic())
            if hydrate_timeout > 0:
                await self._wait_react_hydration(timeout_sec=hydrate_timeout)
            last = await self.evaluate(PAGE_PROBE_JS, await_promise=False)
            if not isinstance(last, dict):
                last = {"probeError": last}
        return last

    async def _wait_react_hydration(self, *, timeout_sec: float) -> None:
        """Wait until MessageInput is client-hydrated; reload if Turbopack stalls."""
        deadline = time.monotonic() + timeout_sec
        polls = 0
        reloads = 0
        while time.monotonic() < deadline:
            polls += 1
            hydrated = await self.evaluate(
                """(() => {
                  const input = document.querySelector('[data-chat-input]');
                  const btn = document.querySelector('.message-send-btn');
                  const inputFiber = input
                    ? Object.keys(input).find((k) => k.startsWith('__reactFiber$'))
                    : null;
                  const btnFiber = btn
                    ? Object.keys(btn).find((k) => k.startsWith('__reactFiber$'))
                    : null;
                  return !!(inputFiber || btnFiber);
                })()""",
                await_promise=False,
            )
            if hydrated is True:
                return
            if polls % 15 == 0 and reloads < 2:
                reloads += 1
                await self.cdp("Page.reload", {"ignoreCache": True}, recv_timeout=120.0)
                await asyncio.sleep(5)
                await self.ensure_dev_bridge(timeout_sec=min(30.0, deadline - time.monotonic()))
            await asyncio.sleep(2)

    async def dismiss_modals(self) -> None:
        await self.evaluate(DISMISS_MODALS_JS, await_promise=False)
        await asyncio.sleep(0.5)

    async def enable_goal_mode(self, *, budget_tokens: int = 50_000) -> dict[str, object]:
        await self.dismiss_modals()
        result = await self.evaluate(
            f"""(() => {{
              const bridge = window.__MYRM_E2E_CHAT__;
              if (!bridge?.setGoalMode || !bridge?.setGoalBudgetTokens) {{
                return {{ ok: false, err: 'no goal bridge' }};
              }}
              bridge.setGoalMode(true);
              bridge.setGoalBudgetTokens({int(budget_tokens)});
              return {{ ok: true, goalMode: bridge.getGoalMode?.() === true }};
            }})()""",
            await_promise=False,
        )
        return result if isinstance(result, dict) else {"ok": False, "probeError": result}

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

    async def _fill_ready_state(self, text: str) -> dict[str, object]:
        payload = json.dumps(text)
        result = await self.evaluate(
            f"""(() => {{
              const expected = {payload};
              const input = document.querySelector('[data-chat-input]');
              const btn = document.querySelector('.message-send-btn');
              const bridge = window.__MYRM_E2E_CHAT__;
              const bridgeMsg = (bridge?.getInputMessage?.() || '').trim();
              const domMsg = (input?.value || '').trim();
              const synced = bridgeMsg === expected.trim() || domMsg === expected.trim();
              return {{
                ok: synced && expected.trim().length > 0 && !btn?.disabled,
                inputLen: Math.max(bridgeMsg.length, domMsg.length),
                sendDisabled: !!btn?.disabled,
                bridgeSynced: bridgeMsg === expected.trim(),
                domSynced: domMsg === expected.trim(),
              }};
            }})()""",
            await_promise=False,
        )
        return result if isinstance(result, dict) else {"ok": False, "probeError": result}

    async def _await_fill_ready(self, text: str, *, timeout_sec: float = 45.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {"ok": False}
        while time.monotonic() < deadline:
            last = await self._fill_ready_state(text)
            if last.get("ok"):
                last["mode"] = "awaitFillReady"
                return last
            await asyncio.sleep(0.15)
        last["mode"] = "awaitFillReadyTimeout"
        return last

    async def ensure_dev_bridge(self, *, timeout_sec: float = 90.0) -> None:
        """Wait for React E2E bridge or install localhost fallback after hydration."""
        deadline = time.monotonic() + timeout_sec
        polls = 0
        while time.monotonic() < deadline:
            polls += 1
            await self.dismiss_modals()
            await self.evaluate(E2E_BRIDGE_INSTALL_JS, await_promise=False)
            probe = await self.evaluate(PAGE_PROBE_JS, await_promise=False)
            if isinstance(probe, dict) and probe.get("hasBridge") and probe.get("hasInput"):
                if probe.get("clientHydrated"):
                    return
            if polls in {15, 30, 45}:
                await self.cdp("Page.reload", {"ignoreCache": True}, recv_timeout=120.0)
                await asyncio.sleep(4)
            await asyncio.sleep(1)
        raise TimeoutError("Dev E2E chat bridge not available on WebUI")

    async def wait_dev_bridge(self, *, timeout_sec: float = 90.0) -> None:
        await self.ensure_dev_bridge(timeout_sec=timeout_sec)

    async def fill_input(self, text: str) -> dict[str, object]:
        await self.ensure_dev_bridge(timeout_sec=45.0)
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

        dev_bridge = await self.evaluate(
            f"""( () => {{
              const bridge = window.__MYRM_E2E_CHAT__;
              if (!bridge?.setInputMessage) {{
                return {{ ok: false, err: 'no dev bridge' }};
              }}
              bridge.setInputMessage({json.dumps(text)});
              return {{ ok: true, mode: 'devBridgeSet' }};
            }})()""",
            await_promise=False,
        )
        if isinstance(dev_bridge, dict) and dev_bridge.get("ok"):
            for _ in range(3):
                ready = await self._await_fill_ready(text, timeout_sec=45.0)
                if ready.get("ok"):
                    ready["mode"] = "devBridge"
                    return ready
                await self.evaluate(
                    f"""( () => {{
                      window.__MYRM_E2E_CHAT__?.setInputMessage?.({json.dumps(text)});
                      return {{ ok: true }};
                    }})()""",
                    await_promise=False,
                )
                await asyncio.sleep(1)

        native_fill = await self.evaluate(
            f"""( () => {{
              const input = document.querySelector('[data-chat-input]');
              if (!input) return {{ ok: false, err: 'no input' }};
              const text = {json.dumps(text)};
              input.focus();
              input.click();
              const proto = window.HTMLTextAreaElement.prototype;
              const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
              if (setter) {{
                setter.call(input, text);
              }} else {{
                input.value = text;
              }}
              input.dispatchEvent(new InputEvent('input', {{ bubbles: true, data: text, inputType: 'insertText' }}));
              input.dispatchEvent(new Event('change', {{ bubbles: true }}));
              return new Promise((resolve) => {{
                requestAnimationFrame(() => {{
                  requestAnimationFrame(() => {{
                    const btn = document.querySelector('.message-send-btn');
                    resolve({{
                      ok: (input.value || '').trim().length > 0 && !btn?.disabled,
                      inputLen: (input.value || '').length,
                      sendDisabled: !!btn?.disabled,
                      mode: 'nativeSetter+inputEvent',
                    }});
                  }});
                }});
              }});
            }})()""",
            await_promise=True,
        )
        if isinstance(native_fill, dict) and native_fill.get("ok"):
            return native_fill

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
            if exec_fill.get("ok"):
                return exec_fill
            if int(exec_fill.get("inputLen") or 0) > 0:
                ready = await self._await_fill_ready(text, timeout_sec=45.0)
                if ready.get("ok"):
                    ready["mode"] = f"{exec_fill.get('mode', 'execCommand')}+await"
                    return ready
            return exec_fill
        return {"ok": False, "probeError": exec_fill}

    async def _submit_started(self) -> dict[str, object]:
        result = await self.evaluate(
            """(() => {
              const main = document.querySelector('main');
              const sending = !!main?.querySelector('button[aria-label="Stop"]');
              const userMsgs = main?.querySelectorAll('[data-message-id]')?.length || 0;
              const input = document.querySelector('[data-chat-input]');
              const cleared = (input?.value || '').trim().length === 0;
              const bridgeEmpty = !(window.__MYRM_E2E_CHAT__?.getInputMessage?.() || '').trim();
              return { sending, userMsgs, cleared: cleared || bridgeEmpty };
            })()""",
            await_promise=False,
        )
        return result if isinstance(result, dict) else {"sending": False, "cleared": False, "userMsgs": 0}

    def _stream_started(self, started: dict[str, object]) -> bool:
        return bool(
            started.get("sending")
            or int(started.get("userMsgs") or 0) > 0
        )

    async def submit(self) -> dict[str, object]:
        dev_submit = await self.evaluate(
            """(() => {
              const bridge = window.__MYRM_E2E_CHAT__;
              if (!bridge?.handleSubmit) {
                return { ok: false, err: 'no dev bridge' };
              }
              return Promise.resolve(bridge.handleSubmit()).then(() => ({
                ok: true,
                mode: 'devBridgeSubmit',
              }));
            })()""",
            await_promise=True,
        )
        if isinstance(dev_submit, dict) and dev_submit.get("ok"):
            await asyncio.sleep(1.5)
            started = await self._submit_started()
            if self._stream_started(started):
                return dev_submit

        native = await self.evaluate(
            """(() => {
              const btn = document.querySelector('.message-send-btn');
              if (!btn) return { ok: false, err: 'no send button' };
              if (btn.disabled) return { ok: false, err: 'send disabled' };
              btn.click();
              return { ok: true, mode: 'nativeClick' };
            })()""",
            await_promise=False,
        )
        if isinstance(native, dict) and native.get("ok"):
            await asyncio.sleep(1.5)
            started = await self._submit_started()
            if self._stream_started(started):
                return native

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
        await asyncio.sleep(1.5)
        started = await self._submit_started()
        if started.get("sending") or started.get("cleared"):
            return {"ok": True, "mode": "enterKeyFallback"}
        return {"ok": False, "mode": "enterKeyFallback", "started": started}

    async def main_state(
        self,
        prompt: str,
        *,
        recv_timeout: float = 90.0,
    ) -> dict[str, object]:
        result = await self.evaluate(
            f"""( () => {{
              const main = document.querySelector('main');
              const text = main?.innerText || '';
              const userMsgs = main?.querySelectorAll('[data-message-id]')?.length || 0;
              const assistantNodes = Array.from(
                main?.querySelectorAll('[data-test-id="assistant-message"]') || [],
              );
              const assistantText = assistantNodes.map((el) => el.innerText || '').join('\\n');
              const sending = !!main?.querySelector('button[aria-label="Stop"]');
              const hasUserPrompt = userMsgs > 0 || text.includes({json.dumps(prompt)});
              const okInAssistant = /\\bOK\\b/i.test(assistantText);
              const okInMain =
                hasUserPrompt &&
                (okInAssistant ||
                  /\\bOK\\b/i.test(text) ||
                  /^\\s*OK\\s*$/m.test(text) ||
                  (text.includes('OK') && !sending));
              return {{
                url: location.href,
                path: location.pathname,
                userMsgs,
                sending,
                hasUserPrompt,
                okInMain,
                okInAssistant,
                sample: text.slice(0, 500),
                assistantSample: assistantText.slice(0, 300),
              }};
            }})()""",
            await_promise=False,
            recv_timeout=recv_timeout,
        )
        return result if isinstance(result, dict) else {"hasUserPrompt": False, "okInMain": False}

    async def wait_stream_started(self, prompt: str, *, timeout_sec: float = 180.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            try:
                last = await self.main_state(prompt)
            except TimeoutError:
                await asyncio.sleep(1)
                continue
            if (
                last.get("sending")
                or last.get("hasUserPrompt")
                or int(last.get("userMsgs") or 0) > 0
            ):
                return last
            chat_id = chat_id_from_path(str(last.get("path") or ""))
            if chat_id and chat_messages_have_ok(chat_id, min_user_count=1):
                return last
            await asyncio.sleep(0.75)
        raise TimeoutError(f"UI send did not start stream: {last}")

    async def wait_turn_done(
        self,
        prompt: str,
        *,
        chat_id_hint: str | None = None,
        min_user_msgs: int = 1,
        timeout_sec: float = 300.0,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            try:
                last = await self.main_state(prompt)
            except TimeoutError:
                await asyncio.sleep(2)
                continue
            chat_id = chat_id_from_path(str(last.get("path") or "")) or chat_id_hint
            if chat_id:
                try:
                    if chat_messages_have_ok(chat_id, min_user_count=min_user_msgs):
                        if not last.get("sending"):
                            last["chatId"] = chat_id
                            last["okViaApi"] = True
                            return last
                except OSError:
                    pass
            if last.get("sending"):
                await asyncio.sleep(1)
                continue
            if last.get("hasUserPrompt") and last.get("okInMain"):
                if chat_id:
                    last["chatId"] = chat_id
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
        await self.wait_dev_bridge()
        fill = await self.fill_input(text)
        if not fill.get("ok"):
            raise RuntimeError(f"UI fill failed: {fill}")
        submit = await self.submit()
        if not submit.get("ok"):
            raise RuntimeError(f"UI submit failed: {submit} fill={fill}")
        started = await self.wait_stream_started(prompt_for_wait)
        return {"fill": fill, "submit": submit, "started": started}


def chat_id_from_path(path: str) -> str | None:
    match = _CHAT_ID_PATH_RE.match(path.strip())
    return match.group(1) if match else None


def warmup_frontend(base_url: str, *, timeout_sec: float = 120.0) -> None:
    """Warm Next.js dev compile before CDP navigation (avoids hung first paint)."""
    deadline = time.monotonic() + timeout_sec
    last_error = "unknown"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base_url.rstrip("/") + "/", timeout=45) as resp:
                if resp.status == 200:
                    return
                last_error = f"HTTP {resp.status}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(3)
    raise TimeoutError(f"Frontend warmup failed within {timeout_sec:.0f}s: {last_error}")


def fetch_chat_messages(chat_id: str, *, api_url: str = API_URL) -> list[dict[str, object]]:
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}/api/v1/chats/{chat_id}/messages",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    messages = data.get("messages")
    return messages if isinstance(messages, list) else []


def chat_messages_have_ok(chat_id: str, *, min_user_count: int = 1, api_url: str = API_URL) -> bool:
    messages = fetch_chat_messages(chat_id, api_url=api_url)
    user_count = sum(1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user")
    if user_count < min_user_count:
        return False
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = str(msg.get("content") or "")
        if _OK_REPLY_RE.search(content):
            return True
    return False


@dataclass(frozen=True, slots=True)
class OwnedCdpPage:
    target_id: str
    websocket_url: str
    cdp_port: int


def create_owned_page(base_url: str, *, cdp_port: int = 9333) -> OwnedCdpPage:
    """Create and register a CDP page owned by the current process."""
    assert_cdp_write_allowed(operation="json/new")
    encoded = urllib.request.quote(base_url.rstrip("/") + "/", safe="")
    req = urllib.request.Request(
        f"http://127.0.0.1:{cdp_port}/json/new?{encoded}",
        method="PUT",
    )
    payload = json.loads(urllib.request.urlopen(req, timeout=15).read())
    target_id = payload.get("id")
    ws = payload.get("webSocketDebuggerUrl")
    if not isinstance(target_id, str) or not target_id:
        raise RuntimeError(f"CDP json/new missing target id: {payload!r}")
    if not isinstance(ws, str) or not ws.startswith("ws://"):
        raise RuntimeError(f"CDP json/new missing webSocketDebuggerUrl: {payload!r}")
    page_url = base_url.rstrip("/") + "/"
    register_target(target_id, page_url)
    return OwnedCdpPage(target_id=target_id, websocket_url=ws, cdp_port=cdp_port)


def close_owned_page(page: OwnedCdpPage) -> None:
    """Close only the exact target created by ``create_owned_page``."""
    if close_exact_target(page.cdp_port, page.target_id):
        unregister_target(page.target_id)


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
