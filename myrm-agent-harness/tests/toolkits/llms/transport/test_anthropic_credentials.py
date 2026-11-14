"""Anthropic credentials: which header carries the key, how a subscription token is sent, and the beta flags it needs.

The golden credentials test pins what the baseline client library sent; these tests pin the rules behind it, and the
cases where the transport deliberately sends less (one Authorization header, no bearer next to the vendor's key).
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.llms.transport import anthropic_messages
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

_MODEL = "anthropic/claude-sonnet-4-5-20991231"  # a dated id the catalog does not list: only the name decides
_MESSAGES = [{"role": "user", "content": "hi"}]
_SUBSCRIPTION_TOKEN = "sk-ant-oat01-subscription-token"
_SCHEMA = {"type": "json_schema", "json_schema": {"name": "r", "schema": {"type": "object", "properties": {}}}}
_OFFICIAL, _GATEWAY = None, "https://gateway.example/anthropic"


def _headers(key: str, api_base: str | None = _OFFICIAL, **params: object) -> dict[str, str]:
    route = resolve_route(_MODEL, api_key=key, api_base=api_base)
    request = anthropic_messages.prepare(route, _MESSAGES, params)
    return {name.lower(): value for name, value in request.headers.items()}


class TestApiKey:
    def test_the_vendor_reads_the_key_header_alone(self) -> None:
        assert _headers("sk-ant-api03-key") == {"anthropic-version": "2023-06-01", "x-api-key": "sk-ant-api03-key"}

    def test_a_gateway_also_gets_the_key_as_a_bearer_token(self) -> None:
        headers = _headers("sk-ant-api03-key", _GATEWAY)

        assert headers["x-api-key"] == "sk-ant-api03-key"
        assert headers["authorization"] == "Bearer sk-ant-api03-key"


class TestSubscriptionToken:
    def test_it_is_a_bearer_credential_with_its_beta_flag_and_no_key_header(self) -> None:
        assert _headers(_SUBSCRIPTION_TOKEN) == {
            "anthropic-version": "2023-06-01",
            "authorization": f"Bearer {_SUBSCRIPTION_TOKEN}",
            "anthropic-beta": "oauth-2025-04-20",
            "anthropic-dangerous-direct-browser-access": "true",
        }

    def test_a_gateway_gets_it_the_same_way_with_one_authorization_header(self) -> None:
        route = resolve_route(_MODEL, api_key=_SUBSCRIPTION_TOKEN, api_base=_GATEWAY)
        request = anthropic_messages.prepare(route, _MESSAGES, {})

        assert _headers(_SUBSCRIPTION_TOKEN, _GATEWAY) == _headers(_SUBSCRIPTION_TOKEN)
        assert sum(name.lower() == "authorization" for name in request.headers) == 1

    def test_the_token_prefix_decides_not_the_host(self) -> None:
        assert "x-api-key" not in _headers(_SUBSCRIPTION_TOKEN, _GATEWAY)
        assert "anthropic-beta" not in _headers("sk-ant-api03-key", _GATEWAY)

    def test_caller_flags_stay_next_to_the_subscription_flag(self) -> None:
        headers = _headers(_SUBSCRIPTION_TOKEN, extra_headers={"anthropic-beta": "context-1m-2025-08-07"})

        assert headers["anthropic-beta"].split(",") == ["context-1m-2025-08-07", "oauth-2025-04-20"]

    def test_the_structured_output_flag_joins_the_subscription_flag(self) -> None:
        headers = _headers(_SUBSCRIPTION_TOKEN, response_format=_SCHEMA)

        assert headers["anthropic-beta"].split(",") == ["oauth-2025-04-20", "structured-outputs-2025-11-13"]

    def test_a_flag_the_caller_already_sent_is_not_repeated(self) -> None:
        headers = _headers(_SUBSCRIPTION_TOKEN, extra_headers={"anthropic-beta": "oauth-2025-04-20"})

        assert headers["anthropic-beta"] == "oauth-2025-04-20"
