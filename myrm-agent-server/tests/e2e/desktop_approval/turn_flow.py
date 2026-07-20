"""Post-approval turn completion and settings revoke for desktop E2E."""

from __future__ import annotations

import asyncio
import platform
import subprocess

import pytest
from cdp_chat_support import chat_id_from_path, chat_messages_have_done, chat_user_message_count, get_e2e_api_url
from mcp_chat_ui import McpChatSession

from tests.e2e.desktop_approval.constants import APPROVAL_WAIT_SEC, BASE_URL, E2E_PROMPT, progress
from tests.e2e.desktop_approval.gate_probe import ensure_interact_gate, require_approval_gate_triggered
from tests.e2e.desktop_approval.textedit_fixture import ensure_textedit_fixture_ready
from tests.e2e.desktop_approval.trust_api import list_trusted_apps_via_api, server_pending_approval_count
from tests.support.e2e_runtime_guard import heartbeat_e2e_lease


def activate_chrome() -> None:
    if platform.system() != "Darwin":
        return
    subprocess.run(
        ["osascript", "-e", 'tell application "Google Chrome" to activate'],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


async def resolve_chat_id(chat: McpChatSession, state: dict[str, object]) -> str | None:
    chat_id = chat_id_from_path(str(state.get("url") or ""))
    if chat_id:
        return chat_id
    explicit = str(state.get("chatId") or "").strip()
    if explicit:
        return explicit
    path = await chat.evaluate("(() => location.pathname)()", await_promise=False)
    return chat_id_from_path(str(path) if path else "")


async def wait_stream_done_with_marker(
    chat: McpChatSession,
    *,
    chat_id_hint: str | None,
    marker: str,
    timeout_sec: float,
) -> dict[str, object]:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    last: dict[str, object] = {}
    poll = 0
    nudged_done = False
    while asyncio.get_event_loop().time() < deadline:
        poll += 1
        heartbeat_e2e_lease()
        probe = await chat.evaluate(
            f"""(() => {{
              const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {{}};
              const sample = String(snap.lastAssistantSample ?? '');
              const marker = {marker!r};
              const re = new RegExp(`\\\\b${{marker}}\\\\b`, 'i');
              return {{
                chatId: snap.chatId ?? null,
                userCount: snap.userCount ?? 0,
                isStreaming: Boolean(snap.isStreaming),
                matched: Boolean(snap.hasDone) || re.test(sample),
                lastAssistantSample: sample,
              }};
            }})()""",
            await_promise=False,
        )
        if isinstance(probe, dict):
            last = probe
            if poll == 1 or poll % 5 == 0:
                sample = str(probe.get("lastAssistantSample") or "")
                progress(
                    f"poll DONE marker #{poll} streaming={probe.get('isStreaming')} "
                    f"matched={probe.get('matched')} sample_len={len(sample)}"
                )
            chat_id = str(probe.get("chatId") or chat_id_hint or "").strip()
            if (
                chat_id
                and int(probe.get("userCount") or 0) >= 1
                and not probe.get("isStreaming")
                and probe.get("matched")
            ):
                return {**probe, "chatId": chat_id}
            if chat_id and not probe.get("isStreaming"):
                api_has_done = await asyncio.to_thread(
                    chat_messages_have_done,
                    chat_id,
                    api_url=get_e2e_api_url(),
                )
                if api_has_done:
                    return {
                        **probe,
                        "chatId": chat_id,
                        "matched": True,
                        "mode": "post-approval-api-done",
                    }
            if (
                not nudged_done
                and poll >= 15
                and not probe.get("isStreaming")
                and not probe.get("matched")
                and int(probe.get("userCount") or 0) >= 1
            ):
                nudged_done = True
                progress("nudge model to reply DONE only")
                await chat.send_message("Reply with only DONE.", "Reply with only DONE.")
                heartbeat_e2e_lease()
                continue
        await asyncio.sleep(2.0)
    return {**last, "ok": False, "err": "turn-timeout"}


async def wait_for_trusted_app_display_name(
    display_name: str,
    *,
    timeout_sec: float = 60.0,
) -> dict[str, object]:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    target = display_name.strip().lower()
    poll = 0
    apps: list[dict[str, object]] = []
    while asyncio.get_event_loop().time() < deadline:
        poll += 1
        heartbeat_e2e_lease()
        apps = await asyncio.to_thread(list_trusted_apps_via_api)
        for app in apps:
            if not isinstance(app, dict):
                continue
            name = str(app.get("display_name") or "").strip().lower()
            if name == target or target in name:
                return app
        if apps and poll % 5 == 0:
            progress(f"trust API poll waiting for {display_name!r}: {apps}")
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"Trusted app {display_name!r} not found via API within {timeout_sec}s: {apps}"
    )


async def verify_settings_revoke_trusted_app(
    chat: McpChatSession,
    *,
    trust_key: str,
    display_name: str,
) -> None:
    settings_url = f"{BASE_URL}/settings/system"
    progress(f"open settings for revoke trust_key={trust_key}")
    nav = await chat.evaluate(
        f"""(() => {{
          window.location.assign({settings_url!r});
          return {{ ok: true }};
        }})()""",
        await_promise=False,
    )
    assert isinstance(nav, dict) and nav.get("ok") is True, nav

    deadline = asyncio.get_event_loop().time() + 120.0
    probe: dict[str, object] = {}
    while asyncio.get_event_loop().time() < deadline:
        heartbeat_e2e_lease()
        probe = await chat.evaluate(
            f"""(() => {{
              const body = document.body?.innerText || '';
              const revokeBtn = document.querySelector('[data-testid="desktop-trust-revoke-{trust_key}"]');
              return {{
                hasDisplayName: body.includes({display_name!r}),
                revokeReady: Boolean(revokeBtn && !revokeBtn.disabled),
              }};
            }})()""",
            await_promise=False,
        )
        if isinstance(probe, dict) and probe.get("hasDisplayName") and probe.get("revokeReady"):
            break
        await asyncio.sleep(1.0)
    else:
        raise AssertionError(f"Settings trusted-app row not ready for revoke: {probe}")

    click = await chat.evaluate(
        f"""(() => {{
          const btn = document.querySelector('[data-testid="desktop-trust-revoke-{trust_key}"]');
          if (!btn || btn.disabled) return {{ ok: false, err: 'revoke-not-ready' }};
          btn.click();
          return {{ ok: true }};
        }})()""",
        await_promise=False,
    )
    assert isinstance(click, dict) and click.get("ok") is True, f"Settings revoke click failed: {click}"

    empty_deadline = asyncio.get_event_loop().time() + 60.0
    while asyncio.get_event_loop().time() < empty_deadline:
        heartbeat_e2e_lease()
        apps = await asyncio.to_thread(list_trusted_apps_via_api)
        if not apps:
            return
        await asyncio.sleep(1.0)
    raise AssertionError(f"Trusted apps not empty after settings revoke: {apps}")


async def complete_turn_after_approval(
    chat: McpChatSession,
    *,
    chat_id_hint: str | None,
) -> str:
    progress("wait assistant DONE")
    after_turn = await wait_stream_done_with_marker(
        chat,
        chat_id_hint=chat_id_hint,
        marker="DONE",
        timeout_sec=180.0,
    )
    if not after_turn.get("matched"):
        chat_id_probe = str(after_turn.get("chatId") or chat_id_hint or "").strip()
        if chat_id_probe and await asyncio.to_thread(
            chat_messages_have_done,
            chat_id_probe,
            api_url=get_e2e_api_url(),
        ):
            progress("approval verified via API DONE marker fallback")
            after_turn = {
                **after_turn,
                "matched": True,
                "chatId": chat_id_probe,
                "mode": "post-approval-api-done",
            }

    if str(after_turn.get("path", "")).startswith("/settings"):
        pytest.fail(f"Send redirected to settings: {after_turn}")
    assert after_turn.get("matched") is True, (
        f"Turn did not complete with DONE after approval: {after_turn}"
    )

    chat_id = await resolve_chat_id(chat, after_turn)
    assert chat_id, f"Expected chat id after approval turn: {after_turn}"
    assert chat_user_message_count(chat_id) >= 1, after_turn
    progress(f"done chat_id={chat_id}")
    return chat_id


async def run_approval_attempt(chat: McpChatSession, *, scope: str = "once") -> str:
    progress("new chat + ensure surface")
    await chat.click_new_chat()
    await chat.ensure_chat_surface(BASE_URL)
    await ensure_textedit_fixture_ready()

    progress("enable computer_use")
    tools_setup = await chat.enable_computer_use()
    assert tools_setup.get("ok") is True, f"computer_use bridge failed: {tools_setup}"
    assert "computer_use" in (tools_setup.get("tools") or []), tools_setup

    heartbeat_e2e_lease()
    progress("send agent prompt (textedit stays minimized; no focus loop)")
    await chat.send_message(E2E_PROMPT, E2E_PROMPT)
    heartbeat_e2e_lease()

    progress("wait desktop tool activity")
    tool_activity, last_tool, server_pending, ui_pending = await ensure_interact_gate(chat)
    progress(
        f"post-wait lastTool={last_tool} server_pending={server_pending} ui_pending={ui_pending}"
    )
    require_approval_gate_triggered(
        last_tool=last_tool,
        server_pending=server_pending,
        ui_pending=ui_pending,
    )

    progress("activate chrome for approval UI")
    await asyncio.to_thread(activate_chrome)
    await asyncio.sleep(1.0)

    progress("wait approval banner")
    approval_deadline = asyncio.get_event_loop().time() + APPROVAL_WAIT_SEC
    approval: dict[str, object] = {"pending": False}
    poll = 0
    while asyncio.get_event_loop().time() < approval_deadline:
        poll += 1
        heartbeat_e2e_lease()
        server_pending = await asyncio.to_thread(server_pending_approval_count)
        probe = await chat.probe_desktop_approval_once()
        if isinstance(probe, dict):
            approval = probe
            if poll == 1 or poll % 10 == 0:
                progress(
                    f"approval poll #{poll} ui_pending={probe.get('pending')} "
                    f"allowVisible={probe.get('allowVisible')} server_pending={server_pending}"
                )
            if probe.get("pending") or probe.get("allowVisible"):
                break
            if server_pending > 0:
                await asyncio.sleep(0.5)
                continue
            if probe.get("err") == "model-completed-without-desktop-tools":
                raise AssertionError(f"Model finished without desktop tools: {probe}")
        await asyncio.sleep(0.5)

    if approval.get("err") == "model-completed-without-desktop-tools":
        raise AssertionError(f"Model finished without desktop tools: {approval}")
    assert approval.get("pending") is True or approval.get("allowVisible") is True, (
        f"Expected desktop approval banner (server_pending="
        f"{await asyncio.to_thread(server_pending_approval_count)}): {approval}"
    )
    if not approval.get("allowVisible"):
        allow_deadline = asyncio.get_event_loop().time() + 60.0
        while asyncio.get_event_loop().time() < allow_deadline:
            probe = await chat.probe_desktop_approval_once()
            if isinstance(probe, dict) and probe.get("allowVisible"):
                approval = probe
                break
            await asyncio.sleep(0.25)
    assert approval.get("allowVisible") is True, f"Allow-once button not visible: {approval}"

    if scope == "always":
        if not approval.get("allowAlwaysVisible"):
            always_deadline = asyncio.get_event_loop().time() + 30.0
            while asyncio.get_event_loop().time() < always_deadline:
                probe = await chat.probe_desktop_approval_once()
                if isinstance(probe, dict) and probe.get("allowAlwaysVisible"):
                    approval = probe
                    break
                await asyncio.sleep(0.25)
        assert approval.get("allowAlwaysVisible") is True, (
            f"Allow-always button not visible: {approval}"
        )
        progress("click allow always")
        click = await chat.click_desktop_allow_always()
        assert click.get("ok") is True, f"Allow-always click failed: {click}"
    else:
        progress("click allow once")
        click = await chat.click_desktop_allow_once()
        assert click.get("ok") is True, f"Allow-once click failed: {click}"

    chat_id_hint = str(
        (await chat.evaluate(
            "(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.()?.chatId ?? null)()",
            await_promise=False,
        ))
        or ""
    ).strip() or None

    trusted: dict[str, object] | None = None
    if scope == "always":
        trusted = await wait_for_trusted_app_display_name("TextEdit", timeout_sec=120.0)

    chat_id = await complete_turn_after_approval(chat, chat_id_hint=chat_id_hint)

    if scope == "always":
        assert trusted is not None
        trust_key = str(trusted.get("trust_key") or "").strip()
        assert trust_key, f"Missing trust_key in trusted app record: {trusted}"
        await verify_settings_revoke_trusted_app(
            chat,
            trust_key=trust_key,
            display_name="TextEdit",
        )

    return chat_id
