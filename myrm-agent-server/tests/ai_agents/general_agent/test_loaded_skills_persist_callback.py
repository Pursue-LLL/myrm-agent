"""Tests for loaded-skills SSOT persist callback."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.ai_agents.general_agent.callbacks import make_loaded_skills_persist_callback


@pytest.mark.asyncio
async def test_loaded_skills_persist_writes_chat_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_update(chat_id: str, updates: dict[str, object]) -> None:
        captured["chat_id"] = chat_id
        captured["updates"] = updates

    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.update_chat_fields",
        _fake_update,
    )

    persist = make_loaded_skills_persist_callback()
    await persist(["alpha_skill", "beta_skill"], "chat-123")

    assert captured["chat_id"] == "chat-123"
    assert captured["updates"] == {"session_loaded_skill_names": ["alpha_skill", "beta_skill"]}


@pytest.mark.asyncio
async def test_loaded_skills_persist_skips_without_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    update_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.update_chat_fields",
        update_mock,
    )

    persist = make_loaded_skills_persist_callback()
    await persist(["alpha_skill"], None)

    update_mock.assert_not_called()
