"""A sender the access policy refuses gets none of their attachments processed.

Speech-to-text, image download and caching, document parsing and sticker vision cost an API bill, bandwidth, disk or a
read of the owner's configuration, and the resolvers that refuse a sender run only after them. The gate asks the
admission verdict the event triggers already use, and fails open: an error in the check must never turn an admitted
sender's voice message into an empty one.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.pairing import DmPolicy, GroupPolicy, GroupTriggerMode, PairingRole, PairingStatus
from app.channels.routing.context_buffer import GroupContextBuffer
from app.channels.routing.policy_resolver import PolicyResolver
from app.channels.routing.router import AgentRouter
from app.channels.types import METADATA_EXPLICIT_MENTION_KEY, InboundMessage, MediaAttachment, MediaType, ReactionLevel

from .turn_pipeline_testkit import TURN, prepared_message, tag_enricher, tag_enricher_async, turn_msg, turn_router

_ENRICHERS = {
    "transcribe_inbound": tag_enricher_async,
    "enrich_video_inbound": tag_enricher,
    "enrich_image_inbound": tag_enricher_async,
    "enrich_contact_inbound": tag_enricher_async,
    "enrich_document_inbound": tag_enricher_async,
    "describe_sticker_inbound": tag_enricher_async,
}

_ATTACHMENTS = [
    pytest.param(MediaType.AUDIO, "transcribe_inbound", id="voice"),
    pytest.param(MediaType.VIDEO, "enrich_video_inbound", id="video"),
    pytest.param(MediaType.IMAGE, "enrich_image_inbound", id="image"),
    pytest.param(MediaType.CONTACT, "enrich_contact_inbound", id="contact"),
    pytest.param(MediaType.DOCUMENT, "enrich_document_inbound", id="document"),
]


@contextmanager
def _processing_recorded() -> Iterator[dict[str, MagicMock]]:
    """Every attachment step replaced by a recorder that tags the content, with the owner-configuration read."""
    with ExitStack() as stack:
        steps: dict[str, MagicMock] = {
            name: stack.enter_context(patch(f"{TURN}.{name}", side_effect=make(name))) for name, make in _ENRICHERS.items()
        }
        stack.enter_context(patch(f"{TURN}.has_video_with_audio", return_value=False))
        steps["load_user_configs"] = stack.enter_context(
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new=AsyncMock(return_value=SimpleNamespace(personal_settings_dict={})),
            )
        )
        yield steps


def _with_media(media_type: MediaType, **overrides: object) -> InboundMessage:
    return dataclasses.replace(turn_msg("see this"), media=(MediaAttachment(media_type=media_type),), **overrides)


def _router_deciding(verdict: bool | Exception) -> AgentRouter:
    """A turn router whose access check answers ``verdict``, or raises it."""
    router = turn_router()
    check = AsyncMock(side_effect=verdict) if isinstance(verdict, Exception) else AsyncMock(return_value=verdict)
    router._resolver.is_sender_admitted = check
    return router


def _admission_checks(router: AgentRouter) -> AsyncMock:
    return cast("AsyncMock", router._resolver.is_sender_admitted)


class TestARefusedSender:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("media_type", "step"), _ATTACHMENTS)
    async def test_no_attachment_step_runs_and_the_message_goes_on_unchanged(self, media_type: MediaType, step: str) -> None:
        router = _router_deciding(False)
        message = _with_media(media_type)

        with _processing_recorded() as steps:
            await router._handle_merged(message)

        steps[step].assert_not_called()
        assert [name for name, recorder in steps.items() if recorder.called] == []
        assert prepared_message(router) == message

    @pytest.mark.asyncio
    async def test_a_sticker_is_not_described(self) -> None:
        router = _router_deciding(False)
        router._sticker_vision = MagicMock()

        with _processing_recorded() as steps:
            await router._handle_merged(turn_msg("sticker", metadata={"is_sticker": True}))

        steps["describe_sticker_inbound"].assert_not_called()
        assert prepared_message(router).content == "sticker"


class TestAnAdmittedSender:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("media_type", "step"), _ATTACHMENTS)
    async def test_the_attachment_is_processed_as_before(self, media_type: MediaType, step: str) -> None:
        router = _router_deciding(True)

        with _processing_recorded() as steps:
            await router._handle_merged(_with_media(media_type))

        steps[step].assert_called_once()
        assert prepared_message(router).content == f"see this+{step}"
        _admission_checks(router).assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_sticker_is_described(self) -> None:
        router = _router_deciding(True)
        router._sticker_vision = MagicMock()

        with _processing_recorded():
            await router._handle_merged(turn_msg("sticker", metadata={"is_sticker": True}))

        assert prepared_message(router).content == "sticker+describe_sticker_inbound"


class TestAFailingCheck:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("media_type", "step"), _ATTACHMENTS)
    async def test_still_processes_the_attachment(
        self, media_type: MediaType, step: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        router = _router_deciding(RuntimeError("policy store unavailable"))

        with caplog.at_level(logging.WARNING, logger="app.channels.routing.router"), _processing_recorded() as steps:
            await router._handle_merged(_with_media(media_type))

        steps[step].assert_called_once()
        assert prepared_message(router).content == f"see this+{step}"
        assert "Admission check failed" in caplog.text


class TestNoCheckIsNeeded:
    @pytest.mark.asyncio
    async def test_a_message_without_attachments_is_not_checked(self) -> None:
        router = _router_deciding(False)

        await router._handle_merged(turn_msg("just text"))

        _admission_checks(router).assert_not_awaited()
        assert prepared_message(router).content == "just text"

    @pytest.mark.asyncio
    async def test_the_answer_to_an_approval_is_not_checked(self) -> None:
        router = _router_deciding(False)

        with _processing_recorded():
            await router._handle_merged(_with_media(MediaType.IMAGE, resume_value={"type": "approve"}))

        _admission_checks(router).assert_not_awaited()


class _Pairing:
    """The two lookups the admission verdict makes: a member's ACTIVE pairing and the owner's ACTIVE ADMIN pairing."""

    async def resolve(self, channel: str, sender_id: str) -> str | None:
        return f"user-{sender_id}" if sender_id in {"alice", "root"} else None

    async def get_pairing_detail(self, channel: str, sender_id: str) -> tuple[PairingStatus, PairingRole, int | None] | None:
        if sender_id == "root":
            return PairingStatus.ACTIVE, PairingRole.ADMIN, None
        if sender_id == "alice":
            return PairingStatus.ACTIVE, PairingRole.MEMBER, None
        return None


class _Policy:
    """DMs need a pairing; groups are admitted only when enabled, or for a guest @mention when guest mode is on."""

    def __init__(self, *, guest_mode: bool) -> None:
        self._guest_mode = guest_mode

    async def get_dm_policy(self, channel: str) -> DmPolicy:
        return DmPolicy.PAIRING

    async def get_group_policy(self, channel: str) -> GroupPolicy:
        return GroupPolicy.ALLOWLIST

    async def get_group_trigger(self, channel: str) -> tuple[GroupTriggerMode, list[str]]:
        return GroupTriggerMode.MENTION_ONLY, []

    async def get_reaction_level(self, channel: str) -> ReactionLevel:
        return ReactionLevel.OFF

    async def get_enabled_groups(self) -> set[str]:
        return {"enabled-group"}

    async def get_guest_mode(self, channel: str) -> bool:
        return self._guest_mode

    async def get_free_response_chats(self, channel: str) -> set[str]:
        return set()

    async def get_default_user_id(self) -> str | None:
        return "owner"


def _router_with_real_policy(*, guest_mode: bool) -> AgentRouter:
    router = turn_router()
    router._resolver = PolicyResolver(
        pairing=_Pairing(),
        policy=_Policy(guest_mode=guest_mode),
        context_buffer=GroupContextBuffer(),
        fx=MagicMock(),
        get_channel=lambda _name: None,
    )
    return router


_GUEST_MENTION: dict[str, object] = {METADATA_EXPLICIT_MENTION_KEY: "1"}
_DM = {"sender_id": "mallory", "chat_id": "mallory"}
_GROUP = {"sender_id": "bob", "chat_id": "family", "is_group": True}

_SENDERS = [
    pytest.param(_DM, False, False, id="stranger-dm"),
    pytest.param({"sender_id": "alice", "chat_id": "alice"}, False, True, id="member-dm"),
    pytest.param({"sender_id": "root", "chat_id": "root"}, False, True, id="owner-dm"),
    pytest.param(_GROUP, False, False, id="group-not-enabled"),
    pytest.param({**_GROUP, "chat_id": "enabled-group"}, False, True, id="group-enabled"),
    pytest.param({**_GROUP, "metadata": _GUEST_MENTION}, True, True, id="guest-mention"),
    pytest.param({**_GROUP, "metadata": _GUEST_MENTION}, False, False, id="mention-without-guest-mode"),
]


class TestAgainstTheRealAccessPolicy:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("fields", "guest_mode", "processed"), _SENDERS)
    async def test_only_the_senders_the_policy_admits_get_their_image_processed(
        self, fields: dict[str, object], guest_mode: bool, processed: bool
    ) -> None:
        router = _router_with_real_policy(guest_mode=guest_mode)

        with _processing_recorded() as steps:
            await router._handle_merged(_with_media(MediaType.IMAGE, **fields))

        assert steps["enrich_image_inbound"].called is processed
        router._prepare_execution_context.assert_awaited_once()
