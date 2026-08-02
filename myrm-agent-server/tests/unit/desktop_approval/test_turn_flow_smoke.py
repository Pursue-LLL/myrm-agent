"""Unit smoke tests for desktop approval turn-flow guards."""

from __future__ import annotations

import asyncio

import pytest

from tests.e2e.desktop_approval import turn_flow
from tests.e2e.desktop_approval.turn_flow import complete_turn_after_approval


class _ForceShellClient:
    def __init__(self) -> None:
        self.recover_calls = 0

    def recover_mux_transport(self) -> None:
        self.recover_calls += 1


class _ForceShellChat:
    def __init__(self) -> None:
        self._client = _ForceShellClient()
        self.navigate_calls = 0
        self.bind_calls = 0

    async def _navigate_to_chat_home(self, *, timeout_ms: int) -> None:
        _ = timeout_ms
        self.navigate_calls += 1
        if self.navigate_calls == 1:
            await asyncio.sleep(0.05)
            return
        return

    async def wait_shell_ready(
        self, *, timeout_sec: float, require_bridge: bool
    ) -> None:
        _ = timeout_sec
        _ = require_bridge

    async def ensure_react_e2e_bridge(self, *, timeout_sec: float) -> None:
        _ = timeout_sec

    async def ensure_e2e_api_base_binding(self) -> None:
        self.bind_calls += 1


class _RouteClient:
    def __init__(self) -> None:
        self.navigate_calls = 0

    def navigate(self, *_: object, **__: object) -> None:
        self.navigate_calls += 1


class _RouteChat:
    def __init__(self) -> None:
        self._client = _RouteClient()
        self._page = object()
        self.probe_calls = 0
        self.bridge_calls = 0
        self.surface_calls = 0

    async def evaluate(self, *_: object, **__: object) -> dict[str, object]:
        self.probe_calls += 1
        if self.probe_calls == 1:
            return {"href": "http://127.0.0.1:3000/", "onTarget": False}
        if self.probe_calls == 2:
            return {"href": "http://127.0.0.1:3000/", "onTarget": False}
        return {
            "href": "http://127.0.0.1:3000/chat/chat-1",
            "onTarget": True,
        }

    async def ensure_react_e2e_bridge(self, *, timeout_sec: float) -> None:
        _ = timeout_sec
        self.bridge_calls += 1

    async def ensure_chat_surface(self, *_: object, **__: object) -> None:
        self.surface_calls += 1


@pytest.mark.asyncio
async def test_force_chat_shell_retries_after_wall_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _to_thread(func: object, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[misc]

    monkeypatch.setattr(turn_flow, "_FORCE_CHAT_NAVIGATE_TIMEOUT_SEC", 0.01)
    monkeypatch.setattr(turn_flow.asyncio, "to_thread", _to_thread)
    chat = _ForceShellChat()
    await turn_flow._force_chat_shell(chat, label="unit")
    assert chat.navigate_calls == 2
    assert chat.bind_calls == 1
    assert chat._client.recover_calls == 1


@pytest.mark.asyncio
async def test_ensure_chat_route_forces_target_when_surface_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _to_thread(func: object, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[misc]

    monkeypatch.setattr(turn_flow.asyncio, "to_thread", _to_thread)
    chat = _RouteChat()
    await turn_flow._ensure_chat_route(chat, "chat-1")
    assert chat._client.navigate_calls == 2
    assert chat.surface_calls == 1
    assert chat.bridge_calls >= 2


@pytest.mark.asyncio
async def test_complete_turn_after_approval_recovers_on_empty_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[dict[str, object]] = [
        {
            "ok": False,
            "matched": False,
            "chatId": "chat-empty",
            "userCount": 0,
            "isStreaming": False,
            "lastAssistantSample": "",
            "err": "turn-timeout",
        },
        {
            "ok": True,
            "matched": True,
            "chatId": "chat-1",
            "userCount": 1,
            "isStreaming": False,
            "lastAssistantSample": "DONE",
        },
    ]

    async def _wait_done(*_: object, **__: object) -> dict[str, object]:
        if not waits:
            raise AssertionError("missing wait_stream_done_with_marker outcome")
        return waits.pop(0)

    routed: list[str] = []

    async def _ensure_route(*args: object) -> None:
        routed.append(str(args[1]))

    async def _resolve_chat_id(*_: object, **__: object) -> str:
        return "chat-1"

    monkeypatch.setattr(turn_flow, "wait_stream_done_with_marker", _wait_done)
    monkeypatch.setattr(turn_flow, "_ensure_chat_route", _ensure_route)
    monkeypatch.setattr(turn_flow, "resolve_chat_id", _resolve_chat_id)
    monkeypatch.setattr(
        turn_flow, "chat_user_message_count", lambda *_args, **_kwargs: 1
    )
    chat = object()
    chat_id = await complete_turn_after_approval(  # type: ignore[arg-type]
        chat,
        chat_id_hint="chat-1",
    )
    assert chat_id == "chat-1"
    assert routed == ["chat-1", "chat-1"]


def test_turn_flow_seeded_resend_api_kickoff_ssot() -> None:
    text = open(turn_flow.__file__, encoding="utf-8").read()
    assert "_kickoff_desktop_turn_via_api_sync" in text
    assert "R232 mux-bypass" in text
    assert "R233 api-primary DONE wait" in text
    assert "api_primary_done=seeded_api_kickoff" in text
    assert "R264 CDP resend transport fail" in text
    assert "run_r262_chain" in text
    seeded_block = text.split("seeded pending fallback approval", maxsplit=1)[1]
    seeded_block = seeded_block.split("if not kickoff_ok:")[0]
    assert (
        "await chat.ensure_react_e2e_bridge"
        not in seeded_block.split(
            "API kickoff miss",
            maxsplit=1,
        )[0]
    )


@pytest.mark.asyncio
async def test_complete_turn_after_approval_api_primary_skips_cdp_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routed: list[str] = []
    waited: list[str] = []

    async def _ensure_route(*args: object) -> None:
        routed.append(str(args[1]))

    def _wait_api_done(
        chat_id: str,
        *,
        api_url: str | None = None,
        timeout_sec: float = 120.0,
        fetch_timeout_sec: float = 15.0,
        progress_interval_sec: float = 30.0,
        on_tick: object | None = None,
    ) -> bool:
        _ = api_url
        _ = timeout_sec
        _ = fetch_timeout_sec
        _ = progress_interval_sec
        _ = on_tick
        waited.append(chat_id)
        return True

    monkeypatch.setattr(turn_flow, "_ensure_chat_route", _ensure_route)
    monkeypatch.setattr(turn_flow, "wait_chat_messages_done", _wait_api_done)
    monkeypatch.setattr(
        turn_flow, "chat_user_message_count", lambda *_args, **_kwargs: 1
    )
    chat = object()
    chat_id = await complete_turn_after_approval(  # type: ignore[arg-type]
        chat,
        chat_id_hint="chat-seeded",
        api_primary_done=True,
    )
    assert chat_id == "chat-seeded"
    assert waited == ["chat-seeded"]
    assert routed == []


@pytest.mark.asyncio
async def test_seeded_kickoff_activity_probe_requires_beyond_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [{"role": "user", "content": "hello"}]

    def _fetch(
        _chat_id: str, *, api_url: str | None = None, **kwargs: object
    ) -> list[dict[str, object]]:
        _ = api_url
        _ = kwargs
        return list(messages)

    monkeypatch.setattr(turn_flow, "fetch_chat_messages", _fetch)
    inactive = turn_flow._seeded_kickoff_activity_probe(  # noqa: SLF001
        "chat-1",
        baseline_user_count=1,
    )
    assert inactive["active"] is False

    messages.append({"role": "assistant", "content": "working"})
    active = turn_flow._seeded_kickoff_activity_probe(  # noqa: SLF001
        "chat-1",
        baseline_user_count=1,
    )
    assert active["active"] is True


@pytest.mark.asyncio
async def test_wait_seeded_resend_turn_kickoff_no_false_positive_on_stale_user_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        turn_flow,
        "_seeded_kickoff_activity_probe",
        lambda *_args, **_kwargs: {"active": False, "userCount": 1},
    )

    class _Chat:
        async def evaluate(
            self, *_args: object, **_kwargs: object
        ) -> dict[str, object]:
            return {"userCount": 1, "isStreaming": False}

        async def send_message(self, *_args: object, **_kwargs: object) -> None:
            return None

    ok = await turn_flow._wait_seeded_resend_turn_kickoff(  # noqa: SLF001
        _Chat(),  # type: ignore[arg-type]
        chat_id="chat-stale",
        timeout_sec=0.5,
        baseline_user_count=1,
        baseline_ui_user_count=1,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_wait_seeded_resend_turn_kickoff_r245_effective_ui_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R245: UI baseline must honor API baseline when R241 fastpath sets baseline_user=1."""
    monkeypatch.setattr(
        turn_flow,
        "_seeded_kickoff_activity_probe",
        lambda *_args, **_kwargs: {"active": False, "userCount": 1},
    )

    class _Chat:
        async def evaluate(
            self, *_args: object, **_kwargs: object
        ) -> dict[str, object]:
            return {"userCount": 1, "isStreaming": False}

        async def send_message(self, *_args: object, **_kwargs: object) -> None:
            return None

    ok = await turn_flow._wait_seeded_resend_turn_kickoff(  # noqa: SLF001
        _Chat(),  # type: ignore[arg-type]
        chat_id="chat-r245",
        timeout_sec=0.5,
        baseline_user_count=1,
        baseline_ui_user_count=0,
    )
    assert ok is False
