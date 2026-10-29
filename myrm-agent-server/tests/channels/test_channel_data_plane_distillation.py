"""Unit tests for bridging a ledger row to a Harness DistillationCandidate: which rows are admitted and why each
other row is rejected.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.channels.routing.channel_data_plane import ChannelDataPlaneService
from app.database.models.channel_message import ChannelMessageModel


class TestToDistillationCandidate:
    """Tests for bridging ChannelMessageModel to Harness DistillationCandidate."""

    def test_user_self_candidate_admitted(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.distillation_guards import (
            DistillationOrigin,
            SelfIdentityState,
            check_distillable,
        )

        msg = ChannelMessageModel(
            id="msg_user_1",
            channel="slack",
            chat_id="dm_100",
            sender_id="usr_alice",
            sender_name="Alice",
            content="I prefer TypeScript over pure JavaScript.",
            is_trigger=True,
            is_self=True,
            is_group=False,
            learning_eligible=True,
            created_at=datetime.now(timezone.utc),
        )
        candidate = ChannelDataPlaneService.to_distillation_candidate(msg)
        assert candidate.origin == DistillationOrigin.USER
        assert candidate.is_self == SelfIdentityState.SELF
        assert candidate.is_bot_or_alert is False
        assert len(candidate.evidence) == 1
        assert candidate.evidence[0].source_id == "channel:slack:dm_100"
        assert candidate.evidence[0].message_id == "msg_user_1"

        res = check_distillable(candidate)
        assert res.allowed is True

    def test_agent_outbound_permanently_rejected(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.distillation_guards import (
            DistillationOrigin,
            DistillationRejectionCode,
            SelfIdentityState,
            check_distillable,
        )

        msg = ChannelMessageModel(
            id="out_msg_1",
            channel="slack",
            chat_id="dm_100",
            sender_id="agent",
            sender_name="Assistant",
            content="I suggest configuring strict typing in tsconfig.json.",
            is_trigger=False,
            is_self=True,
            is_group=False,
            learning_eligible=False,
            created_at=datetime.now(timezone.utc),
        )
        candidate = ChannelDataPlaneService.to_distillation_candidate(msg)
        assert candidate.origin == DistillationOrigin.AGENT
        assert candidate.is_self == SelfIdentityState.OTHER

        res = check_distillable(candidate)
        assert res.allowed is False
        assert res.rejection_code == DistillationRejectionCode.REJECT_ORIGIN_AGENT

    def test_group_third_party_rejected_as_other(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.distillation_guards import (
            DistillationOrigin,
            DistillationRejectionCode,
            SelfIdentityState,
            check_distillable,
        )

        msg = ChannelMessageModel(
            id="msg_group_1",
            channel="feishu",
            chat_id="group_rnd",
            sender_id="usr_bob",
            sender_name="Bob",
            content="I think we should migrate the database tonight.",
            is_trigger=False,
            is_self=False,
            is_group=True,
            learning_eligible=True,
            created_at=datetime.now(timezone.utc),
        )
        candidate = ChannelDataPlaneService.to_distillation_candidate(msg)
        assert candidate.origin == DistillationOrigin.USER
        assert candidate.is_self == SelfIdentityState.OTHER

        res = check_distillable(candidate)
        assert res.allowed is False
        assert res.rejection_code == DistillationRejectionCode.REJECT_IDENTITY_OTHER

    def test_unconfirmed_private_speaker_rejected_as_unconfirmed(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.distillation_guards import (
            DistillationOrigin,
            DistillationRejectionCode,
            SelfIdentityState,
            check_distillable,
        )

        msg = ChannelMessageModel(
            id="msg_guest_1",
            channel="webchat",
            chat_id="guest_session",
            sender_id="anon_guest",
            content="My favorite color is blue.",
            is_trigger=True,
            is_self=False,
            is_group=False,
            learning_eligible=True,
            created_at=datetime.now(timezone.utc),
        )
        candidate = ChannelDataPlaneService.to_distillation_candidate(msg)
        assert candidate.origin == DistillationOrigin.USER
        assert candidate.is_self == SelfIdentityState.UNCONFIRMED

        res = check_distillable(candidate)
        assert res.allowed is False
        assert res.rejection_code == DistillationRejectionCode.REJECT_IDENTITY_UNCONFIRMED

    def test_bot_alert_rejected(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.distillation_guards import (
            DistillationRejectionCode,
            check_distillable,
        )

        msg = ChannelMessageModel(
            id="msg_alert_1",
            channel="slack",
            chat_id="alerts_channel",
            sender_id="sentry_bot",
            sender_name="SentryBot",
            content="Unhandled TypeError in server loop.",
            is_trigger=False,
            is_self=False,
            is_group=True,
            learning_eligible=False,
            created_at=datetime.now(timezone.utc),
        )
        candidate = ChannelDataPlaneService.to_distillation_candidate(msg)
        assert candidate.is_bot_or_alert is True

        res = check_distillable(candidate)
        assert res.allowed is False
        assert res.rejection_code in (
            DistillationRejectionCode.REJECT_BOT_OR_ALERT,
            DistillationRejectionCode.REJECT_IDENTITY_OTHER,
        )
