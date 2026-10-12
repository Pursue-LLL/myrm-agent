"""Shared-context display names reach the agent params and the wiki lane from the database.

Both call sites open their own DB session; a broken session import is swallowed by their
fallback handlers and silently drops every name, so the names are asserted against a real
SharedContextService round trip.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.wiki.core.types import QueryResult
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai_agents.agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.database.models import Base
from app.database.models.memory import SharedContextModel
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from app.services.agent.stream_session.lanes.wiki_knowledge_lane import create_wiki_knowledge_lane_stream
from app.services.memory.shared_context.shared_context import SharedContextService
from app.services.wiki.knowledge_query_service import WikiKnowledgeQueryResult
from tests.api.agent.conftest import _build_mock_user_configs
from tests.api.agent.utils import get_model_selection

CONTEXT_NAME = "Engineering Handbook"


@dataclass
class _FakeCancelToken:
    is_cancelled: bool = False
    cancel_reason: str | None = None


@pytest_asyncio.fixture
async def shared_context(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SharedContextModel]:
    """One persisted shared context; every ``get_session()`` in the process points at its database."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.connection.get_session_factory", lambda: factory)
    async with factory() as session:
        yield await SharedContextService(session).create_context(name=CONTEXT_NAME)
    await engine.dispose()


async def test_converter_resolves_shared_context_names(shared_context: SharedContextModel) -> None:
    payload: dict[str, Any] = {
        "message_id": "msg-shared-context-names",
        "chat_id": "chat-shared-context-names",
        "query": "Summarize the handbook",
        "model_selection": get_model_selection(),
        "action_mode": "agent",
        "session_knowledge_base_ids": [shared_context.id],
    }

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=_build_mock_user_configs()),
    ):
        params, *_ = await convert_to_general_agent_params(AgentRequest(**payload), [])

    assert params.memory_shared_context_ids == [shared_context.id]
    assert params.memory_shared_context_names == {shared_context.id: CONTEXT_NAME}


async def test_wiki_lane_resolves_missing_shared_context_names(
    shared_context: SharedContextModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    async def _capture_query(**kwargs: object) -> WikiKnowledgeQueryResult:
        captured.update(kwargs)
        return WikiKnowledgeQueryResult(
            answer="From the handbook.",
            sources=[],
            related_articles=[],
            confidence_score=0.9,
            refused=False,
            retrieval_result=QueryResult(question="Q", answer="From the handbook.", related_articles=[]),
        )

    monkeypatch.setattr(
        "app.services.agent.stream_session.lanes.wiki_knowledge_lane.execute_wiki_knowledge_query",
        _capture_query,
    )
    params = GeneralAgentParams(
        message_id="msg-lane-names",
        chat_id="chat-lane-names",
        agent_id="default",
        query="What does the handbook say?",
        model_cfg=ModelConfig(model="test/model", api_key="k"),
        enable_wiki=True,
        memory_shared_context_ids=[shared_context.id],
    )

    _ = [event async for event in create_wiki_knowledge_lane_stream(params, cast(object, _FakeCancelToken()))]

    assert captured["context_name_map"] == {shared_context.id: CONTEXT_NAME}
