"""Tests for wiki knowledge query intent gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.ai_agents.agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.params.models import AgentRequest
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.wiki.wiki_query_intent import matches_wiki_query_intent, should_use_wiki_knowledge_lane


@dataclass
class _FakeCollector:
    def feed_event(self, _event: dict[str, object]) -> None:
        return None


def _session(
    *,
    query: str = "上周 API 迁移方案有几个？",
    enable_wiki: bool = True,
    action_mode: str = "agent",
) -> AgentStreamSession:
    request = AgentRequest(
        message_id="msg-wiki-lane",
        chat_id="chat-wiki-lane",
        agent_id="default",
        query=query,
        action_mode=action_mode,
        enable_memory=False,
    )
    params = GeneralAgentParams(
        message_id="msg-wiki-lane",
        chat_id="chat-wiki-lane",
        agent_id="default",
        query=query,
        model_cfg=ModelConfig(model="test/model", api_key="k"),
        enable_wiki=enable_wiki,
    )
    return AgentStreamSession(
        request=request,
        http_request=cast(object, None),
        params=params,
        cancel_token=CancellationToken(),
        steering_token=None,
        routing_tier=None,
        context_warnings=[],
        archive_restore_results=[],
        research_model_cfg=None,
        registry=object(),
        collector=_FakeCollector(),
        monitor=cast(object, None),
        is_long_running_task=False,
        goal_provider=None,
        extra_context={},
    )


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("上周 API 迁移方案有几个？", True),
        ("What is revenue growth?", True),
        ("How many migration plans were discussed?", True),
        ("统计一下 wiki 里的 API 条目数量", True),
        ("import this PDF into wiki", False),
        ("请编译 wiki vault", False),
        ("run wiki_maintain on the vault", False),
        ("写一段 Python 脚本", False),
        ("hello", False),
    ],
)
def test_matches_wiki_query_intent(question: str, expected: bool) -> None:
    assert matches_wiki_query_intent(question) is expected


def test_should_use_wiki_knowledge_lane_rejects_fast_mode() -> None:
    session = _session(action_mode="fast")
    assert should_use_wiki_knowledge_lane(session) is False


def test_should_use_wiki_knowledge_lane_rejects_when_wiki_disabled() -> None:
    session = _session(enable_wiki=False)
    assert should_use_wiki_knowledge_lane(session) is False


def test_should_use_wiki_knowledge_lane_accepts_with_vault_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.wiki.wiki_query_intent.is_vault_ready",
        lambda _agent_id=None: True,
    )
    monkeypatch.setattr(
        "app.services.wiki.wiki_query_intent.vault_has_wiki_content",
        lambda _agent_id=None: True,
    )

    session = _session()
    assert should_use_wiki_knowledge_lane(session) is True
