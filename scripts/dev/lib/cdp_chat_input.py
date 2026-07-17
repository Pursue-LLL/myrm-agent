"""Chat input preparation and controlled React interaction workflow."""

from __future__ import annotations

import asyncio
import json
import sys
import time

from cdp_chat_bootstrap import CdpChatBootstrap
from cdp_chat_support import (
    E2E_BRIDGE_INSTALL_JS,
    MODEL_PROBE_JS,
    PAGE_PROBE_JS,
    SELECT_FIRST_ENABLED_MODEL_JS,
    SELECT_MIMO_MODEL_JS,
    _api_provider_ready,
    chat_id_from_path,
    chat_user_message_count,
    PREPARE_AUTOMATION_SEND_JS,
)


class CdpChatInput(CdpChatBootstrap):
    _baseline_user_msgs: int = 0

    async def _ensure_send_ready(self, *, timeout_sec: float = 90.0) -> dict[str, object]:
        """Prefer API readiness + E2E bridge over flaky model-picker UI automation."""
        if _api_provider_ready():
            try:
                await self.evaluate(
                    """(() => {
                      const bridge = window.__MYRM_E2E_CHAT__;
                      if (!bridge?.ensureProviders) return { ok: false, err: 'no ensureProviders' };
                      return Promise.resolve(bridge.ensureProviders()).then(() => ({ ok: true }));
                    })()""",
                    await_promise=True,
                    recv_timeout=min(timeout_sec, 60.0),
                )
            except (TimeoutError, RuntimeError):
                pass
            deadline = time.monotonic() + timeout_sec
            last: dict[str, object] = {"ok": False, "mode": "api-bypass"}
            while time.monotonic() < deadline:
                probe = await self.evaluate(
                    """(() => {
                      const bridge = window.__MYRM_E2E_CHAT__;
                      const btn = document.querySelector('.message-send-btn');
                      return {
                        sendReady: !!bridge?.isSendReady?.(),
                        sendDisabled: !!btn?.disabled,
                        providersInitialized: !!bridge?.isProvidersInitialized?.(),
                      };
                    })()""",
                    await_promise=False,
                )
                last = probe if isinstance(probe, dict) else {"ok": False, "probeError": probe}
                if last.get("sendReady"):
                    last["ok"] = True
                    return last
                for picker_js in (SELECT_MIMO_MODEL_JS, SELECT_FIRST_ENABLED_MODEL_JS):
                    try:
                        picked = await self.evaluate(
                            picker_js,
                            await_promise=True,
                            recv_timeout=10.0,
                        )
                    except TimeoutError:
                        continue
                    if isinstance(picked, dict) and picked.get("ok"):
                        await asyncio.sleep(0.5)
                        break
                await asyncio.sleep(0.5)
            debug = await self.evaluate(
                """(() => window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null)()""",
                await_promise=False,
            )
            if isinstance(debug, dict):
                last["debug"] = debug
            # API readiness can be true while the browser provider store is still empty
            # (common on isolated stacks). Fall back to UI model selection.
            return await self.ensure_model_ready(timeout_sec=timeout_sec)
        return await self.ensure_model_ready(timeout_sec=timeout_sec)

    async def ensure_model_ready(self, *, timeout_sec: float = 180.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {"ok": False}
        reloads = 0
        while time.monotonic() < deadline:
            probe = await self.evaluate(MODEL_PROBE_JS, await_promise=False)
            last = probe if isinstance(probe, dict) else {"ok": False, "probeError": probe}
            if last.get("ok"):
                return last
            if last.get("unconfigured"):
                picked_ok = False
                for picker_js in (SELECT_MIMO_MODEL_JS, SELECT_FIRST_ENABLED_MODEL_JS):
                    try:
                        picked = await self.evaluate(
                            picker_js,
                            await_promise=True,
                            recv_timeout=8.0,
                        )
                    except TimeoutError:
                        picked = {"ok": False, "err": "picker_timeout"}
                    if isinstance(picked, dict) and picked.get("ok"):
                        await asyncio.sleep(1.0)
                        picked_ok = True
                        break
                if not picked_ok and reloads < 2:
                    reloads += 1
                    await self.cdp("Page.reload", {"ignoreCache": True}, recv_timeout=120.0)
                    await asyncio.sleep(4)
                    await self.ensure_dev_bridge(timeout_sec=45.0)
            await asyncio.sleep(1)
        raise TimeoutError(f"Model not ready for chat send: {last}")

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
              const bridgeSynced = bridgeMsg === expected.trim();
              const domSynced = domMsg === expected.trim();
              const bridgeReady = !!bridge?.isSendReady?.();
              const providersReady = !!bridge?.isProvidersInitialized?.();
              const sendEnabled = !btn?.disabled;
              const ok = expected.trim().length > 0 && (
                (bridgeSynced && (bridgeReady || providersReady)) ||
                (domSynced && sendEnabled)
              );
              return {{
                ok,
                inputLen: Math.max(bridgeMsg.length, domMsg.length),
                sendDisabled: !!btn?.disabled,
                bridgeSynced,
                domSynced,
                bridgeReady,
                providersReady,
              }};
            }})()""",
            await_promise=False,
        )
        return result if isinstance(result, dict) else {"ok": False, "probeError": result}

    async def _await_fill_ready(self, text: str, *, timeout_sec: float = 45.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {"ok": False}
        while time.monotonic() < deadline:
            await self.evaluate(PREPARE_AUTOMATION_SEND_JS, await_promise=False)
            last = await self._fill_ready_state(text)
            if last.get("ok"):
                last["mode"] = "awaitFillReady"
                return last
            await asyncio.sleep(0.15)
        last["mode"] = "awaitFillReadyTimeout"
        return last

    async def ensure_dev_bridge(self, *, timeout_sec: float = 90.0, allow_reload: bool = True) -> None:
        """Wait for React E2E bridge or install localhost fallback after hydration."""
        deadline = time.monotonic() + timeout_sec
        polls = 0
        while time.monotonic() < deadline:
            polls += 1
            await self.dismiss_modals()
            await self.ensure_e2e_api_base_binding()
            await self.evaluate(E2E_BRIDGE_INSTALL_JS, await_promise=False)
            probe = await self.evaluate(PAGE_PROBE_JS, await_promise=False)
            if isinstance(probe, dict) and probe.get("hasBridge") and probe.get("clientHydrated"):
                return
            if isinstance(probe, dict) and probe.get("hasBridge") and probe.get("hasInput"):
                if probe.get("clientHydrated"):
                    return
            if allow_reload and polls in {15, 30, 45}:
                await self.cdp("Page.reload", {"ignoreCache": True}, recv_timeout=120.0)
                await asyncio.sleep(4)
            await asyncio.sleep(1)
        raise TimeoutError("Dev E2E chat bridge not available on WebUI")

    async def wait_dev_bridge(self, *, timeout_sec: float = 90.0) -> None:
        await self.ensure_dev_bridge(timeout_sec=timeout_sec)

    async def _retry_bridge_fill(self, text: str, *, timeout_sec: float = 120.0) -> dict[str, object]:
        """When the React E2E bridge exists, never rely on DOM-only fill fallbacks."""
        payload = json.dumps(text)
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {"ok": False, "mode": "bridgeRetry"}
        while time.monotonic() < deadline:
            await self.ensure_e2e_api_base_binding()
            await self.evaluate(E2E_BRIDGE_INSTALL_JS, await_promise=False)
            try:
                await self.evaluate(
                    """(() => {
                      const bridge = window.__MYRM_E2E_CHAT__;
                      if (!bridge?.ensureProviders) return { ok: false, err: 'no ensureProviders' };
                      return Promise.resolve(bridge.ensureProviders()).then(() => ({ ok: true }));
                    })()""",
                    await_promise=True,
                    recv_timeout=60.0,
                )
            except (TimeoutError, RuntimeError):
                pass
            await self.evaluate(PREPARE_AUTOMATION_SEND_JS, await_promise=False)
            await self.evaluate(
                f"""( () => {{
                  const bridge = window.__MYRM_E2E_CHAT__;
                  if (!bridge?.setInputMessage) {{
                    return {{ ok: false, err: 'no dev bridge' }};
                  }}
                  bridge.setInputMessage({payload});
                  return {{ ok: true, mode: 'devBridgeSet' }};
                }})()""",
                await_promise=False,
            )
            last = await self._await_fill_ready(text, timeout_sec=5.0)
            if last.get("ok"):
                last["mode"] = "devBridgeRetry"
                return last
            await asyncio.sleep(1.0)
        debug = await self.evaluate(
            """(() => window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null)()""",
            await_promise=False,
        )
        if isinstance(debug, dict):
            last["debug"] = debug
        return last

    async def fill_input(self, text: str) -> dict[str, object]:
        await self.ensure_dev_bridge(timeout_sec=90.0, allow_reload=True)
        await self.evaluate(PREPARE_AUTOMATION_SEND_JS, await_promise=False)

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

        bridge_probe = await self.evaluate(
            """(() => ({
              hasBridge: !!window.__MYRM_E2E_CHAT__?.setInputMessage,
            }))()""",
            await_promise=False,
        )
        if isinstance(bridge_probe, dict) and bridge_probe.get("hasBridge"):
            bridge_fill = await self._retry_bridge_fill(text, timeout_sec=120.0)
            if bridge_fill.get("ok"):
                return bridge_fill
            raise RuntimeError(f"E2E bridge fill failed: {bridge_fill}")

        focus: dict[str, object] = {"ok": False, "err": "no input"}
        for _ in range(12):
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
            if not (isinstance(dev_bridge, dict) and dev_bridge.get("ok")):
                raise RuntimeError(f"Focus input failed: {focus}")

        dev_bridge_retry = await self.evaluate(
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
        if isinstance(dev_bridge_retry, dict) and dev_bridge_retry.get("ok"):
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
        if isinstance(native_fill, dict) and int(native_fill.get("inputLen") or 0) > 0:
            await self._ensure_send_ready(timeout_sec=45.0)
            ready = await self._await_fill_ready(text, timeout_sec=45.0)
            if ready.get("ok"):
                ready["mode"] = f"{native_fill.get('mode', 'nativeSetter')}+await"
                return ready

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
        if isinstance(react_fill, dict) and int(react_fill.get("inputLen") or 0) > 0:
            await self._ensure_send_ready(timeout_sec=45.0)
            ready = await self._await_fill_ready(text, timeout_sec=45.0)
            if ready.get("ok"):
                ready["mode"] = f"{react_fill.get('mode', 'react-onChange')}+await"
                return ready

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
              const bridgeChatId = window.__MYRM_E2E_CHAT__?.debugProviderState?.()?.chatId ?? null;
              return {
                sending,
                userMsgs,
                cleared: cleared || bridgeEmpty,
                path: location.pathname,
                bridgeChatId,
              };
            })()""",
            await_promise=False,
        )
        return result if isinstance(result, dict) else {"sending": False, "cleared": False, "userMsgs": 0}

    async def _stream_started(self, started: dict[str, object]) -> bool:
        baseline_user_msgs = int(getattr(self, "_baseline_user_msgs", 0) or 0)
        path = str(started.get("path") or "")
        if started.get("sending") or int(started.get("userMsgs") or 0) > baseline_user_msgs:
            return True
        chat_id = chat_id_from_path(path) or str(started.get("bridgeChatId") or "").strip() or None
        if not chat_id:
            chat_id = await self.bridge_chat_id()
        if chat_id:
            try:
                if chat_user_message_count(chat_id) > baseline_user_msgs:
                    return True
            except OSError:
                pass
        return False
