"""What one message from the session gate goes through before the agent runs it.

Runs the real ``AgentRouter._handle_merged`` with the preparation, the execution and the message effects replaced by
recorders (see ``turn_pipeline_testkit``), so what is pinned is the sequence of steps ahead of the run: journal, session
state and attachment enrichment.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.router_keys import routing_state_key
from tests.support.pending_approvals import asked_in

from .turn_pipeline_testkit import (
    STATE_KEY,
    TURN,
    attach_journal,
    execution_kwargs,
    prepared_message,
    tag_enricher,
    tag_enricher_async,
    turn_msg,
    turn_router,
)

# --- journal ---------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_fresh_message_is_journaled_and_acknowledged_when_the_turn_is_over() -> None:
    router = turn_router()
    journal = attach_journal(router)

    await router._handle_merged(turn_msg())

    journal.write.assert_called_once()
    journal.acknowledge.assert_called_once_with(journal.write.call_args.args[0].id)


@pytest.mark.asyncio
async def test_a_replayed_message_is_not_journaled_again_and_acknowledges_its_own_entry() -> None:
    router = turn_router()
    journal = attach_journal(router)

    await router._handle_merged(turn_msg(metadata={"is_recovery": True, "recovery_entry_ids": ["entry-7"]}))

    journal.write.assert_not_called()
    journal.acknowledge.assert_called_once_with("entry-7")


@pytest.mark.asyncio
async def test_a_turn_merged_from_replays_acknowledges_every_entry_it_stands_for() -> None:
    router = turn_router()
    journal = attach_journal(router)

    await router._handle_merged(turn_msg(metadata={"is_recovery": True, "recovery_entry_ids": ["entry-7", "entry-8"]}))

    journal.write.assert_not_called()
    assert [call.args for call in journal.acknowledge.call_args_list] == [("entry-7",), ("entry-8",)]


@pytest.mark.asyncio
async def test_a_replayed_message_without_an_entry_id_touches_the_journal_not_at_all() -> None:
    router = turn_router()
    journal = attach_journal(router)

    await router._handle_merged(turn_msg(metadata={"is_recovery": True}))

    journal.write.assert_not_called()
    journal.acknowledge.assert_not_called()


@pytest.mark.asyncio
async def test_the_timeout_resume_of_a_replayed_turn_is_journaled_like_any_live_message() -> None:
    router = turn_router()
    journal = attach_journal(router)
    asked = asked_in()
    asked.message.metadata.update({"is_recovery": True, "recovery_entry_ids": ["entry-7"]})

    await router._handle_merged(asked.resume_message({"decision": "reject"}))

    journal.write.assert_called_once()
    journal.acknowledge.assert_called_once_with(journal.write.call_args.args[0].id)


# --- session state ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("timeout", "expected"), [(3600, 3600), (None, None), (0, None)])
async def test_a_running_yolo_window_rides_on_the_message(timeout: int | None, expected: int | None) -> None:
    router = turn_router()
    enabled_at = time.time() - 5
    router._session_yolo[STATE_KEY] = (enabled_at, timeout)

    await router._handle_merged(turn_msg())

    assert prepared_message(router).metadata["yolo_state"] == (enabled_at, expected)
    assert STATE_KEY in router._session_yolo


@pytest.mark.asyncio
async def test_an_expired_yolo_window_is_dropped_and_not_applied() -> None:
    router = turn_router()
    router._session_yolo[STATE_KEY] = (time.time() - 100, 10)

    await router._handle_merged(turn_msg())

    assert "yolo_state" not in prepared_message(router).metadata
    assert STATE_KEY not in router._session_yolo


@pytest.mark.asyncio
async def test_the_personality_of_the_session_rides_on_the_message() -> None:
    router = turn_router()
    router._session_personality[STATE_KEY] = "pirate"

    await router._handle_merged(turn_msg())

    assert prepared_message(router).metadata["personality_style"] == "pirate"


@pytest.mark.asyncio
async def test_session_state_of_another_thread_is_not_applied() -> None:
    router = turn_router()
    other_thread = routing_state_key("telegram", "chat-1", "th-9")
    router._session_yolo[other_thread] = (time.time(), None)
    router._session_personality[other_thread] = "pirate"

    await router._handle_merged(turn_msg())

    assert {"yolo_state", "personality_style"}.isdisjoint(prepared_message(router).metadata)


# --- attachments -----------------------------------------------------------------------------------------------------


_ENRICHERS = [
    pytest.param("has_video_attachment_fn", "enrich_video_inbound", False, id="video"),
    pytest.param("has_image_attachment_fn", "enrich_image_inbound", True, id="image"),
    pytest.param("has_contact_attachment", "enrich_contact_inbound", True, id="contact"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("has", "enrich", "is_async"), _ENRICHERS)
async def test_an_attachment_of_a_new_turn_is_enriched_into_the_message(has: str, enrich: str, is_async: bool) -> None:
    router = turn_router()
    make = tag_enricher_async if is_async else tag_enricher

    with (
        patch(f"{TURN}.{has}", return_value=True),
        patch(f"{TURN}.{enrich}", side_effect=make(enrich)) as enricher,
        patch(f"{TURN}.has_video_with_audio", return_value=False),
    ):
        await router._handle_merged(turn_msg("see this"))

    enricher.assert_called_once()
    assert prepared_message(router).content == f"see this+{enrich}"


@pytest.mark.asyncio
@pytest.mark.parametrize(("has", "enrich", "is_async"), _ENRICHERS)
async def test_the_answer_to_an_approval_is_not_enriched(has: str, enrich: str, is_async: bool) -> None:
    router = turn_router()

    with patch(f"{TURN}.{has}", return_value=True) as present, patch(f"{TURN}.{enrich}") as enricher:
        await router._handle_merged(turn_msg("approve", resume_value={"type": "approve"}))

    present.assert_not_called()
    enricher.assert_not_called()
    assert prepared_message(router).content == "approve"


@pytest.mark.asyncio
async def test_a_video_with_sound_gets_its_audio_transcribed_after_the_video_is_described() -> None:
    router = turn_router()

    with (
        patch(f"{TURN}.has_video_attachment_fn", return_value=True),
        patch(f"{TURN}.enrich_video_inbound", side_effect=tag_enricher("video")),
        patch(f"{TURN}.has_video_with_audio", return_value=True),
        patch(f"{TURN}.transcribe_video_inbound", side_effect=tag_enricher_async("video-audio")),
    ):
        await router._handle_merged(turn_msg("clip"))

    assert prepared_message(router).content == "clip+video+video-audio"


@pytest.mark.asyncio
async def test_a_document_is_enriched_with_the_owners_extraction_setting() -> None:
    router = turn_router()
    enrich = AsyncMock(side_effect=tag_enricher_async("document"))

    with (
        patch(f"{TURN}.has_document_attachment", return_value=True),
        patch(f"{TURN}.enrich_document_inbound", new=enrich),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=SimpleNamespace(personal_settings_dict={"k": 1})),
        ),
        patch("app.services.files.attachment_settings.should_extract_document_text", return_value=True) as should_extract,
    ):
        await router._handle_merged(turn_msg("report"))

    should_extract.assert_called_once_with({"k": 1})
    assert enrich.await_args is not None
    assert enrich.await_args.kwargs == {"extract_enabled": True}
    assert prepared_message(router).content == "report+document"


@pytest.mark.asyncio
async def test_a_voice_message_is_transcribed_and_the_run_is_told_it_was_voice() -> None:
    router = turn_router()

    with (
        patch(f"{TURN}.has_audio_attachment", return_value=True),
        patch(f"{TURN}.transcribe_inbound", side_effect=tag_enricher_async("voice")),
    ):
        await router._handle_merged(turn_msg("spoken"))

    assert prepared_message(router).content == "spoken+voice"
    assert execution_kwargs(router) == {"is_resume": False, "inbound_had_voice": True}


@pytest.mark.asyncio
async def test_the_answer_to_an_approval_is_not_checked_for_voice() -> None:
    router = turn_router()

    with patch(f"{TURN}.has_audio_attachment", return_value=True) as present, patch(f"{TURN}.transcribe_inbound") as transcribe:
        await router._handle_merged(turn_msg("approve", resume_value={"type": "approve"}))

    present.assert_not_called()
    transcribe.assert_not_called()
    assert execution_kwargs(router) == {"is_resume": True, "inbound_had_voice": False}


@pytest.mark.asyncio
@pytest.mark.parametrize("resume", [False, True])
async def test_a_sticker_is_described_with_or_without_a_resume(resume: bool) -> None:
    router = turn_router()
    router._sticker_vision = MagicMock()
    resume_value: dict[str, object] | None = {"type": "approve"} if resume else None

    with patch(f"{TURN}.describe_sticker_inbound", side_effect=tag_enricher_async("sticker")):
        await router._handle_merged(turn_msg("sticker", metadata={"is_sticker": True}, resume_value=resume_value))

    assert prepared_message(router).content == "sticker+sticker"


@pytest.mark.asyncio
async def test_a_sticker_is_left_alone_without_a_vision_service() -> None:
    router = turn_router()
    router._sticker_vision = None

    with patch(f"{TURN}.describe_sticker_inbound") as describe:
        await router._handle_merged(turn_msg("sticker", metadata={"is_sticker": True}))

    describe.assert_not_called()


@pytest.mark.asyncio
async def test_the_enrichers_run_in_a_fixed_order() -> None:
    router = turn_router()
    router._sticker_vision = MagicMock()

    with (
        patch(f"{TURN}.has_audio_attachment", return_value=True),
        patch(f"{TURN}.transcribe_inbound", side_effect=tag_enricher_async("voice")),
        patch(f"{TURN}.describe_sticker_inbound", side_effect=tag_enricher_async("sticker")),
        patch(f"{TURN}.has_video_attachment_fn", return_value=True),
        patch(f"{TURN}.enrich_video_inbound", side_effect=tag_enricher("video")),
        patch(f"{TURN}.has_video_with_audio", return_value=False),
        patch(f"{TURN}.has_image_attachment_fn", return_value=True),
        patch(f"{TURN}.enrich_image_inbound", side_effect=tag_enricher_async("image")),
        patch(f"{TURN}.has_contact_attachment", return_value=True),
        patch(f"{TURN}.enrich_contact_inbound", side_effect=tag_enricher_async("contact")),
    ):
        await router._handle_merged(turn_msg("x", metadata={"is_sticker": True}))

    assert prepared_message(router).content == "x+voice+sticker+video+image+contact"
