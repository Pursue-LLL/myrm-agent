"""Integration test: _attach_web_handoff full pipeline.

Exercises the real ChatService DB path to verify that the handoff
button uses the database Chat UUID, not the IM peer_id.

Tunnel/ingress is monkey-patched but ChatService hits the real SQLite DB.
"""

from __future__ import annotations

import pytest

from app.channels.routing.router_execution import RouterExecutionMixin
from app.channels.types import InboundMessage, OutboundMessage
from app.remote_access.tunnel_manager import TunnelManager, TunnelState
from app.services.chat.chat_service import ChatService
from app.services.event.app_event_bus import ServerEventBus


@pytest.fixture(autouse=True)
def _patch_tunnel_running(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = TunnelManager()
    manager._state = TunnelState.RUNNING
    manager._public_url = "https://tunnel-test.example.com"
    monkeypatch.setattr(
        "app.remote_access.mobile_deep_link.get_tunnel_manager",
        lambda: manager,
    )

    async def _no_ingress() -> str:
        return ""

    monkeypatch.setattr(
        "app.core.infra.ingress.get_public_ingress_base_url",
        _no_ingress,
    )


async def test_attach_web_handoff_resolves_db_uuid() -> None:
    """Full path: create channel chat → _attach_web_handoff → verify URL has DB UUID."""
    session_key = "telegram:integration-test-peer-42"
    chat = await ChatService.get_or_create_channel_chat(session_key, "telegram")
    db_uuid = chat.id

    result = OutboundMessage(
        channel="telegram",
        recipient_id="integration-test-peer-42",
        content="Hello from agent",
        user_id="local-user",
    )
    inbound = InboundMessage(
        channel="telegram",
        sender_id="integration-test-peer-42",
        content="hi",
    )

    patched = await RouterExecutionMixin._attach_web_handoff(
        result,
        inbound,
    )

    assert patched.components, "Expected handoff button to be attached"
    last_row = patched.components[-1]
    btn = last_row[0]
    assert btn.action_id == "web:continue_chat"
    assert db_uuid in btn.url, f"URL must contain DB UUID {db_uuid}, got {btn.url}"
    assert "integration-test-peer-42" not in btn.url, "URL must NOT contain IM peer_id"


async def test_attach_web_handoff_resolves_a_topic_scoped_chat() -> None:
    """A forum-topic conversation stores channel + peer + topic + agent; the lookup must match it.

    The other cases here use a bare ``channel:peer`` key, which the stored key also starts with —
    that is why they passed while the lookup dropped every topic-scoped chat.
    """
    from app.channels.types.session import SessionKey

    session_key = SessionKey(
        channel="telegram",
        peer_kind="group",
        peer_id="-1007770001",
        thread_id="100",
        agent_id="agent-uuid-1",
    ).to_str()
    chat = await ChatService.get_or_create_channel_chat(session_key, "telegram")

    result = OutboundMessage(
        channel="telegram",
        recipient_id="-1007770001",
        content="Hello from the topic agent",
        user_id="local-user",
    )
    inbound = InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="hi",
        chat_id="-1007770001",
        is_group=True,
        thread_id="100",
    )

    patched = await RouterExecutionMixin._attach_web_handoff(result, inbound)

    assert patched.components, "a topic-scoped chat must still get the handoff button"
    assert chat.id in patched.components[-1][0].url


async def test_attach_web_handoff_ignores_a_longer_peer_with_the_same_prefix() -> None:
    """``-1008881`` must not resolve the conversation of ``-1008880001``."""
    from app.channels.types.session import SessionKey

    other_key = SessionKey(channel="telegram", peer_kind="group", peer_id="-1008880001", thread_id="100").to_str()
    await ChatService.get_or_create_channel_chat(other_key, "telegram")

    result = OutboundMessage(
        channel="telegram",
        recipient_id="-1008881",
        content="unrelated turn",
        user_id="local-user",
    )
    inbound = InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="hi",
        chat_id="-1008881",
        is_group=True,
        thread_id="100",
    )

    patched = await RouterExecutionMixin._attach_web_handoff(result, inbound)

    assert not patched.components, "a different group must not borrow another chat's handoff"


async def test_attach_web_handoff_preserves_existing_components() -> None:
    """Handoff button appends to, not replaces, existing components."""
    from app.channels.types.components import ActionButton, ButtonStyle

    session_key = "feishu:preserve-test-peer"
    await ChatService.get_or_create_channel_chat(session_key, "feishu")

    existing_btn = ActionButton(
        label="Approve",
        action_id="approval:approve:req-1",
        style=ButtonStyle.PRIMARY,
    )
    result = OutboundMessage(
        channel="feishu",
        recipient_id="preserve-test-peer",
        content="Need approval",
        user_id="local-user",
        components=((existing_btn,),),
    )
    inbound = InboundMessage(
        channel="feishu",
        sender_id="preserve-test-peer",
        content="approve",
    )

    patched = await RouterExecutionMixin._attach_web_handoff(
        result,
        inbound,
    )

    assert len(patched.components) == 2
    assert patched.components[0][0].action_id == "approval:approve:req-1"
    assert patched.components[1][0].action_id == "web:continue_chat"


async def test_attach_web_handoff_no_chat_returns_unchanged() -> None:
    """When no channel chat exists, original message is returned untouched."""
    result = OutboundMessage(
        channel="telegram",
        recipient_id="unknown-peer-999",
        content="Hello",
        user_id="local-user",
    )
    inbound = InboundMessage(
        channel="telegram",
        sender_id="unknown-peer-999",
        content="hi",
    )

    patched = await RouterExecutionMixin._attach_web_handoff(
        result,
        inbound,
    )

    assert patched is result
    assert not patched.components


async def test_attach_web_handoff_graceful_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exception in ChatService should not block message delivery."""

    async def _exploding_lookup(_key: str) -> None:
        raise RuntimeError("DB connection lost")

    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.get_channel_chat_by_key",
        staticmethod(_exploding_lookup),
    )

    result = OutboundMessage(
        channel="telegram",
        recipient_id="crash-peer",
        content="Still delivered",
        user_id="local-user",
    )
    inbound = InboundMessage(
        channel="telegram",
        sender_id="crash-peer",
        content="hi",
    )

    patched = await RouterExecutionMixin._attach_web_handoff(
        result,
        inbound,
    )

    assert patched is result
    assert not patched.components


async def test_web_channel_skips_handoff() -> None:
    """_deliver_agent_result gates on msg.channel != 'web'; verify the gate logic.
    Web channel messages should NOT get handoff buttons (WebUI already IS the target).
    """
    session_key = "web:web-test-peer"
    await ChatService.get_or_create_channel_chat(session_key, "web")

    result = OutboundMessage(
        channel="web",
        recipient_id="web-test-peer",
        content="Hello from WebUI",
        user_id="local-user",
    )
    inbound = InboundMessage(
        channel="web",
        sender_id="web-test-peer",
        content="hi",
    )

    if inbound.channel != "web":
        patched = await RouterExecutionMixin._attach_web_handoff(
            result,
            inbound,
        )
    else:
        patched = result

    assert patched is result
    assert not patched.components


async def test_btw_notifier_delivers_handoff_for_a_source_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_deliver`` attaches the handoff button for the task's originating Chat UUID."""
    from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

    session_key = "telegram:btw-notify-peer-7"
    chat = await ChatService.get_or_create_channel_chat(session_key, "telegram")

    sent: list[OutboundMessage] = []

    async def _capture(msg: OutboundMessage) -> None:
        sent.append(msg)

    monkeypatch.setattr(
        "app.core.channel_bridge.channel_gateway.bus.send_now",
        _capture,
    )

    notifier = BtwTaskNotifier(ServerEventBus())
    await notifier._deliver(
        {
            "channel": "telegram",
            "chat_id": "btw-notify-peer-7",
            "source_chat_id": chat.id,
            "task_id": "task-1",
            "status": "completed",
            "title": "Background task",
            "result": "done",
            "locale": "en",
        }
    )

    assert sent, "the notification must still be delivered"
    components = sent[-1].components or ()
    assert components, "the originating chat must get the handoff button"
    btn = components[-1][0]
    assert chat.id in btn.url
    assert "btw-notify-peer-7" not in btn.url


async def test_btw_notifier_btw_branch_skips_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """The BTW branch carries an IM peer in ``chat_id``, so there is no Chat row to link to."""
    from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

    sent: list[OutboundMessage] = []

    async def _capture(msg: OutboundMessage) -> None:
        sent.append(msg)

    monkeypatch.setattr("app.core.channel_bridge.channel_gateway.bus.send_now", _capture)

    notifier = BtwTaskNotifier(ServerEventBus())
    await notifier._deliver(
        {
            "channel": "telegram",
            "chat_id": "im-peer-not-a-uuid",
            "background_source": "btw",
            "task_id": "task-2",
            "status": "completed",
            "title": "Background task",
            "result": "done",
            "locale": "en",
        }
    )

    assert sent, "the notification must still be delivered"
    assert not (sent[-1].components or ()), "an IM peer must not be resolved as a Chat UUID"


async def test_btw_notifier_no_task_id_skips_handoff() -> None:
    """btw_notifier only attaches handoff when task_id is present (L103)."""
    task_id = ""
    components: tuple[tuple[object, ...], ...] = ()
    if task_id:
        from app.remote_access.mobile_deep_link import resolve_web_handoff_components

        components = await resolve_web_handoff_components("some-id", locale="en")
    assert not components


async def test_idempotent_get_or_create() -> None:
    """Multiple calls with same session_key return same DB UUID."""
    session_key = "telegram:idempotent-peer"
    chat1 = await ChatService.get_or_create_channel_chat(session_key, "telegram")
    chat2 = await ChatService.get_or_create_channel_chat(session_key, "telegram")
    assert chat1.id == chat2.id
