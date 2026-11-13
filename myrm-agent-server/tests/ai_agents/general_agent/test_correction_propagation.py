"""Tests for implicit feedback detection and correction propagation.

Covers: make_correction_propagation_callback, _run_correction_propagation,
implicit_feedback pipeline (detect_implicit_feedback, plan_memory_corrections),
and the composite _build_session_cleanup_callback.
"""

import pytest

# ---------------------------------------------------------------------------
# Unit tests (no LLM / no DB)
# ---------------------------------------------------------------------------


class TestDetectCorrectionSignals:
    """Test correction detection via Harness-layer detect_feedback_signals."""

    def test_english_correction_detected(self, correction_messages: list[dict[str, str]]) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        assert detect_feedback_signals(correction_messages) == FeedbackSignal.NEGATIVE

    def test_chinese_correction_detected(self, zh_correction_messages: list[dict[str, str]]) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        assert detect_feedback_signals(zh_correction_messages) == FeedbackSignal.NEGATIVE

    def test_no_correction_returns_none(self, no_correction_messages: list[dict[str, str]]) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        signal = detect_feedback_signals(no_correction_messages)
        assert signal != FeedbackSignal.NEGATIVE

    def test_positive_feedback_returns_positive(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        messages = [
            {"role": "user", "content": "Write a poem"},
            {"role": "assistant", "content": "Roses are red..."},
            {"role": "user", "content": "That's exactly right, perfect!"},
        ]
        assert detect_feedback_signals(messages) == FeedbackSignal.POSITIVE

    def test_empty_messages_safe(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        assert detect_feedback_signals([]) == FeedbackSignal.NONE

    def test_single_message_safe(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        assert detect_feedback_signals([{"role": "user", "content": "hello"}]) == FeedbackSignal.NONE


class TestImplicitFeedbackUnit:
    """Unit tests for the implicit_feedback module (no LLM)."""

    @pytest.mark.asyncio
    async def test_short_messages_return_none(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            detect_implicit_feedback,
        )

        async def dummy_llm(system: str, prompt: str) -> str:
            raise AssertionError("Should not call LLM for short messages")

        result = await detect_implicit_feedback([{"role": "user", "content": "hi"}], dummy_llm)
        assert not result.has_implicit_contradiction
        assert result.proposals == []

    @pytest.mark.asyncio
    async def test_regex_negative_skips_detection_llm(self, correction_messages: list[dict[str, str]]) -> None:
        """When regex catches NEGATIVE, LLM detection is skipped (only planning runs)."""
        from myrm_agent_harness.toolkits.memory.strategies.extractor import FeedbackSignal
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            detect_implicit_feedback,
        )

        call_count = {"detection": 0, "planning": 0}

        async def tracking_llm(system: str, prompt: str) -> str:
            if "implicit feedback analyst" in system:
                call_count["detection"] += 1
            else:
                call_count["planning"] += 1
            return "[]"

        result = await detect_implicit_feedback(correction_messages, tracking_llm)
        assert result.signal == FeedbackSignal.NEGATIVE
        assert call_count["detection"] == 0, "Detection LLM should be skipped"
        assert call_count["planning"] == 1, "Planning LLM should be called"

    def test_parse_plan_response_handles_valid_json(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            _parse_plan_response,
        )

        raw = '[{"action":"update","memory_type":"semantic","content":"User works at Google","confidence":0.9,"reasoning":"User stated they moved to Google"}]'
        proposals = _parse_plan_response(raw)
        assert len(proposals) == 1
        assert proposals[0].action == CorrectionAction.UPDATE
        assert proposals[0].content == "User works at Google"
        assert proposals[0].confidence == 0.9

    def test_parse_plan_response_handles_invalid_json(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            _parse_plan_response,
        )

        proposals = _parse_plan_response("not json at all")
        assert proposals == []

    def test_parse_plan_response_skips_invalid_actions(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            _parse_plan_response,
        )

        raw = '[{"action":"invalid","memory_type":"semantic","content":"x","confidence":0.9,"reasoning":"y"}]'
        proposals = _parse_plan_response(raw)
        assert proposals == []


class TestCallbackFactory:
    """Test make_correction_propagation_callback factory."""

    def test_returns_callable(self) -> None:
        from app.ai_agents.general_agent.correction_propagation import make_correction_propagation_callback

        async def dummy_llm(system: str, prompt: str) -> str:
            return '{"has_contradiction": false, "signals": []}'

        cb = make_correction_propagation_callback(agent_id="test-agent", llm_func=dummy_llm)
        assert callable(cb)

    @pytest.mark.asyncio
    async def test_callback_handles_no_correction_gracefully(self) -> None:
        """When no correction is detected, callback should return without error."""
        from app.ai_agents.general_agent.correction_propagation import make_correction_propagation_callback

        async def dummy_llm(system: str, prompt: str) -> str:
            return '{"has_contradiction": false, "signals": []}'

        cb = make_correction_propagation_callback(agent_id="test-agent", llm_func=dummy_llm)
        messages: list[dict[str, str]] = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
        ]
        await cb(messages, "chat-123")

    @pytest.mark.asyncio
    async def test_callback_handles_exception_gracefully(self) -> None:
        """Callback should catch exceptions and not propagate them."""
        from app.ai_agents.general_agent.correction_propagation import make_correction_propagation_callback

        async def failing_llm(system: str, prompt: str) -> str:
            raise RuntimeError("LLM failure")

        cb = make_correction_propagation_callback(agent_id="test-agent", llm_func=failing_llm)
        messages: list[dict[str, str]] = [
            {"role": "user", "content": "Tell me about X"},
            {"role": "assistant", "content": "X is about..."},
            {"role": "user", "content": "That's wrong! X is actually Y."},
            {"role": "assistant", "content": "Sorry, Y..."},
        ]
        await cb(messages, "chat-456")


class TestRunCorrectionPropagation:
    """Test _run_correction_propagation with controlled inputs."""

    @pytest.mark.asyncio
    async def test_short_messages_returns_early(self) -> None:
        from app.ai_agents.general_agent.correction_propagation import _run_correction_propagation

        async def dummy_llm(system: str, prompt: str) -> str:
            raise AssertionError("LLM should not be called for short messages")

        await _run_correction_propagation(
            [{"role": "user", "content": "hi"}],
            agent_id="test",
            llm_func=dummy_llm,
            chat_id=None,
        )

    @pytest.mark.asyncio
    async def test_no_negative_feedback_returns_early(self, no_correction_messages: list[dict[str, str]]) -> None:
        from app.ai_agents.general_agent.correction_propagation import _run_correction_propagation

        async def dummy_llm(system: str, prompt: str) -> str:
            return '{"has_contradiction": false, "signals": []}'

        await _run_correction_propagation(
            no_correction_messages,
            agent_id="test",
            llm_func=dummy_llm,
            chat_id=None,
        )

    @pytest.mark.asyncio
    async def test_negative_signal_without_proposals_logs_and_returns(self, correction_messages: list[dict[str, str]]) -> None:
        """A NEGATIVE signal with an empty plan must not raise, just bail out."""
        from app.ai_agents.general_agent.correction_propagation import _run_correction_propagation

        async def empty_plan_llm(system: str, prompt: str) -> str:
            return "[]"

        await _run_correction_propagation(
            correction_messages,
            agent_id="test",
            llm_func=empty_plan_llm,
            chat_id="chat-1",
        )

    @pytest.mark.asyncio
    async def test_full_routing_with_manager_and_shared_contexts(
        self, correction_messages: list[dict[str, str]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end wiring: detected proposals reach both personal and shared queues."""
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            CorrectionProposal,
        )

        from app.ai_agents.general_agent import correction_propagation as mod

        async def planning_llm(system: str, prompt: str) -> str:
            return (
                '[{"action": "add", "memory_type": "semantic", '
                '"content": "The company is MindForge", "confidence": 0.9, '
                '"reasoning": "user corrected the name"}]'
            )

        recorded: list[object] = []

        async def _personal(proposals, **kwargs) -> None:  # type: ignore[no-untyped-def]
            recorded.append(("personal", proposals))

        async def _shared(proposals, **kwargs) -> None:  # type: ignore[no-untyped-def]
            recorded.append(("shared", proposals))

        monkeypatch.setattr(mod, "_route_proposals_to_personal_memory", _personal)
        monkeypatch.setattr(mod, "_route_proposals_to_shared_contexts", _shared)

        await mod._run_correction_propagation(
            correction_messages,
            agent_id="agent-1",
            llm_func=planning_llm,
            chat_id="chat-1",
            memory_manager=None,
        )

        kinds = [kind for kind, _ in recorded]
        assert kinds == ["personal", "shared"]
        assert all(
            isinstance(proposal, CorrectionProposal) and proposal.action == CorrectionAction.ADD
            for _, proposals in recorded
            for proposal in proposals
        )


class TestRecurrenceLlmFunc:
    """The text LLM adapter (recurrence + staleness review) must return the extracted answer text."""

    def test_returns_none_without_consolidation_llm(self) -> None:

        from myrm_agent_harness.toolkits.memory.manager import MemoryManager

        manager = MemoryManager.__new__(MemoryManager)
        manager._consolidation_llm = None  # type: ignore[attr-defined]

        assert manager._build_text_llm_func() is None

    @pytest.mark.asyncio
    async def test_extracts_answer_text_from_response(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from myrm_agent_harness.toolkits.memory.manager import MemoryManager

        manager = MemoryManager.__new__(MemoryManager)
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="consolidated summary"))
        manager._consolidation_llm = llm  # type: ignore[attr-defined]

        llm_func = manager._build_text_llm_func()
        assert llm_func is not None
        result = await llm_func("system", "user")

        assert result == "consolidated summary"
        llm.ainvoke.assert_awaited_once()


class TestDefaultPolicy:
    """Test that _DEFAULT_POLICY includes correction_auto_approve."""

    def test_correction_auto_approve_in_default_policy(self) -> None:
        from app.services.memory.shared_context.shared_context import _DEFAULT_POLICY

        assert "correction_auto_approve" in _DEFAULT_POLICY
        assert _DEFAULT_POLICY["correction_auto_approve"] is True


class TestCorrectionSourceId:
    def test_build_correction_proposal_source_id_is_stable(self) -> None:
        from app.ai_agents.general_agent.correction_propagation import build_correction_proposal_source_id

        first = build_correction_proposal_source_id("chat-1", "API version is v3")
        second = build_correction_proposal_source_id("chat-1", "API version is v3")
        assert first == second
        assert first.startswith("chat-1:")

    def test_build_correction_proposal_source_id_varies_by_summary(self) -> None:
        from app.ai_agents.general_agent.correction_propagation import build_correction_proposal_source_id

        first = build_correction_proposal_source_id("chat-1", "Use gRPC")
        second = build_correction_proposal_source_id("chat-1", "Use REST")
        assert first != second
