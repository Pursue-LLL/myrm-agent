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
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for profile in PROFILES.values():
        for name in (*profile.api_key_env, *profile.api_base_env, *profile.api_version_env):
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


# Each provider's endpoint variables, strongest first.
_ENDPOINT_ENV: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_BASE_URL", "OPENAI_API_BASE"),
    "azure": ("AZURE_API_BASE", "AZURE_OPENAI_ENDPOINT"),
    "anthropic": ("ANTHROPIC_API_BASE", "ANTHROPIC_BASE_URL"),
    "gemini": ("GEMINI_API_BASE",),
    "ollama": ("OLLAMA_API_BASE",),
    "deepseek": ("DEEPSEEK_API_BASE",),
    "openrouter": ("OPENROUTER_API_BASE",),
    "zai": ("ZAI_API_BASE",),
    "xai": ("XAI_API_BASE",),
    "moonshot": ("MOONSHOT_API_BASE",),
    "lm_studio": ("LM_STUDIO_API_BASE",),
    "together_ai": ("TOGETHER_AI_API_BASE",),
    "volcengine": ("VOLCENGINE_API_BASE",),
    "fireworks_ai": ("FIREWORKS_API_BASE",),
    "minimax": ("MINIMAX_API_BASE",),
    "groq": ("GROQ_API_BASE",),
    "dashscope": ("DASHSCOPE_API_BASE",),
    "perplexity": ("PERPLEXITY_API_BASE",),
    "cohere_chat": ("COHERE_API_BASE",),
    "cerebras": ("CEREBRAS_API_BASE",),
}
_ENDPOINT_CASES = [(provider, name) for provider, names in _ENDPOINT_ENV.items() for name in names]


class TestEndpointFromEnvironment:
    """A call that names no endpoint takes the provider's own variable, then the provider's default endpoint."""

    def test_the_table_names_each_providers_endpoint_variables(self) -> None:
        assert {pid: p.api_base_env for pid, p in PROFILES.items() if p.api_base_env} == _ENDPOINT_ENV

    @pytest.mark.parametrize(("provider", "variable"), _ENDPOINT_CASES)
    def test_the_variable_replaces_the_default_endpoint(
        self, monkeypatch: pytest.MonkeyPatch, provider: str, variable: str
    ) -> None:
        monkeypatch.setenv(variable, "https://env.example")
        route = resolve_route(f"{provider}/some-model")
        assert route.base_url == normalize_base_url(PROFILES[provider], "https://env.example")
        assert route.base_url != PROFILES[provider].base_url

    @pytest.mark.parametrize("provider", ["mistral", "xiaomi_mimo", "yunshu", "bedrock"])
    def test_a_provider_without_endpoint_variables_ignores_the_ones_of_others(
        self, monkeypatch: pytest.MonkeyPatch, provider: str
    ) -> None:
        for names in _ENDPOINT_ENV.values():
            for name in names:
                monkeypatch.setenv(name, "https://env.example")
        assert resolve_route(f"{provider}/some-model").base_url == PROFILES[provider].base_url

    @pytest.mark.parametrize("provider", sorted(_ENDPOINT_ENV))
    def test_an_explicit_endpoint_wins_over_the_variable(self, monkeypatch: pytest.MonkeyPatch, provider: str) -> None:
        monkeypatch.setenv(_ENDPOINT_ENV[provider][0], "https://env.example")
        route = resolve_route(f"{provider}/some-model", api_base="https://explicit.example")
        assert route.base_url == normalize_base_url(PROFILES[provider], "https://explicit.example")

    @pytest.mark.parametrize(
        "provider", [provider for provider, names in _ENDPOINT_ENV.items() if len(names) > 1], ids=str
    )
    def test_the_stronger_variable_wins_when_a_provider_has_two(
        self, monkeypatch: pytest.MonkeyPatch, provider: str
    ) -> None:
        strong, weak = _ENDPOINT_ENV[provider]
        monkeypatch.setenv(weak, "https://weak.example")
        monkeypatch.setenv(strong, "https://strong.example")
        assert resolve_route(f"{provider}/some-model").base_url == "https://strong.example"

    def test_an_empty_variable_is_no_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "")
        monkeypatch.setenv("OPENAI_API_BASE", "https://weak.example/v1")
        assert resolve_route("openai/gpt-4o").base_url == "https://weak.example/v1"
        monkeypatch.setenv("OPENAI_API_BASE", "")
        assert resolve_route("openai/gpt-4o").base_url == "https://api.openai.com/v1"

    def test_a_variable_is_reduced_to_the_root_like_an_explicit_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://gw.example/v1/chat/completions/")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gw.example/v1/messages")
        assert resolve_route("openai/gpt-4o").base_url == "https://gw.example/v1"
        assert resolve_route("anthropic/claude-sonnet-4-5").base_url == "https://gw.example"

    def test_one_providers_variable_never_redirects_another(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example/v1")
        monkeypatch.setenv("OPENAI_API_BASE", "https://env.example/v1")
        route = resolve_route("deepseek/deepseek-chat")
        assert route.base_url == "https://api.deepseek.com"

    def test_azure_finds_its_resource_in_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert resolve_route("azure/my-deployment").base_url is None
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://res.openai.azure.com")
        assert resolve_route("azure/my-deployment").base_url == "https://res.openai.azure.com"

    def test_an_unknown_provider_still_needs_an_explicit_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example/v1")
        with pytest.raises(UnsupportedProviderError, match="Cannot resolve a provider"):
            resolve_route("mystery/model-1")

    def test_the_azure_api_version_has_its_own_variable(self) -> None:
        assert {pid: p.api_version_env for pid, p in PROFILES.items() if p.api_version_env} == {
            "azure": ("AZURE_API_VERSION",)
        }


# Each provider's credential variables, strongest first.
_KEY_ENV: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "azure": ("AZURE_API_KEY", "AZURE_OPENAI_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "ollama": ("OLLAMA_API_KEY",),
    "bedrock": ("AWS_BEARER_TOKEN_BEDROCK",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY", "OR_API_KEY"),
    "zai": ("ZAI_API_KEY",),
    "xai": ("XAI_API_KEY",),
    "moonshot": ("MOONSHOT_API_KEY",),
    "lm_studio": ("LM_STUDIO_API_KEY",),
    "mistral": ("MISTRAL_API_KEY",),
    "together_ai": ("TOGETHERAI_API_KEY", "TOGETHER_API_KEY", "TOGETHER_AI_API_KEY"),
    "volcengine": ("VOLCENGINE_API_KEY", "ARK_API_KEY"),
    "fireworks_ai": ("FIREWORKS_API_KEY", "FIREWORKS_AI_API_KEY", "FIREWORKSAI_API_KEY"),
    "minimax": ("MINIMAX_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "dashscope": ("DASHSCOPE_API_KEY",),
    "perplexity": ("PERPLEXITYAI_API_KEY", "PERPLEXITY_API_KEY"),
    "cohere_chat": ("COHERE_API_KEY", "CO_API_KEY"),
    "cerebras": ("CEREBRAS_API_KEY",),
    "xiaomi_mimo": ("XIAOMI_MIMO_API_KEY",),
    "yunshu": ("YUNSHU_API_KEY",),
}
_KEY_CASES = [(provider, name) for provider, names in _KEY_ENV.items() for name in names]


class TestCredentialFromEnvironment:
    """A call that carries no key takes the first of the provider's own variables that is set."""

    def test_the_table_names_each_providers_credential_variables(self) -> None:
        assert {pid: p.api_key_env for pid, p in PROFILES.items()} == _KEY_ENV

    @pytest.mark.parametrize(("provider", "variable"), _KEY_CASES)
    def test_each_variable_supplies_the_key(
        self, monkeypatch: pytest.MonkeyPatch, provider: str, variable: str
    ) -> None:
        monkeypatch.setenv(variable, "from-env")
        assert resolve_route(f"{provider}/some-model").api_key == "from-env"

    @pytest.mark.parametrize("provider", sorted(_KEY_ENV))
    def test_an_explicit_key_wins_over_every_variable(self, monkeypatch: pytest.MonkeyPatch, provider: str) -> None:
        for name in _KEY_ENV[provider]:
            monkeypatch.setenv(name, "from-env")
        assert resolve_route(f"{provider}/some-model", api_key="explicit").api_key == "explicit"

    @pytest.mark.parametrize("provider", [p for p, names in _KEY_ENV.items() if len(names) > 1])
    def test_the_strongest_variable_wins_when_several_are_set(
        self, monkeypatch: pytest.MonkeyPatch, provider: str
    ) -> None:
        for name in _KEY_ENV[provider]:
            monkeypatch.setenv(name, name)
        assert resolve_route(f"{provider}/some-model").api_key == _KEY_ENV[provider][0]


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
            ("gemini", "https://gw.example", "https://gw.example"),  # only Google's own host is missing a version
            ("gemini", "https://gw.example/", "https://gw.example"),
            ("openai", "https://gw.example", "https://gw.example"),  # most providers take the base as it is
            ("mistral", "https://api.mistral.ai", "https://api.mistral.ai/v1"),
            ("mistral", "https://api.mistral.ai/v1", "https://api.mistral.ai/v1"),
            ("mistral", "https://api.mistral.ai/v1/", "https://api.mistral.ai/v1"),
            ("mistral", "https://gw.example/mistral", "https://gw.example/mistral/v1"),
            ("mistral", "https://gw.example/v1/chat/completions", "https://gw.example/v1"),
            ("minimax", "https://api.minimaxi.com", "https://api.minimaxi.com/v1"),
            ("minimax", "https://api.minimaxi.com/v1", "https://api.minimaxi.com/v1"),
            ("minimax", "https://gw.example/minimax", "https://gw.example/minimax/v1"),
            ("minimax", "https://gw.example/v1/chat/completions", "https://gw.example/v1"),
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
