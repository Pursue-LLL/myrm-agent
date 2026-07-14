"""Tests for enrich_channel_user_instructions IM persona injection.

Covers:
- Trigger conditions (edit=False + markdown=False)
- Non-trigger conditions (edit=True / markdown=True / capabilities=None)
- Co-existence with channel warnings and personality templates
- Default ChannelCapabilities behavior
- Ordering guarantee (warnings before IM persona)
"""

from __future__ import annotations

import pytest

from app.channels.types import ChannelCapabilities, InboundMessage
from app.core.channel_bridge.agent_executor.execute_preamble_instructions import (
    enrich_channel_user_instructions,
)


def _msg(caps: ChannelCapabilities | None, metadata: dict[str, object] | None = None) -> InboundMessage:
    return InboundMessage(
        channel="test",
        sender_id="u1",
        content="hello",
        chat_id="c1",
        channel_capabilities=caps,
        metadata=metadata or {},
    )


@pytest.mark.asyncio
async def test_im_persona_injected_for_restricted_channel() -> None:
    """Channels with edit=False and markdown=False should get IM persona."""
    caps = ChannelCapabilities(edit=False, markdown=False, max_text_length=4096)
    result = await enrich_channel_user_instructions(
        _msg(caps),
        user_instructions="",
        resolved_profile=None,
        agent_subagent_ids=None,
        resolved_agent_id=None,
    )
    assert "mobile IM app" in result
    assert "one-sentence summary" in result


@pytest.mark.asyncio
async def test_im_persona_not_injected_when_edit_supported() -> None:
    """Channels with edit=True should NOT get IM persona."""
    caps = ChannelCapabilities(edit=True, markdown=False, max_text_length=4096)
    result = await enrich_channel_user_instructions(
        _msg(caps),
        user_instructions="",
        resolved_profile=None,
        agent_subagent_ids=None,
        resolved_agent_id=None,
    )
    assert "mobile IM app" not in result


@pytest.mark.asyncio
async def test_im_persona_not_injected_when_markdown_supported() -> None:
    """Channels with markdown=True should NOT get IM persona."""
    caps = ChannelCapabilities(edit=False, markdown=True, max_text_length=4096)
    result = await enrich_channel_user_instructions(
        _msg(caps),
        user_instructions="",
        resolved_profile=None,
        agent_subagent_ids=None,
        resolved_agent_id=None,
    )
    assert "mobile IM app" not in result


@pytest.mark.asyncio
async def test_im_persona_appended_to_existing_instructions() -> None:
    """IM persona should be appended to existing user_instructions."""
    caps = ChannelCapabilities(edit=False, markdown=False)
    result = await enrich_channel_user_instructions(
        _msg(caps),
        user_instructions="Be helpful.",
        resolved_profile=None,
        agent_subagent_ids=None,
        resolved_agent_id=None,
    )
    assert result.startswith("Be helpful.")
    assert "mobile IM app" in result


@pytest.mark.asyncio
async def test_no_injection_when_capabilities_is_none() -> None:
    """Messages without channel_capabilities should not crash or inject persona."""
    result = await enrich_channel_user_instructions(
        _msg(None),
        user_instructions="base",
        resolved_profile=None,
        agent_subagent_ids=None,
        resolved_agent_id=None,
    )
    assert "mobile IM app" not in result
    assert "base" in result


@pytest.mark.asyncio
async def test_default_capabilities_triggers_im_persona() -> None:
    """Default ChannelCapabilities (markdown=False, edit=False) triggers IM persona."""
    caps = ChannelCapabilities()
    result = await enrich_channel_user_instructions(
        _msg(caps),
        user_instructions="",
        resolved_profile=None,
        agent_subagent_ids=None,
        resolved_agent_id=None,
    )
    assert "mobile IM app" in result


@pytest.mark.asyncio
async def test_warnings_and_im_persona_coexist() -> None:
    """When media=False and IM conditions met, both warnings and persona appear in order."""
    caps = ChannelCapabilities(edit=False, markdown=False, media=False, file_upload=False)
    result = await enrich_channel_user_instructions(
        _msg(caps),
        user_instructions="",
        resolved_profile=None,
        agent_subagent_ids=None,
        resolved_agent_id=None,
    )
    assert "DO NOT attempt to generate or send any images" in result
    assert "DO NOT attempt to generate or send any files" in result
    assert "mobile IM app" in result
    warnings_pos = result.index("following limitations")
    persona_pos = result.index("mobile IM app")
    assert warnings_pos < persona_pos


@pytest.mark.asyncio
async def test_personality_template_coexists_with_im_persona() -> None:
    """Non-default personality template appends after IM persona."""
    caps = ChannelCapabilities(edit=False, markdown=False)
    result = await enrich_channel_user_instructions(
        _msg(caps, metadata={"personality_style": "concise"}),
        user_instructions="",
        resolved_profile=None,
        agent_subagent_ids=None,
        resolved_agent_id=None,
    )
    assert "mobile IM app" in result
    assert "Communication Style" in result
    persona_pos = result.index("mobile IM app")
    style_pos = result.index("Communication Style")
    assert persona_pos < style_pos


@pytest.mark.asyncio
async def test_both_edit_and_markdown_true_no_persona() -> None:
    """Full-featured channel (edit=True, markdown=True) gets no persona/warnings."""
    caps = ChannelCapabilities(edit=True, markdown=True, media=True, file_upload=True)
    result = await enrich_channel_user_instructions(
        _msg(caps),
        user_instructions="",
        resolved_profile=None,
        agent_subagent_ids=None,
        resolved_agent_id=None,
    )
    assert "mobile IM app" not in result
    assert "limitations" not in result
