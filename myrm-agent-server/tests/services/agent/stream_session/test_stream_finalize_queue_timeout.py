"""Tests for structured AgentQueueTimeout error rendering in stream_finalize."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import orjson
import pytest
from myrm_agent_harness.agent.config.exceptions import ConfigIncompleteError
from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError
from myrm_agent_harness.toolkits.llms.errors.error_types import FailoverReason

from app.services.agent.gateway import (
    AgentBusyError,
    AgentDrainingError,
    AgentExecutionTimeout,
    AgentQueueTimeout,
)
from app.services.agent.params.models import TurnCapabilityTelemetryRequest
from app.services.agent.stream_session import stream_finalize
from app.services.agent.stream_session.stream_session_types import AgentStreamSession


def _make_session(locale: str | None = None) -> AgentStreamSession:
    session = cast(AgentStreamSession, MagicMock(spec=AgentStreamSession))
    session.params = MagicMock(message_id="msg-1", locale=locale)
    session.request = MagicMock(chat_id=None, turn_capability_telemetry=None)
    session.collector = MagicMock()
    session.had_fatal_error = False
    session.turn_capability_terminal_recorded = False
    return session


async def _collect_payload(
    exc: AgentQueueTimeout, locale: str | None = None
) -> dict[str, object]:
    session = _make_session(locale)
    chunks = [
        chunk
        async for chunk in stream_finalize.yield_stream_exception_chunks(session, exc)
    ]
    assert len(chunks) == 1
    raw = chunks[0]
    assert raw.startswith("data: ")
    return cast(dict[str, object], orjson.loads(raw[len("data: ") :]))


class TestQueueTimeoutStructuredError:
    @pytest.mark.asyncio
    async def test_user_limit_zh(self) -> None:
        exc = AgentQueueTimeout(
            "Queue timeout (10s) — user concurrency limit reached (3 active)",
            reason="user_limit",
            active_sessions=[
                {"chatId": "chat-a", "agentType": "general", "elapsedSeconds": 12.5},
                {"chatId": "chat-b", "agentType": "general", "elapsedSeconds": 3.2},
            ],
        )
        payload = await _collect_payload(exc, "zh-CN")
        assert payload["type"] == "error"
        assert payload["error_kind"] == "concurrency_limit"
        diag = payload["diagnostic_result"]
        assert isinstance(diag, dict)
        assert diag["error_type"] == "concurrency_limit"
        assert diag["locale"] == "zh"
        assert "并发会话已达上限" in str(diag["user_message"])
        assert "chat-a" in str(diag["user_message"])
        assert isinstance(diag["resolution_steps"], list)
        assert len(diag["resolution_steps"]) == 2

    @pytest.mark.asyncio
    async def test_user_limit_en(self) -> None:
        exc = AgentQueueTimeout(
            "Queue timeout (10s)",
            reason="user_limit",
            active_sessions=[
                {"chatId": "chat-a", "agentType": "general", "elapsedSeconds": 5.0}
            ],
        )
        payload = await _collect_payload(exc, "en-US")
        diag = payload["diagnostic_result"]
        assert isinstance(diag, dict)
        assert diag["locale"] == "en"
        assert "Concurrency limit reached" in str(diag["user_message"])
        assert "chat-a" in str(diag["user_message"])

    @pytest.mark.asyncio
    async def test_memory_pressure(self) -> None:
        exc = AgentQueueTimeout(
            "Queue timeout (10s) — Memory pressure (CRITICAL)",
            reason="memory_pressure",
        )
        payload = await _collect_payload(exc, "zh-CN")
        diag = payload["diagnostic_result"]
        assert isinstance(diag, dict)
        assert "内存压力" in str(diag["user_message"])

    @pytest.mark.asyncio
    async def test_global_limit_no_holders(self) -> None:
        exc = AgentQueueTimeout(
            "Queue timeout (10s) — active=20/20",
            reason="global_limit",
            active_sessions=[],
        )
        payload = await _collect_payload(exc, None)
        diag = payload["diagnostic_result"]
        assert isinstance(diag, dict)
        assert diag["locale"] == "en"
        assert "Server is busy" in str(diag["user_message"])

    @pytest.mark.asyncio
    async def test_holders_truncated_at_three(self) -> None:
        exc = AgentQueueTimeout(
            "Queue timeout (10s)",
            reason="global_limit",
            active_sessions=[
                {"chatId": f"chat-{i}", "agentType": "general", "elapsedSeconds": 1.0}
                for i in range(5)
            ],
        )
        payload = await _collect_payload(exc, "en")
        diag = payload["diagnostic_result"]
        assert isinstance(diag, dict)
        assert "chat-0" in str(diag["user_message"])
        assert "+2 more" in str(diag["user_message"])

    @pytest.mark.asyncio
    async def test_holders_truncated_zh_suffix(self) -> None:
        exc = AgentQueueTimeout(
            "Queue timeout (10s)",
            reason="global_limit",
            active_sessions=[
                {"chatId": f"chat-{i}", "agentType": "general", "elapsedSeconds": 1.0}
                for i in range(5)
            ],
        )
        payload = await _collect_payload(exc, "zh")
        diag = payload["diagnostic_result"]
        assert isinstance(diag, dict)
        assert "chat-0" in str(diag["user_message"])
        assert "等 2 个会话" in str(diag["user_message"])


class TestExceptionChunkBranches:
    """Cover the remaining error branches of yield_stream_exception_chunks."""

    @staticmethod
    async def _chunks(
        exc: BaseException,
        locale: str | None = None,
        session: AgentStreamSession | None = None,
    ) -> list[str]:
        session = session or _make_session(locale)
        return [
            chunk
            async for chunk in stream_finalize.yield_stream_exception_chunks(session, exc)
        ]

    @staticmethod
    def _decode(raw: str) -> dict[str, object]:
        assert raw.startswith("data: ")
        return cast(dict[str, object], orjson.loads(raw[len("data: ") :]))

    @pytest.mark.asyncio
    async def test_value_error_resume_failed_clears_checkpoint(self) -> None:
        session = _make_session()
        session.request.chat_id = "chat-resume"
        cp = AsyncMock()
        with patch("app.platform_utils.get_checkpointer", return_value=cp):
            raw = (await self._chunks(ValueError("Resume failed: bad state"), session=session))[0]
        payload = self._decode(raw)
        assert payload["data"] == "Resume failed: Resume failed: bad state"
        assert session.had_fatal_error is True
        assert cp.adelete_thread.await_count == 2

    @pytest.mark.asyncio
    async def test_value_error_context_overflow_clears_checkpoint(self) -> None:
        session = _make_session()
        session.request.chat_id = "chat-overflow"
        cp = AsyncMock()
        with patch("app.platform_utils.get_checkpointer", return_value=cp):
            raw = (await self._chunks(ValueError("context overflow: too long"), session=session))[0]
        payload = self._decode(raw)
        assert "Resume failed" in str(payload["data"])
        assert session.had_fatal_error is True
        assert cp.adelete_thread.await_count == 2

    @pytest.mark.asyncio
    async def test_value_error_generic_agent_error(self) -> None:
        raw = (await self._chunks(ValueError("boom")))[0]
        payload = self._decode(raw)
        assert payload["data"] == "Agent error: boom"

    @pytest.mark.asyncio
    async def test_agent_draining_error(self) -> None:
        raw = (await self._chunks(AgentDrainingError("draining")))[0]
        payload = self._decode(raw)
        assert "restarting" in str(payload["data"])

    @pytest.mark.asyncio
    async def test_agent_execution_timeout(self) -> None:
        raw = (await self._chunks(AgentExecutionTimeout("slow")))[0]
        payload = self._decode(raw)
        assert "timed out" in str(payload["data"]).lower()

    @pytest.mark.asyncio
    async def test_agent_busy_error(self) -> None:
        raw = (await self._chunks(AgentBusyError("busy")))[0]
        payload = self._decode(raw)
        assert payload["error_type"] == "AgentBusyError"
        assert payload["status_code"] == 409

    @pytest.mark.asyncio
    async def test_config_incomplete_error_zh(self) -> None:
        exc = ConfigIncompleteError(
            user_friendly_message={
                "en": "Model is not configured.",
                "zh": "模型未配置，请前往设置完成配置。",
            },
            technical_details="missing model config",
            resolution_steps=["前往设置页面选择模型"],
            error_code="model_not_configured",
        )
        raw = (await self._chunks(exc, "zh-CN"))[0]
        payload = self._decode(raw)
        assert payload["data"] == "模型未配置，请前往设置完成配置。"
        metadata = payload["metadata"]
        assert isinstance(metadata, dict)
        assert metadata["error_type"] == "model_not_configured"
        assert metadata["resolution_steps"] == ["前往设置页面选择模型"]

    @pytest.mark.asyncio
    async def test_config_incomplete_error_en_fallback(self) -> None:
        exc = ConfigIncompleteError(
            user_friendly_message={"en": "Model is not configured.", "zh": "模型未配置。"},
            technical_details="missing model config",
            resolution_steps=["pick a model"],
            error_code="model_not_configured",
        )
        raw = (await self._chunks(exc, "fr"))[0]
        payload = self._decode(raw)
        assert payload["data"] == "Model is not configured."

    @pytest.mark.asyncio
    async def test_myrm_llm_error_with_recovery_and_cooldown(self) -> None:
        exc = MyrmLLMError(
            error_code=FailoverReason.RATE_LIMIT,
            default_msg="Rate limited by provider",
            context={"cooldown_remaining_ms": 30000},
            recovery_actions=["wait", "top_up"],
            diagnostic_result={
                "user_message": "请求过于频繁，请稍后重试。",
                "error_type": "rate_limit",
            },
        )
        with patch(
            "app.core.errors.llm_errors.generate_recovery_actions",
            return_value=["wait"],
        ):
            raw = (await self._chunks(exc, "zh"))[0]
        payload = self._decode(raw)
        assert payload["data"] == "请求过于频繁，请稍后重试。"
        assert payload["retry_after_ms"] == 30000
        metadata = payload["metadata"]
        assert isinstance(metadata, dict)
        assert metadata["error_type"] == "RATE_LIMIT"
        assert payload["recovery_actions"] == ["wait"]

    @pytest.mark.asyncio
    async def test_myrm_llm_error_en_fallback(self) -> None:
        exc = MyrmLLMError(
            error_code=FailoverReason.MODEL_NOT_FOUND,
            default_msg="Model does not exist",
            recovery_actions=["switch model"],
        )
        with patch(
            "app.core.errors.llm_errors.generate_recovery_actions",
            return_value=["switch model"],
        ):
            raw = (await self._chunks(exc, "en"))[0]
        payload = self._decode(raw)
        assert "[model_not_found]" in str(payload["data"])
        assert "retry_after_ms" not in payload

    @pytest.mark.asyncio
    async def test_unknown_error_fallback(self) -> None:
        raw = (await self._chunks(RuntimeError("mystery")))[0]
        payload = self._decode(raw)
        assert payload["data"] == "Agent execution error"

    @pytest.mark.asyncio
    async def test_checkpoint_cleanup_failure_swallowed(self) -> None:
        """Checkpoint cleanup exceptions on resume failure are non-blocking."""
        session = _make_session()
        session.request.chat_id = "chat-cleanup"
        cp = AsyncMock()
        cp.adelete_thread.side_effect = RuntimeError("checkpoint gone")
        with patch("app.platform_utils.get_checkpointer", return_value=cp):
            raw = (await self._chunks(ValueError("Resume failed: gone"), session=session))[0]
        payload = self._decode(raw)
        assert "Resume failed" in str(payload["data"])
        assert session.had_fatal_error is True

    @pytest.mark.asyncio
    async def test_turn_capability_failed_recorded_once(self) -> None:
        """The terminal failure telemetry is recorded when context is present."""
        session = _make_session()
        session.request.turn_capability_telemetry = TurnCapabilityTelemetryRequest(
            source="direct", effective_skill_count=1, effective_mcp_count=0
        )
        with patch(
            "app.services.agent.stream_session.stream_finalize.record_turn_capability_send_failed",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await self._chunks(ValueError("boom"), session=session)
        assert session.turn_capability_terminal_recorded is True
