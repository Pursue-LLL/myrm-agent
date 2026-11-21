"""Client attribution: the identity, the header set each gateway documents, and their wiring into create_chat_model."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.llms.core.attribution import (
    ClientAttribution,
    openrouter_headers,
    set_client_attribution,
    vercel_headers,
)
from myrm_agent_harness.toolkits.llms.core.llm import create_chat_model

_IDENTITY = ClientAttribution(
    site_url="https://app.example",
    app_name="Example App",
    openrouter_categories=("personal-agent", "general-chat"),
    vercel_user_agent="Example/1.0 (Vercel-AI-Gateway-Client)",
)
_VERCEL_URL = "https://ai-gateway.vercel.sh/v1"
_OPENROUTER_URL = "https://openrouter.ai/api/v1"


def _extra_headers(
    model: str, base_url: str | None = None, model_kwargs: Mapping[str, object] | None = None
) -> dict[str, str] | None:
    built = create_chat_model(model, base_url=base_url, api_key="sk-test", model_kwargs=model_kwargs or {})
    return (built.model_kwargs or {}).get("extra_headers")


class TestHeaderSets:
    def test_openrouter_names_and_categories(self) -> None:
        assert openrouter_headers(_IDENTITY) == {
            "HTTP-Referer": "https://app.example",
            "X-OpenRouter-Title": "Example App",
            "X-OpenRouter-Categories": "personal-agent,general-chat",
        }

    def test_vercel_names_and_user_agent(self) -> None:
        assert vercel_headers(_IDENTITY) == {
            "HTTP-Referer": "https://app.example",
            "X-Title": "Example App",
            "User-Agent": "Example/1.0 (Vercel-AI-Gateway-Client)",
        }

    def test_optional_fields_are_omitted_when_unset(self) -> None:
        minimal = ClientAttribution(site_url="https://app.example", app_name="Example App")
        assert openrouter_headers(minimal) == {
            "HTTP-Referer": "https://app.example",
            "X-OpenRouter-Title": "Example App",
        }
        assert vercel_headers(minimal) == {"HTTP-Referer": "https://app.example", "X-Title": "Example App"}


class TestIdentity:
    @pytest.mark.parametrize(
        "override",
        [
            {"site_url": "https://app.example/\u00e9"},
            {"app_name": "\u8682\u8681"},
            {"openrouter_categories": ("personal-agent", "\u901a\u7528")},
            {"vercel_user_agent": "Example/\u00e91.0"},
        ],
    )
    def test_non_ascii_header_values_are_rejected(self, override: dict[str, object]) -> None:
        fields: dict[str, object] = {"site_url": "https://app.example", "app_name": "Example App", **override}
        with pytest.raises(ValueError, match="must be ASCII"):
            ClientAttribution(**fields)  # type: ignore[arg-type]

    def test_identity_is_immutable(self) -> None:
        with pytest.raises(FrozenInstanceError):
            _IDENTITY.app_name = "Other"  # type: ignore[misc]


class TestCreateChatModelWiring:
    @pytest.mark.parametrize(
        ("model", "base_url", "build"),
        [
            ("gpt-4o", _VERCEL_URL, vercel_headers),
            ("anthropic/claude-3.5-sonnet", _OPENROUTER_URL, openrouter_headers),
            ("openrouter/google/gemini-2.0-flash", None, openrouter_headers),
            ("OpenRouter/google/gemini-2.0-flash", None, openrouter_headers),
        ],
    )
    def test_gateway_calls_carry_the_registered_identity(
        self, model: str, base_url: str | None, build: Callable[[ClientAttribution], dict[str, str]]
    ) -> None:
        set_client_attribution(_IDENTITY)
        assert _extra_headers(model, base_url) == build(_IDENTITY)

    def test_other_providers_get_no_attribution_headers(self) -> None:
        set_client_attribution(_IDENTITY)
        assert _extra_headers("gpt-4o", "https://api.openai.com/v1") is None

    @pytest.mark.parametrize(("model", "base_url"), [("gpt-4o", _VERCEL_URL), ("openrouter/x/y", None)])
    def test_nothing_is_sent_until_a_host_registers_an_identity(self, model: str, base_url: str | None) -> None:
        assert _extra_headers(model, base_url) is None

    def test_registration_can_be_removed(self) -> None:
        set_client_attribution(_IDENTITY)
        set_client_attribution(None)
        assert _extra_headers("gpt-4o", _VERCEL_URL) is None

    def test_a_caller_header_wins_in_any_letter_case(self) -> None:
        set_client_attribution(_IDENTITY)
        caller = {"extra_headers": {"http-referer": "https://own.example", "X-Custom": "1"}}
        assert _extra_headers("gpt-4o", _VERCEL_URL, model_kwargs=caller) == {
            "http-referer": "https://own.example",
            "X-Custom": "1",
            "X-Title": "Example App",
            "User-Agent": "Example/1.0 (Vercel-AI-Gateway-Client)",
        }

    def test_the_callers_model_kwargs_are_not_mutated(self) -> None:
        set_client_attribution(_IDENTITY)
        shared = {"extra_headers": {"X-Custom": "1"}}
        _extra_headers("gpt-4o", _VERCEL_URL, model_kwargs=shared)
        assert shared == {"extra_headers": {"X-Custom": "1"}}
        assert _extra_headers("gpt-4o", _OPENROUTER_URL, model_kwargs=shared) == {
            **openrouter_headers(_IDENTITY),
            "X-Custom": "1",
        }

    @patch("myrm_agent_harness.toolkits.llms.core.llm.TransportChatModel")
    def test_headers_reach_the_model_only_through_model_kwargs(self, transport: MagicMock) -> None:
        set_client_attribution(_IDENTITY)
        create_chat_model("gpt-4o", base_url=_VERCEL_URL)
        factory_kwargs = transport.call_args[1]
        assert factory_kwargs["model_kwargs"]["extra_headers"] == vercel_headers(_IDENTITY)
        assert "extra_headers" not in factory_kwargs

    def test_hooks_facade_registers_the_same_identity(self) -> None:
        from myrm_agent_harness.api import hooks

        assert hooks.ClientAttribution is ClientAttribution
        assert hooks.vercel_headers is vercel_headers
        hooks.set_client_attribution(_IDENTITY)
        assert _extra_headers("gpt-4o", _VERCEL_URL) == vercel_headers(_IDENTITY)
