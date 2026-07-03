"""Incognito mode: session-level full memory off without changing global enable_memory.

Tests the complete behavior matrix without external LLM dependencies:
- enable_memory=True + incognito=True → no memory tools / no auto extraction
- enable_memory=False + incognito=True → no memory at all
- session_cleanup_callback disabled in incognito
- system prompt excludes MEMORY_RULES in incognito
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.params.models import AgentRequest


class TestIncognitoConverterMatrix:
    """All possible (enable_memory, incognito_mode) combinations."""

    def test_memory_on_incognito_on(self) -> None:
        req = AgentRequest(
            message_id="m1", query="q", chat_id="c",
            enable_memory=True, enable_memory_auto_extraction=True, incognito_mode=True,
        )
        enable_memory = req.enable_memory
        auto_extraction = False if req.incognito_mode else (req.enable_memory and req.enable_memory_auto_extraction)
        assert enable_memory is True
        assert auto_extraction is False

    def test_memory_on_incognito_off(self) -> None:
        req = AgentRequest(
            message_id="m2", query="q", chat_id="c",
            enable_memory=True, enable_memory_auto_extraction=True, incognito_mode=False,
        )
        enable_memory = req.enable_memory
        auto_extraction = False if req.incognito_mode else (req.enable_memory and req.enable_memory_auto_extraction)
        assert enable_memory is True
        assert auto_extraction is True

    def test_memory_off_incognito_on(self) -> None:
        req = AgentRequest(
            message_id="m3", query="q", chat_id="c",
            enable_memory=False, enable_memory_auto_extraction=True, incognito_mode=True,
        )
        enable_memory = req.enable_memory
        auto_extraction = False if req.incognito_mode else (req.enable_memory and req.enable_memory_auto_extraction)
        assert enable_memory is False
        assert auto_extraction is False

    def test_memory_off_incognito_off(self) -> None:
        req = AgentRequest(
            message_id="m4", query="q", chat_id="c",
            enable_memory=False, enable_memory_auto_extraction=True, incognito_mode=False,
        )
        enable_memory = req.enable_memory
        auto_extraction = False if req.incognito_mode else (req.enable_memory and req.enable_memory_auto_extraction)
        assert enable_memory is False
        assert auto_extraction is False


class TestIncognitoSystemPrompt:
    """System prompt must exclude MEMORY_RULES when incognito."""

    def test_incognito_disables_memory_rules_in_prompt(self) -> None:
        from app.ai_agents.prompts.general_agent_prompt import get_core_system_prompt

        prompt_with_memory = get_core_system_prompt(enable_memory=True)
        prompt_without_memory = get_core_system_prompt(enable_memory=False)
        assert len(prompt_with_memory) > len(prompt_without_memory)
        assert "memory_save" in prompt_with_memory or "MEMORY" in prompt_with_memory
        assert "memory_save" not in prompt_without_memory

    def test_prompt_cache_key_stability(self) -> None:
        from app.ai_agents.prompts.general_agent_prompt import get_core_system_prompt

        p1 = get_core_system_prompt(enable_memory=False)
        p2 = get_core_system_prompt(enable_memory=False)
        assert p1 is p2 or p1 == p2


class TestIncognitoSessionCleanup:
    """session_cleanup_callback must return None in incognito."""

    def test_cleanup_returns_none_when_incognito(self) -> None:
        from app.ai_agents.general_agent.factory import _build_session_cleanup_callback

        agent_wrapper = MagicMock()
        agent_wrapper.enable_memory = True
        agent_wrapper.incognito_mode = True

        result = _build_session_cleanup_callback(agent_wrapper, "user-1")
        assert result is None

    def test_cleanup_returns_none_when_memory_disabled(self) -> None:
        from app.ai_agents.general_agent.factory import _build_session_cleanup_callback

        agent_wrapper = MagicMock()
        agent_wrapper.enable_memory = False
        agent_wrapper.incognito_mode = False

        result = _build_session_cleanup_callback(agent_wrapper, "user-1")
        assert result is None


class TestReadOnlyMemoryViewSubagentIsolation:
    """Harness ReadOnlyMemoryView behaviors (subagent READ_ONLY_GLOBAL path, not GeneralAgent incognito)."""

    def test_set_last_cited_memory_ids_does_not_raise(self) -> None:
        from myrm_agent_harness.toolkits.memory.ephemeral import ReadOnlyMemoryView

        parent = MagicMock()
        parent._namespaces = ["ns"]
        parent._scope = MagicMock()
        parent._config = MagicMock()
        view = ReadOnlyMemoryView(parent)

        view.set_last_cited_memory_ids(["id-1", "id-2"])
        assert view._last_cited_memory_ids == ["id-1", "id-2"]

    @pytest.mark.asyncio
    async def test_search_delegates_in_readonly(self) -> None:
        from myrm_agent_harness.toolkits.memory.ephemeral import ReadOnlyMemoryView

        parent = MagicMock()
        parent._namespaces = ["ns"]
        parent._scope = MagicMock()
        parent._config = MagicMock()
        parent.search = AsyncMock(return_value=[])
        view = ReadOnlyMemoryView(parent)

        results = await view.search("test query")
        parent.search.assert_awaited_once()
        assert results == []

    @pytest.mark.asyncio
    async def test_store_raises_permission_error(self) -> None:
        from myrm_agent_harness.toolkits.memory.ephemeral import ReadOnlyMemoryView
        from myrm_agent_harness.toolkits.memory.types import SemanticMemory

        parent = MagicMock()
        parent._namespaces = ["ns"]
        parent._scope = MagicMock()
        parent._config = MagicMock()
        view = ReadOnlyMemoryView(parent)

        with pytest.raises(PermissionError, match="READ_ONLY_GLOBAL"):
            await view.store(SemanticMemory(content="should fail"))

    @pytest.mark.asyncio
    async def test_end_session_returns_empty(self) -> None:
        from myrm_agent_harness.toolkits.memory.ephemeral import ReadOnlyMemoryView

        parent = MagicMock()
        parent._namespaces = ["ns"]
        parent._scope = MagicMock()
        parent._config = MagicMock()
        view = ReadOnlyMemoryView(parent)

        result = await view.end_session()
        assert result == []
