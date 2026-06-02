from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.channels.channel_ingress import (
    ChannelIngressRequest,
    ResolvedChannelIdentityRequest,
    ingest_channel_message,
)


class _FakeBus:
    def __init__(self) -> None:
        self.messages = []

    async def _handle_inbound(self, msg: object) -> None:
        self.messages.append(msg)


@pytest.mark.asyncio
async def test_ingest_channel_message_propagates_thread_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import channel_bridge as channels_module

    fake_bus = _FakeBus()
    fake_gateway = SimpleNamespace(bus=fake_bus, _router=object())
    monkeypatch.setattr(channels_module, "channel_gateway", fake_gateway)

    body = ChannelIngressRequest(
        message_id="msg-1",
        content="hello",
        channel_type="feishu",
        chat_type="group",
        chat_id="chat-1",
        channel_user_id="owner-1",
        thread_id="body-thread",
        timestamp=1710000000.0,
        resolved_identity=ResolvedChannelIdentityRequest(
            platform_user_id="owner-1",
            sandbox_owner_id="owner-1",
            channel_id="feishu",
            channel_user_id="owner-1",
            conversation_id="feishu:group:chat-1",
            task_id="feishu:group:chat-1:thread:topic-9",
            thread_id="topic-9",
        ),
    )

    result = await ingest_channel_message(body)

    assert result == {"status": "queued"}
    assert len(fake_bus.messages) == 1
    inbound = fake_bus.messages[0]
    assert inbound.user_id == "owner-1"
    assert inbound.thread_id == "topic-9"
    assert inbound.metadata["trusted_inbound"] == "control_plane"
    assert inbound.metadata["resolved_identity"]["task_id"] == "feishu:group:chat-1:thread:topic-9"


@pytest.mark.asyncio
async def test_ingest_channel_message_propagates_force_new_epoch(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import channel_bridge as channels_module

    fake_bus = _FakeBus()
    fake_gateway = SimpleNamespace(bus=fake_bus, _router=object())
    monkeypatch.setattr(channels_module, "channel_gateway", fake_gateway)

    body = ChannelIngressRequest(
        message_id="msg-2",
        content="hello after new",
        channel_type="feishu",
        chat_type="private",
        chat_id="chat-2",
        channel_user_id="owner-2",
        force_new_epoch=True,
        timestamp=1710000001.0,
        resolved_identity=ResolvedChannelIdentityRequest(
            platform_user_id="owner-2",
            sandbox_owner_id="owner-2",
            channel_id="feishu",
            channel_user_id="owner-2",
            conversation_id="feishu:private:chat-2",
            task_id="feishu:private:chat-2",
        ),
    )

    result = await ingest_channel_message(body)

    assert result == {"status": "queued"}
    assert len(fake_bus.messages) == 1
    inbound = fake_bus.messages[0]
    assert inbound.metadata["force_new_epoch"] is True
