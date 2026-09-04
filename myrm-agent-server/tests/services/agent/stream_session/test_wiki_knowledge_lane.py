"""Tests for wiki knowledge lane stream."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest
from myrm_agent_harness.toolkits.wiki.core.types import QueryResult

from app.ai_agents.agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.stream_session.lanes.wiki_knowledge_lane import create_wiki_knowledge_lane_stream
from app.services.wiki.knowledge_query_service import WikiKnowledgeQueryResult


@dataclass
class _FakeCancelToken:
    is_cancelled: bool = False
    cancel_reason: str | None = None


@pytest.mark.asyncio
async def test_wiki_knowledge_lane_emits_sources_message_and_lane_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_result = WikiKnowledgeQueryResult(
        answer="Two migration plans were recorded.",
        sources=[{"path": "concepts/api.md", "filename": "api.md", "snippet": "Plan A"}],
        related_articles=["api"],
        confidence_score=0.82,
        retrieval_result=QueryResult(
            question="How many migration plans?",
            answer="Two migration plans were recorded.",
            related_articles=["api"],
        ),
    )

    async def _fake_execute(**_kwargs: object) -> WikiKnowledgeQueryResult:
        return fake_result

    monkeypatch.setattr(
        "app.services.agent.stream_session.lanes.wiki_knowledge_lane.execute_wiki_knowledge_query",
        _fake_execute,
    )

    params = GeneralAgentParams(
        message_id="msg-lane-1",
        chat_id="chat-lane-1",
        agent_id="default",
        query="How many migration plans?",
        model_cfg=ModelConfig(model="test/model", api_key="k"),
        enable_wiki=True,
    )

    events = [
        event
        async for event in create_wiki_knowledge_lane_stream(
            params,
            cast(object, _FakeCancelToken()),
        )
    ]

    types = [event.get("type") for event in events]
    assert types == ["status", "sources", "message", "status", "message_end"]

    assert events[0].get("step_key") == "wiki_knowledge_lane"
    assert events[1]["data"][0]["index"] == 1
    assert events[2]["data"] == fake_result.answer
    assert events[3].get("step_key") == "wiki_knowledge_lane_clear"
    assert events[4].get("execution_lane") == "wiki_knowledge"
    assert events[4].get("wiki_source_count") == 1


@pytest.mark.asyncio
async def test_wiki_knowledge_lane_forwards_shared_context_ids_and_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}

    fake_result = WikiKnowledgeQueryResult(
        answer="Federated answer from shared vaults.",
        sources=[{"path": "concepts/guide.md", "filename": "guide.md", "snippet": "Text", "kb_name": "Shared KB"}],
        related_articles=["guide"],
        confidence_score=0.9,
        retrieval_result=QueryResult(
            question="What is the shared policy?",
            answer="Federated answer from shared vaults.",
            related_articles=["guide"],
        ),
    )

    async def _inspect_execute(**kwargs: object) -> WikiKnowledgeQueryResult:
        captured_kwargs.update(kwargs)
        return fake_result

    monkeypatch.setattr(
        "app.services.agent.stream_session.lanes.wiki_knowledge_lane.execute_wiki_knowledge_query",
        _inspect_execute,
    )

    params = GeneralAgentParams(
        message_id="msg-lane-shared",
        chat_id="chat-lane-shared",
        agent_id="default",
        query="What is the shared policy?",
        model_cfg=ModelConfig(model="test/model", api_key="k"),
        enable_wiki=True,
        memory_shared_context_ids=["kb-vault-1", "kb-vault-2"],
        memory_shared_context_names={"kb-vault-1": "Shared KB"},
    )

    events = [
        event
        async for event in create_wiki_knowledge_lane_stream(
            params,
            cast(object, _FakeCancelToken()),
        )
    ]

    assert captured_kwargs.get("shared_context_ids") == ["kb-vault-1", "kb-vault-2"]
    assert events[1]["type"] == "sources"
    assert events[1]["data"][0]["kb_name"] == "Shared KB"


@pytest.mark.asyncio
async def test_wiki_knowledge_lane_query_failure_yields_failed_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fail_execute(**_kwargs: object) -> WikiKnowledgeQueryResult:
        raise RuntimeError("vault unavailable")

    monkeypatch.setattr(
        "app.services.agent.stream_session.lanes.wiki_knowledge_lane.execute_wiki_knowledge_query",
        _fail_execute,
    )

    params = GeneralAgentParams(
        message_id="msg-lane-fail",
        chat_id="chat-lane-fail",
        agent_id="default",
        query="How many plans?",
        model_cfg=ModelConfig(model="test/model", api_key="k"),
        enable_wiki=True,
    )

    events = [
        event
        async for event in create_wiki_knowledge_lane_stream(
            params,
            cast(object, _FakeCancelToken()),
        )
    ]

    assert events[-1]["type"] == "message_end"
    assert events[-1].get("completion_status") == "failed"
    assert events[-1].get("execution_lane") == "wiki_knowledge"
