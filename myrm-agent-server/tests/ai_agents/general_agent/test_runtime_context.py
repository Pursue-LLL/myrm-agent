"""What a GeneralAgent hands the harness for one turn: the optional runtime context, its memory binding and its wiki vaults.

Every optional entry appears only when the agent was given the thing it describes, so a turn that was given nothing
carries none of them; a privacy-sensitive entry (loaded skills) is withheld for an incognito chat.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.agent.skills.runtime.session_skills_rehydrate import SESSION_LOADED_SKILL_NAMES_CONTEXT_KEY
from myrm_agent_harness.agent.types import QuoteAttachment
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.ai_agents.general_agent import GeneralAgent
from app.core.types import ModelConfig

CHAT_ID = "chat-runtime"
OPTIONAL_KEYS = (
    "prompt_mode",
    "prompt_locale",
    "approval_session_key",
    "project_id",
    "max_context_tokens",
    "vision_fallback_model_cfgs",
    "vision_fallback_model_cfg",
    "video_fallback_model_cfgs",
    "compression_intent",
    "quote_attachment",
    "goal",
    SESSION_LOADED_SKILL_NAMES_CONTEXT_KEY,
)


def _model(**overrides: object) -> ModelConfig:
    return ModelConfig(provider="openai", model="gpt-4o-mini", api_key="test", **overrides)


def _agent(**overrides: object) -> GeneralAgent:
    params: dict[str, object] = {
        "model_cfg": _model(),
        "mcp_config": None,
        "search_service_cfg": SearchServiceConfig(search_service="searxng"),
        "chat_id": CHAT_ID,
        "channel_name": "web_chat",
        "agent_id": "planner",
    }
    params.update(overrides)
    return GeneralAgent(**params)


def _context(agent: GeneralAgent, *, query: object = "hello", chat_history: list[list[str]] | None = None) -> dict[str, object]:
    return agent._build_runtime_context(query=query, chat_history=chat_history, effective_chat_id=CHAT_ID)


class TestOptionalRuntimeContext:
    def test_a_plain_turn_carries_none_of_the_optional_entries(self) -> None:
        # "continue" names no file or module, so there is no compression focus either.
        context = _context(_agent(), query="continue")

        assert [key for key in OPTIONAL_KEYS if key in context] == []

    def test_a_search_turn_names_its_prompt_mode_and_the_users_locale(self) -> None:
        context = _context(_agent(prompt_mode="search", locale="zh"))

        assert (context["prompt_mode"], context["prompt_locale"]) == ("search", "zh")

    def test_the_approval_key_the_channel_claimed_travels_with_the_turn(self) -> None:
        agent = _agent()
        agent.approval_session_key = "telegram:chat-1"

        assert _context(agent)["approval_session_key"] == "telegram:chat-1"

    def test_the_project_and_the_models_context_window_travel_with_the_turn(self) -> None:
        context = _context(_agent(project_id="proj-1", model_cfg=_model(max_context_tokens=64000)))

        assert (context["project_id"], context["max_context_tokens"]) == ("proj-1", 64000)

    def test_the_media_fallback_models_travel_with_the_turn(self) -> None:
        vision, video = _model(supports_vision=True), _model(supports_video=True)

        context = _context(
            _agent(vision_fallback_model_cfg=vision, vision_fallback_model_cfgs=[vision], video_fallback_model_cfgs=[video])
        )

        assert context["vision_fallback_model_cfg"] is vision
        assert context["vision_fallback_model_cfgs"] == [vision]
        assert context["video_fallback_model_cfgs"] == [video]

    def test_the_text_the_user_quoted_becomes_a_quote_attachment(self) -> None:
        context = _context(_agent(quote="the sentence they selected"))

        assert context["quote_attachment"] == QuoteAttachment(source_message_id="", quoted_text="the sentence they selected")

    def test_the_goal_of_a_goal_turn_travels_with_the_turn(self) -> None:
        assert _context(_agent(goal="ship the release"))["goal"] == "ship the release"

    def test_the_skills_loaded_earlier_in_the_chat_are_handed_back_in_their_order(self) -> None:
        context = _context(_agent(session_loaded_skill_names=["pdf", "xlsx"]))

        assert context[SESSION_LOADED_SKILL_NAMES_CONTEXT_KEY] == ["pdf", "xlsx"]

    def test_an_incognito_chat_withholds_the_skills_it_loaded(self) -> None:
        context = _context(_agent(session_loaded_skill_names=["pdf"], incognito_mode=True))

        assert SESSION_LOADED_SKILL_NAMES_CONTEXT_KEY not in context

    def test_a_history_in_the_legacy_pair_form_is_not_read_for_the_compression_focus(self) -> None:
        context = _context(_agent(), query="look at app/main.py", chat_history=[["user", "see app/old.py"]])

        assert context["compression_intent"]["focus_files"] == ["app/main.py"]


class TestMemoryBinding:
    @pytest.mark.parametrize(
        "overrides",
        [{"enable_memory": False}, {"incognito_mode": True}],
        ids=["memory-off", "incognito"],
    )
    def test_a_chat_that_keeps_no_memory_has_no_binding(self, overrides: dict[str, object]) -> None:
        assert _agent(**overrides)._resolve_context_binding(CHAT_ID) is None


class TestWikiVaults:
    def test_the_agents_own_vault_is_resolved_for_its_id(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        resolved = MagicMock(return_value=tmp_path / "planner")
        monkeypatch.setattr("app.services.wiki.vault.resolve_agent_wiki_vault_path", resolved)

        assert _agent()._resolve_wiki_base_dir() == str(tmp_path / "planner")
        resolved.assert_called_once_with("planner")

    def test_the_shared_vaults_are_resolved_for_the_bound_contexts(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        resolved = MagicMock(return_value=[tmp_path / "team", tmp_path / "ops"])
        monkeypatch.setattr("app.services.wiki.vault.resolve_shared_wiki_vault_paths", resolved)

        assert _agent(memory_shared_context_ids=["ctx-team", "ctx-ops"])._resolve_wiki_public_dirs() == [
            str(tmp_path / "team"),
            str(tmp_path / "ops"),
        ]
        resolved.assert_called_once_with(["ctx-team", "ctx-ops"])

    @pytest.mark.parametrize(
        ("names", "expected_names"),
        [({"ctx-team": "Team"}, {"ctx-team": "Team"}), (None, None), ({}, None)],
        ids=["named", "unnamed", "empty"],
    )
    def test_the_shared_vault_labels_use_the_names_the_contexts_were_given(
        self, monkeypatch: pytest.MonkeyPatch, names: dict[str, str] | None, expected_names: dict[str, str] | None
    ) -> None:
        resolved = MagicMock(return_value={"ctx-team": "Team"})
        monkeypatch.setattr("app.services.wiki.vault.resolve_shared_wiki_vault_labels", resolved)
        agent = _agent(memory_shared_context_ids=["ctx-team"], memory_shared_context_names=names)

        assert agent._resolve_wiki_public_dir_labels() == {"ctx-team": "Team"}
        resolved.assert_called_once_with(["ctx-team"], context_name_map=expected_names)


class TestProcessStream:
    async def test_the_turn_is_streamed_through_the_pipeline_with_everything_it_was_given(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        received: list[tuple[tuple[object, ...], dict[str, object]]] = []

        async def pipeline(*args: object, **kwargs: object) -> AsyncGenerator[dict[str, object], None]:
            received.append((args, kwargs))
            yield {"type": "chunk", "n": 1}
            yield {"type": "chunk", "n": 2}

        monkeypatch.setattr("app.ai_agents.general_agent.stream_pipeline.execute_stream_pipeline", pipeline)
        agent = _agent()
        cancel_token, steering_token = MagicMock(), MagicMock()

        chunks = [
            chunk
            async for chunk in agent.process_stream(
                "hi",
                chat_history=None,
                message_id="m-1",
                chat_id="c-1",
                cancel_token=cancel_token,
                steering_token=steering_token,
                timezone="Asia/Shanghai",
                force_external_agent="codex",
                context={"extra": 1},
            )
        ]

        assert chunks == [{"type": "chunk", "n": 1}, {"type": "chunk", "n": 2}]
        assert received == [
            (
                (agent, "hi", None, "m-1", "c-1", cancel_token, steering_token, "Asia/Shanghai", "codex"),
                {"extra_context": {"extra": 1}},
            )
        ]
