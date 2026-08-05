"""Chat turn observation and completion workflow."""

from __future__ import annotations

import asyncio
import json
import time

import cdp_chat_support
from cdp_chat_submit import CdpChatSubmit
from cdp_chat_support import (
    BRIDGE_TURN_SNAPSHOT_JS,
    PREPARE_AUTOMATION_SEND_JS,
    SELECT_FIRST_ENABLED_MODEL_JS,
    SELECT_MIMO_MODEL_JS,
    WAIT_WORKSPACE_STREAM_JS,
    chat_id_from_path,
    chat_messages_have_ok,
    fetch_provider_readiness_snapshot,
)
from e2e_wave_ledger import maybe_register_e2e_chat
from send_turn_contract import SendTurnError, SendTurnPhase, is_live_send_turn_profile


def _bridge_has_completion(bridge: dict[str, object]) -> bool:
    """Unified completion signal check: hasCompletionSignal (SSOT) with hasOk/hasDone fallback."""
    return bool(
        bridge.get("hasCompletionSignal")
        or bridge.get("hasOk")
        or bridge.get("hasDone")
    )


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
              const bridgeUsers = window.__MYRM_E2E_CHAT__?.turnSnapshot?.().userCount;
              const assistantCount =
                main?.querySelectorAll('[data-test-id="assistant-message"]')?.length || 0;
              const allWithId = main?.querySelectorAll('[data-message-id]')?.length || 0;
              const domUsers = Math.max(0, allWithId - assistantCount);
              const userMsgs =
                typeof bridgeUsers === 'number' && bridgeUsers >= 0 ? bridgeUsers : domUsers;
              const assistantNodes = Array.from(
                main?.querySelectorAll('[data-test-id="assistant-message"]') || [],
              );
              const assistantText = assistantNodes.map((el) => el.innerText || '').join('\\n');
              const sending = !!main?.querySelector('button[aria-label="Stop"]');
              const hasUserPrompt = userMsgs > 0 || text.includes({json.dumps(prompt)});
              const okInAssistant = /(?:\bOK\b|GOAL_OK|\bDONE\b)/i.test(assistantText);
              const okInMain =
                hasUserPrompt &&
                (okInAssistant ||
                  /(?:\bOK\b|GOAL_OK|\bDONE\b)/i.test(text) ||
                  /^\\s*(?:OK|DONE)\\s*$/m.test(text) ||
                  ((text.includes('OK') || text.includes('DONE')) && !sending));
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
        return (
            result
            if isinstance(result, dict)
            else {"hasUserPrompt": False, "okInMain": False}
        )

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
                bridge_id = str(last.get("bridgeChatId") or "").strip()
                ui_progress = bool(
                    last.get("sending")
                    or int(last.get("userMsgs") or 0) >= min_user_msgs
                )
                try:
                    api_ok = (
                        cdp_chat_support.chat_user_message_count(chat_id)
                        >= min_user_msgs
                    )
                except OSError:
                    api_ok = False
                if api_ok and bridge_id == chat_id:
                    if not is_live_send_turn_profile() and ui_progress:
                        last["chatId"] = chat_id
                        last["okViaApi"] = True
                        return last
                try:
                    if chat_messages_have_ok(chat_id, min_user_count=min_user_msgs):
                        if is_live_send_turn_profile():
                            bridge_turn = await self._bridge_turn_snapshot()
                            if isinstance(bridge_turn, dict):
                                ui_users = int(bridge_turn.get("userCount") or 0)
                                ui_streaming = bridge_turn.get("isStreaming") is True
                                if ui_users >= min_user_msgs or ui_streaming:
                                    last["chatId"] = chat_id
                                    last["okViaUiTurn"] = True
                                    return last
                        else:
                            return last
                except OSError:
                    pass
            await asyncio.sleep(0.75)
        raise TimeoutError(f"UI send did not start stream: {last}")

    async def _bridge_turn_snapshot(self) -> dict[str, object] | None:
        try:
            result = await self.evaluate(
                BRIDGE_TURN_SNAPSHOT_JS, await_promise=False, recv_timeout=8.0
            )
        except (RuntimeError, TimeoutError):
            return None
        return result if isinstance(result, dict) else None

    async def _best_effort_user_message_count(
        self,
        chat_id: str,
        *,
        timeout_sec: float = 4.0,
        max_attempts: int = 1,
        wall_timeout_sec: float = 6.0,
    ) -> int:
        normalized = chat_id.strip()
        if not normalized:
            return 0
        try:
            count = await asyncio.wait_for(
                asyncio.to_thread(
                    cdp_chat_support.chat_user_message_count,
                    normalized,
                    timeout_sec=timeout_sec,
                    max_attempts=max_attempts,
                ),
                timeout=wall_timeout_sec,
            )
        except (TimeoutError, OSError, ValueError):
            return 0
        return max(0, int(count))

    async def _finish_if_api_ok(
        self,
        chat_id: str,
        prompt: str,
        *,
        min_user_msgs: int,
    ) -> dict[str, object] | None:
        if is_live_send_turn_profile():
            return None
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
            if is_live_send_turn_profile() and bool(payload.get("okViaApi")):
                raise SendTurnError(
                    SendTurnPhase.OBSERVE,
                    "okViaApi completion forbidden in LIVE profile",
                )
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
                    and _bridge_has_completion(bridge)
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
                    and _bridge_has_completion(bridge)
                    and not bridge.get("isStreaming")
                ):
                    return _finish(
                        chat_id, {**bridge, "okViaBridge": True, "okViaApi": False}
                    )

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
                        for token in (
                            "Target closed",
                            "No page found",
                            "detached Frame",
                        )
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

    async def wait_turn_settled(
        self,
        *,
        chat_id_hint: str | None = None,
        min_user_msgs: int = 1,
        timeout_sec: float = 180.0,
    ) -> dict[str, object]:
        """Wait until the assistant finishes without requiring an OK token."""
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            bridge = await self._bridge_turn_snapshot()
            if isinstance(bridge, dict):
                last = bridge
                chat_id = str(bridge.get("chatId") or "").strip() or chat_id_hint
                if (
                    chat_id
                    and int(bridge.get("userCount") or 0) >= min_user_msgs
                    and not bridge.get("isStreaming")
                    and str(bridge.get("lastAssistantSample") or "").strip()
                ):
                    maybe_register_e2e_chat(chat_id)
                    return {**bridge, "chatId": chat_id, "okViaBridge": True}
            await asyncio.sleep(1.5)
        raise TimeoutError(f"Timed out waiting for assistant reply: {last}")

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
                and (
                    _bridge_has_completion(bridge)
                    or int(bridge.get("userCount") or 0) >= 1
                )
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
        last: object = {"ok": False}
        ui_base = (getattr(self, "_base_url", None) or "http://127.0.0.1:3000").rstrip(
            "/"
        )
        for attempt in range(12):
            await self.ensure_e2e_api_base_binding()
            bridge_probe = await self.evaluate(
                """(() => ({
                  hasAttach: typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function',
                  fallback: window.__MYRM_E2E_CHAT__?.__e2eFallback === true,
                }))()""",
                await_promise=False,
            )
            if isinstance(bridge_probe, dict) and not bridge_probe.get("hasAttach"):
                try:
                    await self.ensure_react_e2e_bridge(
                        timeout_sec=min(45.0, 15.0 + attempt * 3)
                    )
                except TimeoutError:
                    await self.navigate_to_chat(
                        chat_id,
                        ui_base,
                        timeout_sec=90.0,
                    )
                    continue
            attach_recv_timeout = 60.0
            try:
                from cdp_chat_support import signoff_parallel_force_chat_timeout_sec

                attach_recv_timeout = signoff_parallel_force_chat_timeout_sec(120.0)
            except ImportError:
                pass
            try:
                result = await self.evaluate(
                    f"""(() => {{
                      const bridge = window.__MYRM_E2E_CHAT__;
                      if (!bridge?.attachToChat) {{
                        return {{ ok: false, err: 'no attachToChat' }};
                      }}
                      return Promise.resolve(bridge.attachToChat({payload}))
                        .then(() => ({{ ok: true }}))
                        .catch((err) => ({{ ok: false, err: String(err) }}));
                    }})()""",
                    await_promise=True,
                    recv_timeout=attach_recv_timeout,
                )
            except RuntimeError as exc:
                message = str(exc)
                if attempt < 11 and (
                    "e2e-private-backend-not-ready" in message
                    or "attach-timeout" in message
                ):
                    if "attach-timeout" in message:
                        await self.navigate_to_chat(
                            chat_id, ui_base, timeout_sec=90.0
                        )
                    await asyncio.sleep(2.0 + attempt)
                    continue
                raise
            last = result
            if isinstance(result, dict) and result.get("ok"):
                return
            err_text = str(result.get("err") or "") if isinstance(result, dict) else ""
            if isinstance(result, dict) and result.get("err") == "no attachToChat":
                await self.navigate_to_chat(chat_id, ui_base, timeout_sec=90.0)
                await asyncio.sleep(1.0)
                continue
            if "attach-timeout" in err_text and attempt < 11:
                await self.navigate_to_chat(chat_id, ui_base, timeout_sec=90.0)
                await asyncio.sleep(2.0 + attempt)
                continue
            await asyncio.sleep(1.0 + attempt)
        raise RuntimeError(f"E2E bridge attachToChat failed: {last}")

    async def fast_desktop_agent_submit(
        self,
        text: str,
        prompt_for_wait: str,
        *,
        chat_id_hint: str | None = None,
        baseline_user_msgs_hint: int | None = None,
        wait_stream_started: bool = True,
    ) -> dict[str, object]:
        """Desktop approval E2E: setInputMessage + nativeClick (matches v48 PASS path)."""
        chat_id = chat_id_hint
        baseline_user_msgs = (
            max(0, int(baseline_user_msgs_hint))
            if baseline_user_msgs_hint is not None
            else 0
        )
        if baseline_user_msgs_hint is None and chat_id:
            baseline_user_msgs = await self._best_effort_user_message_count(chat_id)
        from cdp_chat_support import signoff_parallel_desktop_mux_step_timeout_sec

        bridge_timeout = signoff_parallel_desktop_mux_step_timeout_sec(60.0)
        await self.ensure_react_e2e_bridge(timeout_sec=bridge_timeout)
        if chat_id:
            await self._attach_chat_session(chat_id)
        await self.evaluate(PREPARE_AUTOMATION_SEND_JS, await_promise=False)
        await self.evaluate(
            f"""(() => {{
              const bridge = window.__MYRM_E2E_CHAT__;
              bridge?.setInputMessage?.({json.dumps(text)});
              return {{ ok: true, inputLen: {len(text)} }};
            }})()""",
            await_promise=False,
        )
        submit = await self.submit_native_click()
        recoverable_submit_errors = {"no send button", "send disabled"}
        submit_err = str(submit.get("err") or "")
        submit_probe = (
            submit.get("probe") if isinstance(submit.get("probe"), dict) else {}
        )
        send_ready_no_button = bool(
            isinstance(submit_probe, dict)
            and submit_probe.get("sendReady")
            and not submit_probe.get("hasBtn")
        )
        # In shared-hot retries the DOM button can disappear while bridge send is ready.
        # Prefer bridge submit first to avoid expensive chat-surface re-hydration loops.
        if (
            not submit.get("ok")
            and submit_err in recoverable_submit_errors
            and send_ready_no_button
        ):
            bridge_submit = await self._submit_via_dev_bridge(
                text,
                baseline_user_msgs=baseline_user_msgs,
            )
            if bridge_submit.get("ok"):
                submit = {**bridge_submit, "mode": "bridgeSendChatMessage"}
        if (
            not submit.get("ok")
            and str(submit.get("err") or "") in recoverable_submit_errors
        ):
            ui_base = (
                getattr(self, "_base_url", None) or "http://127.0.0.1:3000"
            ).rstrip("/")
            await self.ensure_chat_surface(ui_base, timeout_sec=30.0)
            if chat_id:
                try:
                    await asyncio.wait_for(
                        self._attach_chat_session(chat_id), timeout=30.0
                    )
                except TimeoutError:
                    pass
            await self.evaluate(PREPARE_AUTOMATION_SEND_JS, await_promise=False)
            await self.evaluate(
                f"""(() => {{
                  const bridge = window.__MYRM_E2E_CHAT__;
                  bridge?.setInputMessage?.({json.dumps(text)});
                  return {{ ok: true, inputLen: {len(text)} }};
                }})()""",
                await_promise=False,
            )
            submit = await self.submit_native_click()
        if (
            not submit.get("ok")
            and str(submit.get("err") or "") in recoverable_submit_errors
        ):
            bridge_submit = await self._submit_via_dev_bridge(
                text,
                baseline_user_msgs=baseline_user_msgs,
            )
            if bridge_submit.get("ok"):
                submit = {**bridge_submit, "mode": "bridgeSendChatMessage"}
        if not submit.get("ok"):
            raise RuntimeError(f"fast desktop native submit failed: {submit}")
        if wait_stream_started:
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
        else:
            started = {
                "streamProbe": "skipped_for_follow_up_nudge",
                "userMsgs": baseline_user_msgs,
            }
        if chat_id:
            started["chatId"] = chat_id
        return {
            "fill": {"ok": True, "mode": "fastNative", "inputLen": len(text)},
            "submit": submit,
            "started": started,
        }

    async def submit_desktop_nudge(
        self,
        text: str,
        *,
        chat_id_hint: str | None = None,
    ) -> dict[str, object]:
        """Follow-up after desktop_snapshot; steer when agent stream is still active."""
        chat_id = chat_id_hint
        baseline_user_msgs = 0
        if chat_id:
            baseline_user_msgs = await self._best_effort_user_message_count(chat_id)
        if chat_id:
            try:
                api_steer = await asyncio.to_thread(
                    cdp_chat_support.steer_chat_message,
                    chat_id,
                    text,
                )
            except OSError as exc:
                api_steer = {"ok": False, "err": str(exc)}
            if isinstance(api_steer, dict) and api_steer.get("ok"):
                return {"submit": api_steer, "mode": "steerApi"}
        await self.ensure_react_e2e_bridge(timeout_sec=20.0)
        payload = json.dumps(text)
        bridge_steer = await self.evaluate(
            f"""(async () => {{
              const bridge = window.__MYRM_E2E_CHAT__;
              if (typeof bridge?.submitSteerNudge !== 'function') {{
                return {{ ok: false, err: 'no-submitSteerNudge' }};
              }}
              return await bridge.submitSteerNudge({payload});
            }})()""",
            await_promise=True,
        )
        if isinstance(bridge_steer, dict) and bridge_steer.get("ok"):
            return {
                "submit": bridge_steer,
                "mode": str(bridge_steer.get("mode", "steerBridge")),
            }
        ui_base = (getattr(self, "_base_url", None) or "http://127.0.0.1:3000").rstrip(
            "/"
        )
        if chat_id:
            chat_target = f"{ui_base}/chat/{chat_id}"
            on_chat = await self.evaluate(
                f"""(() => {{
                  const href = String(location.href || '');
                  return {{ onChat: href.startsWith({chat_target!r}) }};
                }})()""",
                await_promise=False,
            )
            if not (isinstance(on_chat, dict) and on_chat.get("onChat")):
                await asyncio.to_thread(
                    self._client.navigate,
                    self._page,
                    chat_target,
                    timeout_ms=120_000,
                )
                await self.ensure_react_e2e_bridge(timeout_sec=20.0)
                await self.evaluate(PREPARE_AUTOMATION_SEND_JS, await_promise=False)
                await self.evaluate(
                    f"""(() => {{
                      window.__MYRM_E2E_CHAT__?.setInputMessage?.({payload});
                      return {{ ok: true, inputLen: {len(text)} }};
                    }})()""",
                    await_promise=False,
                )
                steer = await self.evaluate(
                    """(() => {
                      const buttons = [...document.querySelectorAll('button[aria-label]')];
                      const steerBtn = buttons.find((btn) => {
                        const label = String(btn.getAttribute('aria-label') || '').toLowerCase();
                        return (
                          label.includes('steer')
                          || label.includes('guidance')
                          || label.includes('转向')
                          || label.includes('指导')
                        );
                      });
                      if (steerBtn && !steerBtn.disabled) {
                        steerBtn.click();
                        return { ok: true, mode: 'steerClick' };
                      }
                      return { ok: false, err: 'no-steer-button' };
                    })()""",
                    await_promise=False,
                )
                if isinstance(steer, dict) and steer.get("ok"):
                    return {"submit": steer, "mode": "steerClick"}
            try:
                await asyncio.wait_for(self._attach_chat_session(chat_id), timeout=15.0)
            except TimeoutError:
                pass
        await self.ensure_chat_surface(ui_base, timeout_sec=30.0)
        if chat_id:
            try:
                await asyncio.wait_for(self._attach_chat_session(chat_id), timeout=30.0)
            except TimeoutError:
                pass
        await self.evaluate(
            """(() => {
              const bridge = window.__MYRM_E2E_CHAT__;
              bridge?.abortActiveStream?.();
              bridge?.releaseActiveStreamForApiResume?.();
              bridge?.prepareAutomationSend?.();
              bridge?.clearStreamRequestMessageId?.();
              return { ok: true };
            })()""",
            await_promise=False,
        )
        for _ in range(40):
            snap = await self.evaluate(BRIDGE_TURN_SNAPSHOT_JS, await_promise=False)
            if isinstance(snap, dict) and not snap.get("isStreaming"):
                break
            await asyncio.sleep(0.5)
        await self.evaluate(
            f"""(() => {{
              window.__MYRM_E2E_CHAT__?.setInputMessage?.({payload});
              return {{ ok: true, inputLen: {len(text)} }};
            }})()""",
            await_promise=False,
        )
        for _ in range(40):
            probe = await self.evaluate(
                """(() => {
                  const btn = document.querySelector('.message-send-btn');
                  return {
                    hasBtn: Boolean(btn),
                    disabled: btn ? Boolean(btn.disabled) : true,
                    sendReady: !!window.__MYRM_E2E_CHAT__?.isSendReady?.(),
                  };
                })()""",
                await_promise=False,
            )
            if (
                isinstance(probe, dict)
                and probe.get("hasBtn")
                and not probe.get("disabled")
            ):
                break
            await asyncio.sleep(0.5)
        submit = await self.send_chat_message_atomic(
            text,
            baseline_user_msgs=baseline_user_msgs,
        )
        if not submit.get("ok"):
            submit = await self.submit_native_click()
        if not submit.get("ok"):
            raise RuntimeError(f"desktop nudge submit failed: {submit}")
        return {"submit": submit, "mode": submit.get("mode", "nudge")}

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
        ui_base = (
            base_url or getattr(self, "_base_url", None) or "http://127.0.0.1:3000"
        ).rstrip("/")
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
                    on_chat_page = (
                        chat_id_from_path(str(probe.get("path") or "")) is not None
                    )
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
                baseline_user_msgs = cdp_chat_support.chat_user_message_count(chat_id)
            except OSError:
                baseline_user_msgs = 0
        self._baseline_user_msgs = baseline_user_msgs
        try:
            if baseline_user_msgs == 0:
                await self._sync_model_selection()
            else:
                await self.evaluate(PREPARE_AUTOMATION_SEND_JS, await_promise=False)
            if chat_id:
                await self.ensure_react_e2e_bridge(timeout_sec=60.0)
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
            ready = await self._ensure_send_ready()
            if baseline_user_msgs > 0:
                await self.evaluate(
                    """(() => {
                      const bridge = window.__MYRM_E2E_CHAT__;
                      if (typeof bridge?.clearStreamRequestMessageId === 'function') {
                        bridge.clearStreamRequestMessageId();
                        return { ok: true, mode: 'cleared-stream-request-id' };
                      }
                      return { ok: false, mode: 'no-clear-hook' };
                    })()""",
                    await_promise=False,
                    recv_timeout=10.0,
                )
            send_probe = await self.evaluate(
                """(() => ({
                  sendReady: !!window.__MYRM_E2E_CHAT__?.isSendReady?.(),
                  path: location.pathname,
                }))()""",
                await_promise=False,
            )
            if not isinstance(send_probe, dict) or not send_probe.get("sendReady"):
                debug = await self.evaluate(
                    """(() => window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null)()""",
                    await_promise=False,
                )
                raise RuntimeError(
                    f"E2E send not ready before submit: ready={ready} probe={send_probe} debug={debug}"
                )
            fill = {"ok": True, "mode": "sendTurnContract", "inputLen": len(text)}
            if is_live_send_turn_profile():
                workspace_ready = await self.evaluate(
                    WAIT_WORKSPACE_STREAM_JS,
                    await_promise=True,
                    recv_timeout=35.0,
                )
                if not isinstance(workspace_ready, dict) or not workspace_ready.get(
                    "ok"
                ):
                    raise RuntimeError(
                        f"SendTurnContract workspace stream not ready: {workspace_ready!r}"
                    )
                send_rev = await self.evaluate(
                    """(() => ({
                      rev: window.__MYRM_E2E_SEND_TURN_REV__
                        ?? window.__MYRM_E2E_CHAT__?.sendTurnRev?.()
                        ?? 'unknown',
                    }))()""",
                    await_promise=False,
                )
                if isinstance(send_rev, dict):
                    print(
                        f"E2E_SEND_TURN: rev={send_rev.get('rev')}",
                        flush=True,
                    )
            try:
                submit = await self.send_chat_message_atomic(
                    text,
                    baseline_user_msgs=baseline_user_msgs,
                )
            except SendTurnError as exc:
                raise RuntimeError(
                    f"SendTurnContract failed phase={exc.phase.value}: {exc}"
                ) from exc
            except RuntimeError as exc:
                if any(
                    token in str(exc)
                    for token in ("Target closed", "No page found", "detached Frame")
                ):
                    raise RuntimeError(
                        f"SendTurnContract transport error: {exc}"
                    ) from exc
                raise
            if not submit.get("ok"):
                raise RuntimeError(
                    f"SendTurnContract submit failed: {submit} fill={fill}"
                )
            submit_mode = str(submit.get("mode") or "")
            if submit_mode != "sendTurnSealed":
                raise RuntimeError(
                    f"SendTurnContract expected sendTurnSealed, got: {submit}"
                )
            sealed_chat_id = str(
                submit.get("chatId") or chat_id or (await self.bridge_chat_id()) or ""
            ).strip()
            if not sealed_chat_id:
                raise RuntimeError(
                    f"SendTurnContract missing chatId after submit: {submit}"
                )
            chat_id = sealed_chat_id
            debug = submit.get("debug")
            started: dict[str, object] = {
                "chatId": chat_id,
                "sendTurnMode": submit_mode,
                "okViaSendTurn": True,
            }
            if isinstance(debug, dict):
                started["userMsgs"] = debug.get("userCount")
                started["sending"] = debug.get("streaming")
            return {"fill": fill, "submit": submit, "started": started}
        finally:
            self._baseline_user_msgs = 0
