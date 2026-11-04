"""Provider table and route resolution: which provider, endpoint and credential a model id resolves to."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.transport.profile import (
    PROFILES,
    UnsupportedProviderError,
    normalize_base_url,
    resolve_route,
    speaks_openai_body,
)


@pytest.fixture(autouse=True)
def _clean_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for profile in PROFILES.values():
        for name in profile.api_key_env:
            monkeypatch.delenv(name, raising=False)


class TestProviderTable:
    def test_every_profile_is_keyed_by_its_own_id(self) -> None:
        assert all(key == profile.id for key, profile in PROFILES.items())

    def test_default_endpoints_are_roots_without_a_trailing_slash(self) -> None:
        for profile in PROFILES.values():
            if profile.base_url is not None:
                assert not profile.base_url.endswith("/"), profile.id

    def test_azure_has_no_default_endpoint(self) -> None:
        assert PROFILES["azure"].base_url is None
        assert PROFILES["azure"].wire == "azure_openai"

    def test_non_openai_protocols_are_exactly_the_ones_with_their_own_wire(self) -> None:
        own_wire = {pid for pid, p in PROFILES.items() if p.wire not in {"openai_chat", "azure_openai"}}
        assert own_wire == {"anthropic", "bedrock", "gemini", "ollama"}

    def test_bedrock_has_no_fixed_endpoint_because_the_region_names_it(self) -> None:
        assert PROFILES["bedrock"].base_url is None
        assert PROFILES["bedrock"].api_key_env == ("AWS_BEARER_TOKEN_BEDROCK",)

    def test_a_provider_without_a_wire_is_not_in_the_table(self) -> None:
        assert "replicate" not in PROFILES


class TestResolveRoute:
    def test_provider_prefix_selects_the_profile_and_strips_the_segment(self) -> None:
        route = resolve_route("deepseek/deepseek-chat", api_key="k")
        assert (route.profile.id, route.model, route.base_url, route.api_key) == (
            "deepseek",
            "deepseek-chat",
            "https://api.deepseek.com",
            "k",
        )

    @pytest.mark.parametrize(
        ("model", "provider"),
        [
            ("gpt-4o", "openai"),
            ("o3-mini", "openai"),
            ("chatgpt-4o-latest", "openai"),
            ("claude-sonnet-4-5", "anthropic"),
            ("gemini-2.5-pro", "gemini"),
        ],
    )
    def test_a_first_party_family_id_without_a_segment_names_its_provider(self, model: str, provider: str) -> None:
        route = resolve_route(model)
        assert (route.profile.id, route.model) == (provider, model)

    def test_a_nested_model_path_keeps_everything_after_the_provider(self) -> None:
        route = resolve_route("openrouter/anthropic/claude-3.5-sonnet")
        assert (route.profile.id, route.model) == ("openrouter", "anthropic/claude-3.5-sonnet")

    def test_the_segment_is_case_insensitive(self) -> None:
        assert resolve_route("OpenAI/gpt-4o").profile.id == "openai"

    def test_an_unknown_provider_without_an_endpoint_is_rejected(self) -> None:
        with pytest.raises(UnsupportedProviderError, match="Cannot resolve a provider"):
            resolve_route("mystery/model-1")

    def test_an_unknown_provider_with_an_endpoint_is_an_openai_compatible_service(self) -> None:
        route = resolve_route("mystery/model-1", api_base="https://gw.example/v1/chat/completions", api_key="k")
        assert route.profile.wire == "openai_chat"
        assert (route.model, route.base_url) == ("mystery/model-1", "https://gw.example/v1")

    def test_a_provider_without_a_wire_fails_with_a_clear_error_even_with_an_endpoint(self) -> None:
        with pytest.raises(UnsupportedProviderError, match="not supported"):
            resolve_route("replicate/meta/llama", api_base="https://gw.example/v1")

    def test_bedrock_resolves_to_its_own_wire_with_the_bearer_key_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock-key")
        route = resolve_route("bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0")
        assert (route.profile.wire, route.model, route.api_key) == (
            "bedrock",
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "bedrock-key",
        )
        assert route.base_url is None

    def test_custom_llm_provider_overrides_the_segment(self) -> None:
        route = resolve_route("deepseek/deepseek-chat", custom_llm_provider="deepseek")
        assert (route.profile.id, route.model) == ("deepseek", "deepseek-chat")

    def test_a_custom_endpoint_replaces_the_default_one(self) -> None:
        route = resolve_route("openai/gpt-4o", api_base="https://proxy.example/v1/")
        assert route.base_url == "https://proxy.example/v1"

    def test_the_environment_credential_is_the_fallback_and_an_explicit_key_wins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "from-env")
        assert resolve_route("openai/gpt-4o").api_key == "from-env"
        assert resolve_route("openai/gpt-4o", api_key="explicit").api_key == "explicit"

    def test_a_credential_is_never_borrowed_from_another_providers_variable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
        assert resolve_route("deepseek/deepseek-chat").api_key is None


class TestNormalizeBaseUrl:
    @pytest.mark.parametrize(
        ("provider", "given", "root"),
        [
            ("openai", "https://gw.example/v1/chat/completions", "https://gw.example/v1"),
            ("openai", "https://gw.example/v1/responses", "https://gw.example/v1"),
            ("openai", "https://gw.example/v1/", "https://gw.example/v1"),
            ("anthropic", "https://gw.example/v1/messages", "https://gw.example"),
            ("anthropic", "https://gw.example/v1", "https://gw.example"),
            ("anthropic", "https://gw.example", "https://gw.example"),
            ("ollama", "http://host:11434/api/chat", "http://host:11434"),
            ("ollama", "http://host:11434/v1/chat/completions", "http://host:11434"),
            ("ollama", "http://host:11434/v1", "http://host:11434"),
            ("gemini", "https://generativelanguage.googleapis.com", "https://generativelanguage.googleapis.com/v1beta"),
            ("gemini", "https://gw.example/v1beta", "https://gw.example/v1beta"),
            (
                "bedrock",
                "https://bedrock-runtime.eu-west-1.amazonaws.com",
                "https://bedrock-runtime.eu-west-1.amazonaws.com",
            ),
            ("bedrock", "https://gw.example/model/amazon.nova-pro-v1%3A0/converse", "https://gw.example"),
            ("bedrock", "https://gw.example/model/m/converse-stream/", "https://gw.example"),
        ],
    )
    def test_a_full_endpoint_or_a_root_reduces_to_the_root_the_wire_extends(
        self, provider: str, given: str, root: str
    ) -> None:
        assert normalize_base_url(PROFILES[provider], given) == root

    def test_an_empty_value_means_no_override(self) -> None:
        assert normalize_base_url(PROFILES["openai"], "") is None
        assert normalize_base_url(PROFILES["openai"], None) is None


class TestSpeaksOpenAIBody:
    @pytest.mark.parametrize("model", ["openai/gpt-4o", "deepseek/deepseek-chat", "azure/my-deployment"])
    def test_openai_shaped_providers(self, model: str) -> None:
        assert speaks_openai_body(model)

    @pytest.mark.parametrize(
        "model",
        ["anthropic/claude-sonnet-4-5", "gemini/gemini-2.5-pro", "ollama/llama3", "bedrock/amazon.nova-pro-v1:0"],
    )
    def test_providers_with_their_own_protocol(self, model: str) -> None:
        assert not speaks_openai_body(model)

    def test_an_unresolvable_model_is_treated_as_openai_compatible(self) -> None:
        assert speaks_openai_body("mystery-model")

    def test_a_custom_provider_decides_for_a_bare_model(self) -> None:
        assert not speaks_openai_body("claude-x", custom_llm_provider="anthropic")
