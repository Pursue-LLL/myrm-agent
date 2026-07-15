"""Chat turn observation and completion workflow."""

from __future__ import annotations

import asyncio
import json
import time

from cdp_chat_submit import CdpChatSubmit
from cdp_chat_support import chat_id_from_path, chat_messages_have_ok, chat_user_message_count
from cdp_chat_support import (
    BRIDGE_TURN_SNAPSHOT_JS,
    PREPARE_AUTOMATION_SEND_JS,
    SELECT_FIRST_ENABLED_MODEL_JS,
    SELECT_MIMO_MODEL_JS,
)
from e2e_wave_ledger import maybe_register_e2e_chat


class CdpChatTurn(CdpChatSubmit):
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
              const okInAssistant = /(?:\bOK\b|GOAL_OK)/i.test(assistantText);
              const okInMain =
                hasUserPrompt &&
                (okInAssistant ||
                  /(?:\bOK\b|GOAL_OK)/i.test(text) ||
                  /^\\s*OK\\s*$/m.test(text) ||
                  (text.includes('OK') && !sending));
              return {{
                url: location.href,
                path: location.pathname,
                bridgeChatId: window.__MYRM_E2E_CHAT__?.debugProviderState?.()?.chatId ?? null,
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

    async def wait_stream_started(
        self,
        prompt: str,
        *,
        timeout_sec: float = 180.0,
        min_user_msgs: int = 1,
        chat_id_hint: str | None = None,
    ) -> dict[str, object]:
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
                or int(last.get("userMsgs") or 0) >= min_user_msgs
            ):
                return last
            chat_id = chat_id_hint or await self.resolve_chat_id(
                path=str(last.get("path") or ""),
                hint=str(last.get("bridgeChatId") or "").strip() or None,
            )
            if chat_id:
                try:
                    if chat_user_message_count(chat_id) >= min_user_msgs:
                        last["chatId"] = chat_id
                        last["okViaApi"] = True
                        return last
                except OSError:
                    pass
                if chat_messages_have_ok(chat_id, min_user_count=min_user_msgs):
                    return last
            await asyncio.sleep(0.75)
        raise TimeoutError(f"UI send did not start stream: {last}")

    async def _bridge_turn_snapshot(self) -> dict[str, object] | None:
        try:
            result = await self.evaluate(BRIDGE_TURN_SNAPSHOT_JS, await_promise=False, recv_timeout=8.0)
        except (RuntimeError, TimeoutError):
            return None
        return result if isinstance(result, dict) else None

    async def _finish_if_api_ok(
        self,
        chat_id: str,
        prompt: str,
        *,
        min_user_msgs: int,
    ) -> dict[str, object] | None:
        try:
            if not chat_messages_have_ok(chat_id, min_user_count=min_user_msgs):
                return None
        except OSError:
            return None
        maybe_register_e2e_chat(chat_id)
        return {
            "chatId": chat_id,
            "okViaApi": True,
            "okViaBridge": False,
        }

    async def wait_turn_done(
        self,
        prompt: str,
        *,
        chat_id_hint: str | None = None,
        min_user_msgs: int = 1,
        timeout_sec: float = 180.0,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}

        def _finish(chat_id: str, payload: dict[str, object]) -> dict[str, object]:
            payload["chatId"] = chat_id
            payload["okViaApi"] = payload.get("okViaApi", True)
            maybe_register_e2e_chat(chat_id)
            return payload

        if chat_id_hint:
            api_deadline = deadline
            while time.monotonic() < api_deadline:
                finished = await self._finish_if_api_ok(
                    chat_id_hint, prompt, min_user_msgs=min_user_msgs
                )
                if finished is not None:
                    return finished
                bridge = await self._bridge_turn_snapshot()
                if (
                    isinstance(bridge, dict)
                    and int(bridge.get("userCount") or 0) >= min_user_msgs
                    and bridge.get("hasOk")
                    and not bridge.get("isStreaming")
                ):
                    return _finish(
                        chat_id_hint,
                        {
                            **bridge,
                            "okViaBridge": True,
                            "okViaApi": False,
                        },
                    )
                await asyncio.sleep(1.5)

        while time.monotonic() < deadline:
            bridge = await self._bridge_turn_snapshot()
            if isinstance(bridge, dict):
                last = bridge
                chat_id = str(bridge.get("chatId") or "").strip() or chat_id_hint
                if (
                    chat_id
                    and int(bridge.get("userCount") or 0) >= min_user_msgs
                    and bridge.get("hasOk")
                    and not bridge.get("isStreaming")
                ):
                    return _finish(chat_id, {**bridge, "okViaBridge": True, "okViaApi": False})

            chat_id = chat_id_hint
            if not chat_id:
                try:
                    probe = await self.main_state(prompt, recv_timeout=8.0)
                    if isinstance(probe, dict):
                        last = probe
                        chat_id = await self.resolve_chat_id(
                            path=str(probe.get("path") or ""),
                            hint=str(probe.get("bridgeChatId") or "").strip() or None,
                        )
                except RuntimeError as exc:
                    message = str(exc)
                    if any(
                        token in message
                        for token in ("Target closed", "No page found", "detached Frame")
                    ):
                        await asyncio.sleep(1.5)
                        continue
                    raise
            if not chat_id:
                chat_id = await self.bridge_chat_id()
            if chat_id:
                finished = await self._finish_if_api_ok(
                    chat_id, prompt, min_user_msgs=min_user_msgs
                )
                if finished is not None:
                    return finished
            try:
                last = await self.main_state(prompt, recv_timeout=8.0)
            except RuntimeError as exc:
                message = str(exc)
                if any(
                    token in message
                    for token in ("Target closed", "No page found", "detached Frame")
                ):
                    await asyncio.sleep(1.5)
                    continue
                raise
            chat_id = await self.resolve_chat_id(
                path=str(last.get("path") or ""),
                hint=str(last.get("bridgeChatId") or "").strip() or chat_id_hint,
            )
            if last.get("sending"):
                await asyncio.sleep(1)
                continue
            if chat_id:
                finished = await self._finish_if_api_ok(
                    chat_id, prompt, min_user_msgs=min_user_msgs
                )
                if finished is not None:
                    return finished
            if last.get("hasUserPrompt") and last.get("okInMain"):
                if chat_id:
                    maybe_register_e2e_chat(chat_id)
                    last["chatId"] = chat_id
                return last
            await asyncio.sleep(1.5)
        raise TimeoutError(f"Timed out waiting for assistant OK: {last}")

    async def _clear_input_via_bridge(self) -> None:
        await self.evaluate(
            """(() => {
              window.__MYRM_E2E_CHAT__?.setInputMessage?.('');
              return { ok: true };
            })()""",
            await_promise=False,
            recv_timeout=8.0,
        )

    async def wait_input_empty(
        self,
        *,
        timeout_sec: float = 60.0,
        chat_id_hint: str | None = None,
    ) -> None:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            if chat_id_hint:
                try:
                    if chat_messages_have_ok(chat_id_hint, min_user_count=1):
                        await self._clear_input_via_bridge()
                        return
                except OSError:
                    pass
            bridge = await self._bridge_turn_snapshot()
            if (
                isinstance(bridge, dict)
                and not bridge.get("isStreaming")
                and (bridge.get("hasOk") or int(bridge.get("userCount") or 0) >= 1)
            ):
                await self._clear_input_via_bridge()
                probe = await self.send_state()
                if int(probe.get("inputLen") or 0) == 0:
                    return
            probe = await self.send_state()
            last = probe
            if not probe.get("sendDisabled") and int(probe.get("inputLen") or 0) == 0:
                return
            if not probe.get("sendDisabled") and int(probe.get("inputLen") or 0) > 0:
                await self._clear_input_via_bridge()
                probe = await self.send_state()
                if int(probe.get("inputLen") or 0) == 0:
                    return
            await asyncio.sleep(1)
        raise TimeoutError(f"Chat input not ready for send: {last}")

    async def _attach_chat_session(self, chat_id: str) -> None:
        payload = json.dumps(chat_id)
        result = await self.evaluate(
            f"""(() => {{
              const bridge = window.__MYRM_E2E_CHAT__;
              if (!bridge?.attachToChat) {{
                return {{ ok: false, err: 'no attachToChat' }};
              }}
              return Promise.resolve(bridge.attachToChat({payload})).then(() => ({{ ok: true }}));
            }})()""",
            await_promise=True,
            recv_timeout=45.0,
        )
        if not isinstance(result, dict) or not result.get("ok"):
            raise RuntimeError(f"E2E bridge attachToChat failed: {result}")

    async def _sync_model_selection(self, *, timeout_sec: float = 45.0) -> None:
        await self.ensure_e2e_api_base_binding()
        try:
            await self.evaluate(
                """(() => {
                  const bridge = window.__MYRM_E2E_CHAT__;
                  if (!bridge?.ensureProviders) return { ok: false };
                  bridge.prepareAutomationSend?.();
                  return bridge.ensureProviders().then(() => ({ ok: true }));
                })()""",
                await_promise=True,
                recv_timeout=timeout_sec,
            )
        except (RuntimeError, TimeoutError):
            pass
        for picker_js in (SELECT_MIMO_MODEL_JS, SELECT_FIRST_ENABLED_MODEL_JS):
            try:
                picked = await self.evaluate(
                    picker_js,
                    await_promise=True,
                    recv_timeout=12.0,
                )
            except TimeoutError:
                continue
            if isinstance(picked, dict) and picked.get("ok"):
                return

    async def send_message(
        self,
        text: str,
        prompt_for_wait: str,
        *,
        chat_id_hint: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, object]:
        ui_base = (base_url or getattr(self, "_base_url", None) or "http://127.0.0.1:3000").rstrip("/")
        baseline_user_msgs = 0
        chat_id = chat_id_hint
        await self.dismiss_modals()
        await self.wait_dev_bridge()
        await self.ensure_e2e_api_base_binding()
        if chat_id_hint:
            on_chat_page = False
            try:
                probe = await self.evaluate(
                    """(() => ({
                      path: location.pathname,
                    }))()""",
                    await_promise=False,
                    recv_timeout=10.0,
                )
                if isinstance(probe, dict):
                    on_chat_page = chat_id_from_path(str(probe.get("path") or "")) is not None
            except (RuntimeError, TimeoutError):
                on_chat_page = False
            if on_chat_page:
                await self.wait_shell_ready(timeout_sec=90.0, require_bridge=True)
            else:
                await self.navigate_to_chat(chat_id_hint, ui_base, timeout_sec=90.0)
        if not chat_id:
            chat_id = await self.bridge_chat_id()
        if chat_id:
            try:
                baseline_user_msgs = chat_user_message_count(chat_id)
            except OSError:
                baseline_user_msgs = 0
        self._baseline_user_msgs = baseline_user_msgs
        try:
            if baseline_user_msgs == 0:
                await self._sync_model_selection()
            else:
                await self.evaluate(PREPARE_AUTOMATION_SEND_JS, await_promise=False)
            if chat_id:
                await self._attach_chat_session(chat_id)
            else:
                await self.evaluate(
                    """(() => {
                      const bridge = window.__MYRM_E2E_CHAT__;
                      if (!bridge?.ensureChatSession) return { ok: false, err: 'no ensureChatSession' };
                      return Promise.resolve(bridge.ensureChatSession()).then(() => ({ ok: true }));
                    })()""",
                    await_promise=True,
                    recv_timeout=30.0,
                )
            await self._ensure_send_ready()
            fill = await self.fill_input(text)
            if not fill.get("ok"):
                raise RuntimeError(f"UI fill failed: {fill}")
            submit = await self.submit()
            if not submit.get("ok"):
                probe = await self.send_state()
                if chat_id:
                    try:
                        if chat_user_message_count(chat_id) > baseline_user_msgs:
                            submit = {
                                **submit,
                                "ok": True,
                                "mode": "apiConfirmedWithoutDom",
                                "chatId": chat_id,
                            }
                    except OSError:
                        pass
                if not submit.get("ok"):
                    if int(probe.get("inputLen") or 0) > 0:
                        raise RuntimeError(f"UI submit failed: {submit} fill={fill}")
                    if chat_id:
                        try:
                            if chat_user_message_count(chat_id) > baseline_user_msgs:
                                submit = {
                                    **submit,
                                    "ok": True,
                                    "mode": "apiConfirmedWithoutDom",
                                    "chatId": chat_id,
                                }
                        except OSError:
                            pass
                    if not submit.get("ok"):
                        raise RuntimeError(
                            f"UI submit failed without stream or API confirmation: {submit} fill={fill}"
                        )
            started: dict[str, object]
            try:
                started = await asyncio.wait_for(
                    self.wait_stream_started(
                        prompt_for_wait,
                        min_user_msgs=baseline_user_msgs + 1,
                        chat_id_hint=chat_id,
                    ),
                    timeout=45.0,
                )
            except TimeoutError:
                started = await self.main_state(prompt_for_wait)
                started["streamProbe"] = "deferred_to_wait_turn_done"
            if not chat_id:
                chat_id = await self.bridge_chat_id()
            if chat_id:
                started["chatId"] = chat_id
            confirmed = False
            if int(started.get("userMsgs") or 0) > baseline_user_msgs or started.get("sending"):
                confirmed = True
            if not confirmed and chat_id:
                try:
                    confirmed = chat_user_message_count(chat_id) > baseline_user_msgs
                except OSError:
                    confirmed = False
            if not confirmed:
                bridge = await self._bridge_turn_snapshot()
                if isinstance(bridge, dict) and int(bridge.get("userCount") or 0) > baseline_user_msgs:
                    confirmed = True
                elif not confirmed:
                    raise RuntimeError(
                        f"UI submit did not start stream: submit={submit} started={started} bridge={bridge}"
                    )
            return {"fill": fill, "submit": submit, "started": started}
        finally:
            self._baseline_user_msgs = 0

