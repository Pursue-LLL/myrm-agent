"""Tests for _agent_response serialization helpers."""

from myrm_agent_harness.backends.profiles.types import AgentProfile, CommandBinding
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy

from app.api.agents._agent_response import (
    _build_model_selection,
    _meta_dict_or_none,
    _meta_list_or_empty,
    _meta_list_or_none,
    _meta_str_list,
    _meta_str_list_or_none,
    _response_memory_policy,
    _response_session_policy,
    _resolve_enabled_builtin_tools,
    _safe_personality,
    _to_agent_response,
)


def _profile(*, metadata: dict | None) -> AgentProfile:
    return AgentProfile(id="a1", display_name="Agent1", metadata=metadata)


def test_allow_discovery_false_is_serialized() -> None:
    response = _to_agent_response(_profile(metadata={"allow_discovery": False}))
    assert response.allow_discovery is False


def test_allow_discovery_true_is_serialized() -> None:
    response = _to_agent_response(_profile(metadata={"allow_discovery": True}))
    assert response.allow_discovery is True


def test_allow_discovery_defaults_true_when_missing() -> None:
    response = _to_agent_response(_profile(metadata=None))
    assert response.allow_discovery is True


class TestSerializationHelpers:
    def test_safe_personality_valid(self) -> None:
        assert _safe_personality("friendly") == "friendly"

    def test_safe_personality_hard_fallback(self, monkeypatch) -> None:
        """Invalid default personality still yields a literal fallback."""
        import app.api.agents._agent_response as mod

        monkeypatch.setattr(
            mod,
            "DEFAULT_PERSONALITY_STYLE",
            "not-a-real-style",
        )
        assert _safe_personality("also-invalid") == "professional"

    def test_meta_str_list_converts_to_strings(self) -> None:
        assert _meta_str_list({"mcp_ids": ["a", 1]}, "mcp_ids") == ["a", "1"]

    def test_meta_str_list_defaults_empty(self) -> None:
        assert _meta_str_list({}, "missing") == []

    def test_meta_str_list_or_none_converts(self) -> None:
        assert _meta_str_list_or_none(
            {"suggestion_prompts": ["p"]}, "suggestion_prompts"
        ) == ["p"]

    def test_meta_str_list_or_none_returns_none_for_scalar(self) -> None:
        assert _meta_str_list_or_none({"suggestion_prompts": "p"}, "suggestion_prompts") is None

    def test_meta_dict_or_none_converts(self) -> None:
        assert _meta_dict_or_none(
            {"security_overrides": {"allow": "1"}}, "security_overrides"
        ) == {"allow": "1"}

    def test_meta_list_or_empty_filters_dicts(self) -> None:
        assert _meta_list_or_empty(
            {"openapi_services": [{"url": "x"}, "junk"]}, "openapi_services"
        ) == [{"url": "x"}]

    def test_meta_list_or_none_nonempty(self) -> None:
        assert _meta_list_or_none(
            {"notify_targets": [{"channel": "c"}]}, "notify_targets"
        ) == [{"channel": "c"}]

    def test_response_memory_policy_valid(self) -> None:
        profile = AgentProfile(id="a1", memory_policy=AgentMemoryPolicy())
        assert _response_memory_policy(profile) is not None

    def test_response_session_policy_valid(self) -> None:
        config = _response_session_policy({"session_policy": {"mode": "daily"}})
        assert config is not None
        assert config.mode == "daily"

    def test_build_model_selection_full(self) -> None:
        selection = _build_model_selection(
            "gpt-4o",
            {"model_selection_full": {"model": "gpt-5", "providerId": "openai"}},
        )
        assert selection is not None
        assert selection.model == "gpt-5"
        assert selection.providerId == "openai"

    def test_build_model_selection_fallback(self) -> None:
        selection = _build_model_selection("gpt-4o", {})
        assert selection is not None
        assert selection.model == "gpt-4o"

    def test_resolve_enabled_builtin_tools_from_profile(self) -> None:
        profile = AgentProfile(id="a1", tools_allowed=["web_search"])
        assert _resolve_enabled_builtin_tools(profile) == ["web_search"]

    def test_full_serialization_with_all_metadata(self) -> None:
        profile = AgentProfile(
            id="a1",
            display_name="Agent1",
            description="Desc",
            model="gpt-4o",
            skills=["s1"],
            tools_allowed=["web_search"],
            memory_policy=AgentMemoryPolicy(),
            command_bindings=[
                CommandBinding(
                    command_name="cmd",
                    skill_ids=("s1",),
                    description="d",
                    aliases=("c",),
                    instruction="i",
                )
            ],
            metadata={
                "allow_discovery": False,
                "mcp_ids": ["mcp1"],
                "personality_style": "friendly",
                "prompt_mode": "lean",
                "agent_type": "team",
                "subagent_ids": ["sub1"],
                "workspace_policy": "ISOLATED_COPY",
                "session_policy": {"mode": "daily"},
                "openapi_services": [{"url": "https://api.example.com/openapi.json"}],
                "notify_targets": [
                    {"channel": "im", "recipient_id": "u1", "label": "me"}
                ],
                "suggestion_prompts": ["p1"],
                "busy_input_mode": "steer",
                "cron_post_run_verify": True,
            },
        )

        response = _to_agent_response(
            profile, show_system_prompt=True, snapshot_count=2, snapshot_saved=True
        )

        assert response.allow_discovery is False
        assert response.personality_style == "friendly"
        assert response.agent_type == "team"
        assert response.workspace_policy == "ISOLATED_COPY"
        assert response.session_policy is not None
        assert response.notify_targets is not None
        assert response.busy_input_mode == "steer"
        assert response.cron_post_run_verify is True
        assert response.snapshot_count == 2
        assert response.snapshot_saved is True
        assert response.command_bindings is not None
        assert response.command_bindings[0].command_name == "cmd"
