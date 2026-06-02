"""Channel Media Degradation E2E Test

Verifies that channels with media=False correctly inject the prompt
and prevent the model from generating images.
"""

import os

import pytest

from app.channels.core.base import BaseChannel
from app.channels.types import ChannelCapabilities, InboundMessage
from app.core.channel_bridge.agent_executor import ChannelAgentExecutor


class MockTextOnlyChannel(BaseChannel):
    name = "mock_text_only"
    capabilities = ChannelCapabilities(media=False, text=True)

    async def send(self, msg) -> str | None:
        return "msg_id"


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("BASIC_API_KEY"), reason="E2E test requires BASIC_API_KEY environment variable")
async def test_channel_media_degradation_prompt_injection():
    """Test that the agent refuses to generate media on a text-only channel."""

    # 1. Setup the executor
    executor = ChannelAgentExecutor()

    # 2. Create a mock inbound message from a text-only channel
    msg = InboundMessage(
        channel="mock_text_only",
        sender_id="test_user_1",
        chat_id="test_chat_1",
        content="Please draw a picture of a cute cat for me.",
        channel_capabilities=ChannelCapabilities(media=False, text=True),
        sent_at="2023-10-10T10:00:00Z",
        sent_timezone="UTC",
    )

    from app.channels.types import TopicContext

    topic_context = TopicContext(topic_id="test_topic", agent_id="main")

    # 4. Execute the stream
    # We need to capture the output

    # Execute stream directly
    stream = executor.execute_stream(msg=msg, topic_context=topic_context)

    from app.channels.types import OutboundMessage, StreamingText

    full_response = ""
    async for chunk in stream:
        if isinstance(chunk, StreamingText):
            full_response = chunk.text
        elif isinstance(chunk, OutboundMessage):
            full_response = chunk.content
    print(f"\n\n--- Agent Response ---\n{full_response}\n----------------------\n")

    # 5. Verify the response
    # The model should refuse to draw and instead describe it in text,
    # because the prompt injection says "DO NOT attempt to generate or send any images, video, or audio"

    # It should not contain markdown image links like ![cat](...)
    assert "![" not in full_response, "Model should not generate markdown images"

    # It should contain a text description
    assert len(full_response) > 20, "Model should provide a text description"

    # It might explicitly mention it can't draw or send images
    # We don't strictly assert this because LLM phrasing varies, but we log it.
    if "cannot" in full_response.lower() or "text" in full_response.lower() or "describe" in full_response.lower():
        print("✅ Model explicitly acknowledged the text-only limitation.")
    else:
        print("⚠️ Model described the cat but didn't explicitly mention the limitation. This is acceptable.")


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("BASIC_API_KEY"), reason="E2E test requires BASIC_API_KEY environment variable")
async def test_channel_media_supported_generates_image():
    """Test that the agent CAN generate media on a rich channel."""

    executor = ChannelAgentExecutor()

    msg = InboundMessage(
        channel="mock_rich_channel",
        sender_id="test_user_2",
        chat_id="test_chat_2",
        content="Please draw a picture of a cute cat for me using the canvas_design tool.",
        channel_capabilities=ChannelCapabilities(media=True, text=True),
        sent_at="2023-10-10T10:00:00Z",
        sent_timezone="UTC",
    )

    from app.channels.types import TopicContext

    topic_context = TopicContext(topic_id="test_topic_2", agent_id="main")

    stream = executor.execute_stream(msg=msg, topic_context=topic_context)

    from app.channels.types import OutboundMessage, StreamingText

    full_response = ""
    async for chunk in stream:
        if isinstance(chunk, StreamingText):
            full_response = chunk.text
        elif isinstance(chunk, OutboundMessage):
            full_response = chunk.content

    print(f"\n\n--- Agent Response (Rich) ---\n{full_response}\n----------------------\n")

    # The model should attempt to use a tool or generate an image link
    # Since it's a real model, it might fail to load the tool, but it shouldn't refuse because of the prompt injection.
    assert "DO NOT attempt to generate or send any images" not in full_response, "Prompt injection should not leak into response"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_rogue_tool_media_stripped_by_bus():
    """Test that MessageBus strips media even if a tool forces it."""
    from app.channels.core.bus import MessageBus, downgrade_components
    from app.channels.types import MediaAttachment, MediaType, OutboundMessage

    # 1. Create a channel that does NOT support media
    class StrictTextChannel(BaseChannel):
        name = "strict_text"
        capabilities = ChannelCapabilities(media=False, text=True)

        async def send(self, msg: OutboundMessage) -> str | None:
            # This is the crucial assertion: the channel SDK should NEVER receive media
            assert len(msg.media) == 0, "Channel received media despite capabilities!"
            assert "Rogue Image" in msg.content, "Fallback text should be in content"
            return "msg_id"

    bus = MessageBus()
    channel = StrictTextChannel()
    bus.register_channel(channel)

    # 2. Simulate a rogue tool returning an OutboundMessage with media
    rogue_media = MediaAttachment(media_type=MediaType.IMAGE, url="https://rogue.com/img.png")
    msg = OutboundMessage(
        user_id="sandbox",
        channel="strict_text",
        recipient_id="user1",
        content="Here is the image you requested:",
        media=(rogue_media,),
    )

    # 3. Send through bus
    # We call downgrade_components directly to simulate what send_tracked does
    downgraded_msg = downgrade_components(msg, channel)

    # 4. Verify
    assert len(downgraded_msg.media) == 0
    assert "[Image: https://rogue.com/img.png]" in downgraded_msg.content
