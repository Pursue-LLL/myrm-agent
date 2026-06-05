import asyncio
import logging
from typing import AsyncGenerator

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.core.exceptions import ChannelSendError
from app.channels.protocols.agent import AgentExecutor
from app.channels.protocols.pairing import (
    ChannelPolicyProvider,
    DmPolicy,
    GroupPolicy,
    GroupTriggerMode,
    PairingStore,
)
from app.channels.routing.router import AgentRouter
from app.channels.routing.session_gate import SessionGateConfig
from app.channels.types import (
    ChannelStatus,
    InboundMessage,
    OutboundMessage,
    ProgressUpdate,
    SessionPolicy,
)

logging.basicConfig(level=logging.DEBUG)


class DummyChannel(BaseChannel):
    def __init__(self, bus: MessageBus):
        super().__init__()
        self.sent_messages = []
        self.name = "dummy"
        self._status = ChannelStatus.RUNNING

    @property
    def capabilities(self):
        from app.channels.types.messages import (
            ChannelCapabilities,
        )

        return ChannelCapabilities(media=True)

    async def send(self, msg: OutboundMessage) -> None:
        print(f"DummyChannel sending message: {msg}")
        if getattr(msg, "media", None):
            print("Raising ChannelSendError due to media")
            raise ChannelSendError("Media not supported", channel=self.name, retriable=False)
        self.sent_messages.append(msg)
        print(f"DummyChannel appended message. Total: {len(self.sent_messages)}")

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class DummyExecutor(AgentExecutor):
    async def execute_stream(
        self, msg: InboundMessage, user_id: str, **kwargs
    ) -> AsyncGenerator[ProgressUpdate | OutboundMessage, None]:
        print(f"DummyExecutor executing for msg: {msg}")
        yield ProgressUpdate(label="thinking")
        from app.channels.types import (
            MediaAttachment,
            MediaType,
        )

        yield msg.get_or_create_correlation_context().create_reply(
            content="Here is your image",
            media=(MediaAttachment(media_type=MediaType.IMAGE, url="http://fake.png"),),
        )


class DummyPairingStore(PairingStore):
    async def resolve(self, channel: str, sender_id: str) -> str | None:
        return "user1"

    async def bind(self, user_id: str, channel: str, sender_id: str) -> None:
        pass

    async def unbind(self, channel: str, sender_id: str) -> None:
        pass

    async def get_session_policy(self, user_id: str) -> SessionPolicy | None:
        return None

    async def set_session_policy(self, user_id: str, policy: SessionPolicy) -> None:
        pass


class DummyPolicyProvider(ChannelPolicyProvider):
    async def get_dm_policy(self, channel: str) -> DmPolicy | None:
        return DmPolicy.OPEN

    async def get_group_policy(self, channel: str) -> GroupPolicy | None:
        return GroupPolicy.OPEN

    async def get_group_trigger(self, channel: str) -> tuple[GroupTriggerMode, list[str]]:
        return GroupTriggerMode.ALL, []

    async def get_enabled_groups(self) -> set[str]:
        return {"chat-123"}

    async def get_guest_mode(self, channel: str) -> bool:
        return False

    async def get_free_response_chats(self, channel: str) -> set[str]:
        return set()

    async def get_default_user_id(self) -> str | None:
        return "user1"


@pytest.mark.asyncio
async def test_router_stream_thread_id_propagation_and_media_strip():
    """Test that AgentRouter propagates thread_id and send_with_retry strips media on failure."""
    bus = MessageBus()
    channel = DummyChannel(bus)
    bus.register_channel(channel)

    router = AgentRouter(
        bus=bus,
        pairing_store=DummyPairingStore(),
        agent_executor=DummyExecutor(),
        policy_provider=DummyPolicyProvider(),
        session_gate_config=SessionGateConfig(debounce_window_ms=0),
    )

    inbound = InboundMessage(
        channel="dummy",
        sender_id="user1",
        content="Send me an image",
        thread_id="thread-123",
        message_id="msg-456",
        chat_id="chat-123",
        is_group=True,
        sent_at="2023-10-10T10:00:00Z",
        sent_timezone="UTC",
    )

    # Start the router and bus
    await bus.start()
    await router.start()

    # Publish message to bus
    await bus._handle_inbound(inbound)

    # Wait for processing
    await asyncio.sleep(0.5)

    # Stop the router and bus
    await router.stop()
    await bus.stop()

    # We should have one message sent (the stripped one)
    assert len(channel.sent_messages) == 1
    sent_msg = channel.sent_messages[0]

    # Verify thread_id and reply_to_id were propagated by RouterStream
    assert sent_msg.thread_id == "thread-123"
    assert sent_msg.reply_to_id == "msg-456"

    # Verify media was stripped by retry logic
    assert not sent_msg.media
    assert "[Image/FileSendFailure" in sent_msg.content
