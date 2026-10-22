"""[INPUT] RegisterBotRequest, SendBotMessageRequest, DispatchMentionsRequest, session_id.
[OUTPUT] BotModeService providing Named Bot Roster registration, peer-to-peer mailbox, and @mention dispatch.
[POS] Service layer for Bot Mode Named Profile Roster & Inter-Bot Mailbox Protocol (Item 33).
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.coordination.bot_mode import (
    BotMessage,
    BotProfile,
    BotStatus,
    InterBotMailboxRelay,
    MentionDispatchResult,
    MessagePriority,
)

from app.schemas.bot_mode import (
    BotInboxResponse,
    BotMessageDTO,
    BotProfileDTO,
    BotRosterListResponse,
    BotStatusEnum,
    DispatchMentionsRequest,
    MentionDispatchResultDTO,
    MessagePriorityEnum,
    RegisterBotRequest,
    ScalarPayload,
    SendBotMessageRequest,
    UpdateBotStatusRequest,
)

logger = logging.getLogger(__name__)


def _to_profile_dto(profile: BotProfile) -> BotProfileDTO:
    return BotProfileDTO(
        bot_id=profile.bot_id,
        handle=profile.handle,
        display_name=profile.display_name,
        role_description=profile.role_description,
        avatar_seed=profile.avatar_seed,
        model_tier=profile.model_tier,
        skills=list(profile.skills),
        tools=list(profile.tools),
        status=BotStatusEnum(profile.status.value),
        active_task_id=profile.active_task_id,
        created_at=profile.created_at,
    )


def _to_message_dto(msg: BotMessage) -> BotMessageDTO:
    return BotMessageDTO(
        message_id=msg.message_id,
        from_bot=msg.from_bot,
        to_bot=msg.to_bot,
        thread_id=msg.thread_id,
        subject=msg.subject,
        body=msg.body,
        priority=MessagePriorityEnum(msg.priority.value),
        task_payload=dict(msg.task_payload),
        is_read=msg.is_read,
        timestamp=msg.timestamp,
    )


def _to_dispatch_dto(result: MentionDispatchResult) -> MentionDispatchResultDTO:
    return MentionDispatchResultDTO(
        dispatched=result.dispatched,
        target_bot_id=result.target_bot_id,
        target_handle=result.target_handle,
        message_id=result.message_id,
        note=result.note,
    )


class BotModeService:
    """Service coordinator managing named AI colleague workstations and mailbox relay."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._relays: dict[str, InterBotMailboxRelay] = {}

    def _get_relay(self, session_id: str) -> InterBotMailboxRelay:
        with self._lock:
            relay = self._relays.get(session_id)
            if not relay:
                relay = InterBotMailboxRelay()
                self._relays[session_id] = relay
            return relay

    def register_bot(
        self,
        session_id: str,
        req: RegisterBotRequest,
    ) -> BotProfileDTO:
        """Register or update a named AI colleague profile in the workstation roster."""
        relay = self._get_relay(session_id)
        status = BotStatus(req.status.value)
        profile = BotProfile(
            bot_id=req.bot_id,
            handle=req.handle,
            display_name=req.display_name,
            role_description=req.role_description,
            avatar_seed=req.avatar_seed,
            model_tier=req.model_tier,
            skills=tuple(req.skills),
            tools=tuple(req.tools),
            status=status,
        )
        relay.roster.register_bot(profile)
        # Fetch the normalized profile from the roster
        stored = relay.roster.get_bot_by_id(profile.bot_id)
        if not stored:
            stored = profile
        logger.info(
            "Registered bot '%s' (@%s) in session '%s'",
            stored.bot_id,
            stored.handle,
            session_id,
        )
        return _to_profile_dto(stored)

    def get_bot(self, session_id: str, bot_id: str) -> BotProfileDTO | None:
        """Fetch bot profile by bot_id or handle."""
        relay = self._get_relay(session_id)
        profile = relay.roster.resolve_mention(bot_id)
        if not profile:
            return None
        return _to_profile_dto(profile)

    def list_bots(
        self,
        session_id: str,
        status_filter: BotStatusEnum | None = None,
    ) -> BotRosterListResponse:
        """List all registered AI colleague workstations in the given session."""
        relay = self._get_relay(session_id)
        filter_status = BotStatus(status_filter.value) if status_filter else None
        bots = relay.roster.list_bots(status_filter=filter_status)
        dtos = [_to_profile_dto(b) for b in bots]
        return BotRosterListResponse(bots=dtos, total_count=len(dtos))

    def update_bot_status(
        self,
        session_id: str,
        bot_id: str,
        req: UpdateBotStatusRequest,
    ) -> BotProfileDTO | None:
        """Update active availability status of a bot workstation."""
        relay = self._get_relay(session_id)
        success = relay.roster.update_status(
            bot_id=bot_id,
            status=BotStatus(req.status.value),
            active_task_id=req.active_task_id,
        )
        if not success:
            return None
        updated = relay.roster.get_bot_by_id(bot_id)
        return _to_profile_dto(updated) if updated else None

    def send_message(
        self,
        session_id: str,
        req: SendBotMessageRequest,
    ) -> BotMessageDTO:
        """Deliver a direct message from one bot to another via mailbox relay."""
        relay = self._get_relay(session_id)
        scalar_payload: dict[str, ScalarPayload] = dict(req.task_payload)
        msg = relay.send_message(
            from_bot=req.from_bot,
            to_bot=req.to_bot,
            subject=req.subject,
            body=req.body,
            priority=MessagePriority(req.priority.value),
            task_payload=scalar_payload,  # type: ignore[arg-type]
            thread_id=req.thread_id,
        )
        return _to_message_dto(msg)

    def dispatch_mentions(
        self,
        session_id: str,
        req: DispatchMentionsRequest,
    ) -> list[MentionDispatchResultDTO]:
        """Parse text for @mentions and dispatch to all matching bot workstations."""
        relay = self._get_relay(session_id)
        scalar_payload: dict[str, ScalarPayload] = dict(req.task_payload)
        results = relay.dispatch_mentions(
            text=req.text,
            from_bot=req.from_bot,
            thread_id=req.thread_id,
            task_payload=scalar_payload,  # type: ignore[arg-type]
        )
        return [_to_dispatch_dto(r) for r in results]

    def get_inbox(
        self,
        session_id: str,
        bot_id: str,
        unread_only: bool = False,
    ) -> BotInboxResponse | None:
        """Retrieve incoming messages for a bot workstation."""
        relay = self._get_relay(session_id)
        profile = relay.roster.resolve_mention(bot_id)
        if not profile:
            return None

        messages = relay.get_inbox(profile.bot_id, unread_only=unread_only)
        all_msgs = relay.get_inbox(profile.bot_id, unread_only=False)
        unread_count = relay.get_unread_count(profile.bot_id)

        return BotInboxResponse(
            bot_id=profile.bot_id,
            handle=profile.handle,
            unread_count=unread_count,
            total_count=len(all_msgs),
            messages=[_to_message_dto(m) for m in messages],
        )

    def mark_as_read(
        self,
        session_id: str,
        bot_id: str,
        message_ids: list[str],
    ) -> int:
        """Mark specific incoming messages as read."""
        relay = self._get_relay(session_id)
        return relay.mark_as_read(bot_id=bot_id, message_ids=tuple(message_ids))

    def clear_mailbox(self, session_id: str, bot_id: str) -> None:
        """Clear mailbox messages for a bot in the session."""
        relay = self._get_relay(session_id)
        relay.clear_mailbox(bot_id=bot_id)

    def reset_session(self, session_id: str) -> None:
        """Reset all roster and mailbox state for a given session."""
        with self._lock:
            relay = self._relays.pop(session_id, None)
            if relay:
                relay.reset_all()
                relay.roster.clear()


# Global singleton instance
_bot_mode_service = BotModeService()


def get_bot_mode_service() -> BotModeService:
    """Get the singleton instance of BotModeService."""
    return _bot_mode_service
