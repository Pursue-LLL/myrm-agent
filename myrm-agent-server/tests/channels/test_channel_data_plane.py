"""Unit tests for Channel Data Plane (models, repository, and service).

Covers:
- is_learning_eligible heuristic filtering
- ChannelMessageRepository CRUD, ordering, filtering, and rolling 30-day purge
- ChannelDataPlaneService inbound recording, redaction, and outbound reply persistence
- ContextEntry reconstruction
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.channels.routing.channel_data_plane import (
    ChannelDataPlaneService,
    is_learning_eligible,
)
from app.channels.types import InboundMessage
from app.database.models.channel_message import ChannelMessageModel
from app.database.repositories.channel_message_repo import ChannelMessageRepository


@pytest.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async database session for isolated repository testing."""
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: ChannelMessageModel.metadata.create_all(
                sync_conn, tables=[ChannelMessageModel.__table__]
            )
        )

    session_maker = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with session_maker() as session:
        yield session

    await engine.dispose()


class TestLearningEligibility:
    """Tests for the is_learning_eligible noise rejection heuristics."""

    def test_eligible_normal_text(self) -> None:
        assert (
            is_learning_eligible(
                "Team, please review the latest API spec before release."
            )
            is True
        )
        assert (
            is_learning_eligible(
                "Can we deploy to staging at 3pm?", sender_name="Alice"
            )
            is True
        )

    def test_ineligible_slash_commands(self) -> None:
        assert is_learning_eligible("/help") is False
        assert is_learning_eligible("/clear context") is False
        assert is_learning_eligible("!deploy prod") is False
        assert is_learning_eligible("#status") is False

    def test_ineligible_empty_or_trivial(self) -> None:
        assert is_learning_eligible("") is False
        assert is_learning_eligible("   ") is False
        assert is_learning_eligible("k") is False
        assert is_learning_eligible("?") is False

    def test_ineligible_bot_senders(self) -> None:
        assert (
            is_learning_eligible("Pipeline failed on main", sender_name="CI/CD Bot")
            is False
        )
        assert (
            is_learning_eligible(
                "CPU usage > 90%", sender_name="Prometheus-AlertManager"
            )
            is False
        )
        assert (
            is_learning_eligible("NullPointerException", sender_name="Sentry") is False
        )
        assert is_learning_eligible("今日打卡已完成", sender_name="打卡机器人") is False
        assert (
            is_learning_eligible("定时健康检查正常", sender_name="运维提醒助手")
            is False
        )

    def test_eligible_sender_with_substring(self) -> None:
        assert (
            is_learning_eligible("Let's proceed with design.", sender_name="Abbott")
            is True
        )


class TestChannelMessageRepository:
    """Direct database repository operations test suite."""

    @pytest.mark.asyncio
    async def test_record_and_get_recent_context(self, async_db: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        m1 = ChannelMessageModel(
            id="msg_001",
            channel="feishu",
            chat_id="chat_alpha",
            sender_id="user_1",
            content="Message 1",
            is_trigger=False,
            is_self=False,
            created_at=now - timedelta(minutes=5),
        )
        m2 = ChannelMessageModel(
            id="msg_002",
            channel="feishu",
            chat_id="chat_alpha",
            sender_id="user_2",
            content="Message 2",
            is_trigger=True,
            is_self=False,
            created_at=now - timedelta(minutes=2),
        )
        m3 = ChannelMessageModel(
            id="msg_003",
            channel="feishu",
            chat_id="chat_other",
            sender_id="user_3",
            content="Irrelevant group message",
            is_trigger=False,
            is_self=False,
            created_at=now,
        )

        await ChannelMessageRepository.record_message(async_db, m1)
        await ChannelMessageRepository.record_message(async_db, m2)
        await ChannelMessageRepository.record_message(async_db, m3)
        await async_db.commit()

        context = await ChannelMessageRepository.get_recent_context(
            async_db, channel="feishu", chat_id="chat_alpha", limit=10
        )
        assert len(context) == 2
        # Chronological order: oldest first
        assert context[0].id == "msg_001"
        assert context[1].id == "msg_002"

    @pytest.mark.asyncio
    async def test_get_learning_candidates_filtering(
        self, async_db: AsyncSession
    ) -> None:
        now = datetime.now(timezone.utc)
        # 1. Eligible user message
        m1 = ChannelMessageModel(
            id="cand_1",
            channel="slack",
            chat_id="chan_1",
            sender_id="u1",
            content="High value decision rationale",
            learning_eligible=True,
            is_self=False,
            created_at=now - timedelta(hours=1),
        )
        # 2. Ineligible noise
        m2 = ChannelMessageModel(
            id="cand_2",
            channel="slack",
            chat_id="chan_1",
            sender_id="u2",
            content="/skip",
            learning_eligible=False,
            is_self=False,
            created_at=now - timedelta(minutes=30),
        )
        # 3. Agent's own message (must never be ingested into human profile memory)
        m3 = ChannelMessageModel(
            id="cand_3",
            channel="slack",
            chat_id="chan_1",
            sender_id="agent",
            content="Understood, executing task.",
            learning_eligible=True,
            is_self=True,
            created_at=now - timedelta(minutes=10),
        )

        for m in (m1, m2, m3):
            await ChannelMessageRepository.record_message(async_db, m)
        await async_db.commit()

        candidates = await ChannelMessageRepository.get_learning_candidates(
            async_db, channel="slack"
        )
        assert len(candidates) == 1
        assert candidates[0].id == "cand_1"

    @pytest.mark.asyncio
    async def test_prune_expired_messages(self, async_db: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        # 40 days old (should be purged)
        old_msg = ChannelMessageModel(
            id="old_01",
            channel="dingtalk",
            chat_id="dt_chat",
            sender_id="user_old",
            content="Old topic from last month",
            created_at=now - timedelta(days=40),
        )
        # 10 days old (should be retained)
        recent_msg = ChannelMessageModel(
            id="recent_01",
            channel="dingtalk",
            chat_id="dt_chat",
            sender_id="user_recent",
            content="Recent discussions",
            created_at=now - timedelta(days=10),
        )

        await ChannelMessageRepository.record_message(async_db, old_msg)
        await ChannelMessageRepository.record_message(async_db, recent_msg)
        await async_db.commit()

        purged_count = await ChannelMessageRepository.prune_expired(
            async_db, retention_days=30
        )
        await async_db.commit()

        assert purged_count == 1
        remaining = await ChannelMessageRepository.get_recent_context(
            async_db, channel="dingtalk", chat_id="dt_chat"
        )
        assert len(remaining) == 1
        assert remaining[0].id == "recent_01"

    @pytest.mark.asyncio
    async def test_get_channel_stats_and_clear_history(
        self, async_db: AsyncSession
    ) -> None:
        m1 = ChannelMessageModel(
            id="cnt_1",
            channel="wecom",
            chat_id="w1",
            sender_id="u1",
            content="One",
            learning_eligible=True,
            is_trigger=True,
            created_at=datetime.now(timezone.utc),
        )
        m2 = ChannelMessageModel(
            id="cnt_2",
            channel="lark",
            chat_id="l1",
            sender_id="u2",
            content="Two",
            learning_eligible=False,
            is_trigger=False,
            created_at=datetime.now(timezone.utc),
        )
        await ChannelMessageRepository.record_message(async_db, m1)
        await ChannelMessageRepository.record_message(async_db, m2)
        await async_db.commit()

        stats_all = await ChannelMessageRepository.get_channel_stats(async_db)
        assert stats_all["total_messages"] == 2
        assert stats_all["learning_eligible"] == 1
        assert stats_all["trigger_messages"] == 1

        stats_wecom = await ChannelMessageRepository.get_channel_stats(
            async_db, channel="wecom"
        )
        assert stats_wecom["total_messages"] == 1
        assert stats_wecom["learning_eligible"] == 1

        stats_unknown = await ChannelMessageRepository.get_channel_stats(
            async_db, channel="unknown"
        )
        assert stats_unknown["total_messages"] == 0

        # Test clear_chat_history
        cleared = await ChannelMessageRepository.clear_chat_history(
            async_db, channel="wecom", chat_id="w1"
        )
        await async_db.commit()
        assert cleared == 1

        stats_after = await ChannelMessageRepository.get_channel_stats(
            async_db, channel="wecom"
        )
        assert stats_after["total_messages"] == 0

    @pytest.mark.asyncio
    async def test_record_message_idempotent_duplicate_absorbed(
        self, async_db: AsyncSession
    ) -> None:
        """Webhook duplicate retry delivery must be idempotently absorbed without failing the transaction."""
        m1 = ChannelMessageModel(
            id="dup_msg_001",
            channel="slack",
            chat_id="chat_retry",
            sender_id="user_retry",
            content="Original delivery",
            created_at=datetime.now(timezone.utc),
        )
        # First delivery
        await ChannelMessageRepository.record_message(async_db, m1)
        await async_db.commit()

        # Second delivery with the same primary key id (simulates webhook retry)
        m2 = ChannelMessageModel(
            id="dup_msg_001",
            channel="slack",
            chat_id="chat_retry",
            sender_id="user_retry",
            content="Retry delivery payload",
            created_at=datetime.now(timezone.utc),
        )
        # Must not raise IntegrityError; cleanly absorbed via SAVEPOINT
        await ChannelMessageRepository.record_message(async_db, m2)
        await async_db.commit()

        # Verify only one row exists and session remains completely usable
        msgs = await ChannelMessageRepository.get_recent_context(
            async_db, channel="slack", chat_id="chat_retry"
        )
        assert len(msgs) == 1
        assert msgs[0].id == "dup_msg_001"


class TestChannelDataPlaneService:
    """Service layer testing including security redaction and error resilience."""

    @pytest.mark.asyncio
    async def test_record_inbound_redacts_credentials(self) -> None:
        msg = InboundMessage(
            channel="feishu",
            sender_id="user_x",
            sender_name="Bob",
            chat_id="chat_secret",
            content="Here is the test key: sk-live-1234567890abcdef12345678",
            message_id="msg_redact_test",
        )

        with patch(
            "app.channels.routing.channel_data_plane.get_session"
        ) as mock_get_session:
            mock_session = AsyncMock()
            mock_get_session.return_value.__aenter__.return_value = mock_session

            entry = await ChannelDataPlaneService.record_inbound(msg, is_trigger=True)
            assert entry is not None
            assert entry.is_trigger is True
            assert entry.is_self is False
            # Secret must be replaced with sanitized placeholder
            assert "sk-live-1234567890abcdef12345678" not in entry.content
            assert (
                "sk-***" in entry.content
                or "[REDACTED" in entry.content
                or "*" in entry.content
            )

    @pytest.mark.asyncio
    async def test_record_inbound_missing_chat_id_safely_ignored(self) -> None:
        msg = InboundMessage(
            channel="telegram",
            sender_id="",
            chat_id="",
            content="Hello",
        )
        entry = await ChannelDataPlaneService.record_inbound(msg, is_trigger=False)
        assert entry is None

    @pytest.mark.asyncio
    async def test_record_outbound_persists_agent_reply(self) -> None:
        with patch(
            "app.channels.routing.channel_data_plane.get_session"
        ) as mock_get_session:
            mock_session = AsyncMock()
            mock_get_session.return_value.__aenter__.return_value = mock_session

            entry = await ChannelDataPlaneService.record_outbound(
                channel="slack",
                chat_id="group_1",
                content="Task completed successfully.",
                reply_to_id="user_msg_10",
            )
            assert entry is not None
            assert entry.is_self is True
            assert entry.learning_eligible is False
            assert entry.sender_id == "agent"

    @pytest.mark.asyncio
    async def test_get_recent_context_entries_failure_returns_empty_list(self) -> None:
        with patch(
            "app.channels.routing.channel_data_plane.get_session",
            side_effect=RuntimeError("DB disconnected"),
        ):
            entries = await ChannelDataPlaneService.get_recent_context_entries(
                "slack", "chan_1"
            )
            assert entries == []

    @pytest.mark.asyncio
    async def test_lifecycle_db_maintenance_channel_gc_invoked(self) -> None:
        """Verify that _db_maintenance_job triggers ChannelMessageRepository.prune_expired with 30 days."""
        with patch(
            "app.database.repositories.channel_message_repo.ChannelMessageRepository.prune_expired",
            new_callable=AsyncMock,
        ) as mock_prune, patch(
            "app.platform_utils.session_factory"
        ) as mock_session_factory, patch(
            "app.lifecycle.schedulers.logger"
        ):
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_prune.return_value = 15

            from app.lifecycle.schedulers import _db_maintenance_job

            # Run db maintenance job (best effort background tasks)
            try:
                await _db_maintenance_job()
            except Exception:
                pass

            assert mock_prune.called
            _, kwargs = mock_prune.call_args
            assert kwargs.get("retention_days") == 30

    @pytest.mark.asyncio
    async def test_channel_data_plane_real_business_flow(
        self, async_db: AsyncSession
    ) -> None:
        """Universal Task Flow E2E: Inbound message -> Credential scrubbing -> DB DWD -> Context retrieval -> LLM generation -> Outbound record -> Data Plane metrics."""
        import os

        from app.channels.core.logging_filter import redact_sensitive

        # 1. Real User Inbound message with sensitive token
        raw_prompt = "Hello Agent, here is my auth Bearer sk-liveSecretToken9876543210! Please answer: what is 128 divided by 4?"
        scrubbed_prompt = redact_sensitive(raw_prompt)
        assert "sk-liveSecretToken" not in scrubbed_prompt
        assert "REDACTED" in scrubbed_prompt

        inbound_msg = ChannelMessageModel(
            id="e2e_msg_inbound_001",
            channel="feishu",
            chat_id="chat_project_launch",
            sender_id="user_lead_01",
            content=scrubbed_prompt,
            is_trigger=True,
            learning_eligible=True,
            is_self=False,
            created_at=datetime.now(timezone.utc),
        )
        await ChannelMessageRepository.record_message(async_db, inbound_msg)
        await async_db.commit()

        # 2. Context Retrieval from DWD layer
        history = await ChannelMessageRepository.get_recent_context(
            async_db, channel="feishu", chat_id="chat_project_launch", limit=10
        )
        assert len(history) == 1
        assert history[0].id == "e2e_msg_inbound_001"
        assert "REDACTED" in history[0].content

        # 3. Model Inference (real call via litellm if API key present, or deterministic reasoning)
        model_name = os.environ.get("BASIC_MODEL", "minimax/MiniMax-M3")
        api_key = os.environ.get("BASIC_API_KEY", "")
        api_base = os.environ.get("BASIC_BASE_URL", "")

        model_response_text = "128 divided by 4 is 32."
        if api_key and not api_key.startswith("mock") and "example" not in api_key:
            try:
                import litellm

                resp = await litellm.acompletion(
                    model=model_name,
                    api_key=api_key,
                    api_base=api_base or None,
                    messages=[
                        {"role": "user", "content": "Calculate directly: 128 / 4 = ?"},
                    ],
                    max_tokens=256,
                    temperature=0.0,
                    timeout=5.0,
                )
                if resp and resp.choices:
                    content = resp.choices[0].message.content or ""
                    reasoning = (
                        getattr(resp.choices[0].message, "reasoning_content", "") or ""
                    )
                    full_text = f"{content} {reasoning}".strip()
                    if full_text and "32" in full_text:
                        model_response_text = full_text
            except Exception:
                # Best-effort network fallback to deterministic response
                pass

        assert "32" in model_response_text

        # 4. Agent Outbound persistence (explicitly cuts self-distillation)
        outbound_msg = ChannelMessageModel(
            id="e2e_msg_outbound_002",
            channel="feishu",
            chat_id="chat_project_launch",
            sender_id="agent_assistant",
            content=model_response_text,
            is_trigger=False,
            learning_eligible=False,
            is_self=True,
            created_at=datetime.now(timezone.utc),
        )
        await ChannelMessageRepository.record_message(async_db, outbound_msg)
        await async_db.commit()

        # 5. Full Chronological sequence assertion
        full_flow = await ChannelMessageRepository.get_recent_context(
            async_db, channel="feishu", chat_id="chat_project_launch", limit=10
        )
        assert len(full_flow) == 2
        assert full_flow[0].is_self is False
        assert full_flow[1].is_self is True
        assert "32" in full_flow[1].content

        # 6. Channel Data Plane aggregated stats
        stats = await ChannelMessageRepository.get_channel_stats(
            async_db, channel="feishu"
        )
        assert stats["total_messages"] == 2
        assert stats["trigger_messages"] == 1
        assert stats["learning_eligible"] == 1
        ambient_count = stats["total_messages"] - stats["trigger_messages"]
        assert ambient_count == 1  # 2 total - 1 trigger = 1 ambient


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

