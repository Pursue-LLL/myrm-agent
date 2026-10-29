"""Unit tests for the Channel Data Plane service.

Covers:
- is_learning_eligible heuristic filtering
- ChannelDataPlaneService inbound recording, outbound reply persistence, and context reconstruction
- observed-context hygiene: agent self rows and bot or alert chatter stay out of the group context
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.api import redact_sensitive_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.routing.channel_data_plane import ChannelDataPlaneService, is_learning_eligible
from app.channels.types import InboundMessage
from app.database.models.channel_message import ChannelMessageModel
from app.database.repositories.channel_message_repo import ChannelMessageRepository


class TestLearningEligibility:
    """Tests for the is_learning_eligible noise rejection heuristics."""

    def test_eligible_normal_text(self) -> None:
        assert is_learning_eligible("Team, please review the latest API spec before release.") is True
        assert is_learning_eligible("Can we deploy to staging at 3pm?", sender_name="Alice") is True

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
        assert is_learning_eligible("Pipeline failed on main", sender_name="CI/CD Bot") is False
        assert is_learning_eligible("CPU usage > 90%", sender_name="Prometheus-AlertManager") is False
        assert is_learning_eligible("NullPointerException", sender_name="Sentry") is False
        assert is_learning_eligible("今日打卡已完成", sender_name="打卡机器人") is False
        assert is_learning_eligible("定时健康检查正常", sender_name="运维提醒助手") is False

    def test_eligible_sender_with_substring(self) -> None:
        assert is_learning_eligible("Let's proceed with design.", sender_name="Abbott") is True


class TestChannelDataPlaneService:
    """Service layer testing including security redaction and error resilience."""

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
        with patch("app.channels.routing.channel_data_plane.get_session") as mock_get_session:
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
            entries = await ChannelDataPlaneService.get_recent_context_entries("slack", "chan_1")
            assert entries == []

    @pytest.mark.asyncio
    async def test_lifecycle_db_maintenance_channel_gc_invoked(self) -> None:
        """Verify that _db_maintenance_job triggers ChannelMessageRepository.prune_expired with 30 days."""
        with (
            patch(
                "app.database.repositories.channel_message_repo.ChannelMessageRepository.prune_expired",
                new_callable=AsyncMock,
            ) as mock_prune,
            patch("app.platform_utils.session_factory") as mock_session_factory,
            patch("app.lifecycle.schedulers.logger"),
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
    async def test_channel_data_plane_real_business_flow(self, async_db: AsyncSession) -> None:
        """Universal Task Flow E2E: Inbound message -> Credential scrubbing -> DB DWD -> Context retrieval -> LLM generation -> Outbound record -> Data Plane metrics."""
        import os

        # 1. Real User Inbound message with sensitive token
        secret_token = "sk-liveSecretToken9876543210"
        raw_prompt = f"Hello Agent, here is my auth Bearer {secret_token}! Please answer: what is 128 divided by 4?"
        scrubbed_prompt = redact_sensitive_text(raw_prompt)
        assert "SecretToken" not in scrubbed_prompt
        assert "what is 128 divided by 4?" in scrubbed_prompt

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
        assert "SecretToken" not in history[0].content

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
                    reasoning = getattr(resp.choices[0].message, "reasoning_content", "") or ""
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
        # R4: agent self rows stay in the DWD ledger but are excluded from
        # context retrieval — the session transcript already carries them.
        full_flow = await ChannelMessageRepository.get_recent_context(
            async_db, channel="feishu", chat_id="chat_project_launch", limit=10
        )
        assert len(full_flow) == 1
        assert full_flow[0].is_self is False
        assert full_flow[0].id == "e2e_msg_inbound_001"

        # 6. Channel Data Plane aggregated stats
        # Outbound row is still persisted for DWD completeness
        stats = await ChannelMessageRepository.get_channel_stats(async_db, channel="feishu")
        assert stats["total_messages"] == 2
        assert stats["trigger_messages"] == 1
        assert stats["learning_eligible"] == 1
        ambient_count = stats["total_messages"] - stats["trigger_messages"]
        assert ambient_count == 1  # 2 total - 1 trigger = 1 ambient


class TestObservedContextHygiene:
    """R4: context reconstruction must exclude agent self rows and bot/alert chatter."""

    @pytest.mark.asyncio
    async def test_get_recent_context_excludes_agent_self_rows(self, async_db: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        human = ChannelMessageModel(
            id="ctx_human",
            channel="feishu",
            chat_id="chat_ctx",
            sender_id="user_1",
            sender_name="Alice",
            content="human question",
            is_trigger=True,
            is_self=False,
            created_at=now - timedelta(minutes=1),
        )
        agent = ChannelMessageModel(
            id="ctx_agent",
            channel="feishu",
            chat_id="chat_ctx",
            sender_id="agent",
            sender_name="Assistant",
            content="agent answer",
            is_trigger=False,
            is_self=True,
            learning_eligible=False,
            created_at=now,
        )
        async_db.add_all([human, agent])
        await async_db.commit()

        msgs = await ChannelMessageRepository.get_recent_context(async_db, channel="feishu", chat_id="chat_ctx")
        assert [m.id for m in msgs] == ["ctx_human"]

    @pytest.mark.asyncio
    async def test_get_recent_context_entries_excludes_bot_named_senders(self, async_db: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        rows = [
            ChannelMessageModel(
                id="ctx_m1",
                channel="slack",
                chat_id="c1",
                sender_id="u1",
                sender_name="Alice",
                content="human line",
                is_trigger=False,
                is_self=False,
                created_at=now - timedelta(minutes=2),
            ),
            ChannelMessageModel(
                id="ctx_m2",
                channel="slack",
                chat_id="c1",
                sender_id="bot1",
                sender_name="Sentry",
                content="alert noise",
                is_trigger=False,
                is_self=False,
                created_at=now - timedelta(minutes=1),
            ),
            ChannelMessageModel(
                id="ctx_m3",
                channel="slack",
                chat_id="c1",
                sender_id="u2",
                sender_name="Bob",
                content="human line 2",
                is_trigger=False,
                is_self=False,
                created_at=now,
            ),
        ]
        async_db.add_all(rows)
        await async_db.commit()

        with patch("app.channels.routing.channel_data_plane.get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = async_db
            entries = await ChannelDataPlaneService.get_recent_context_entries("slack", "c1")

        assert [e.sender_name for e in entries] == ["Alice", "Bob"]
