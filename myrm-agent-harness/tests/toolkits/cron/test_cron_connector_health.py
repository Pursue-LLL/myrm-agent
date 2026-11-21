"""Unit tests for connector health classification, redaction, destination keys and failure details."""

from __future__ import annotations

import string

import httpx
import pytest

from myrm_agent_harness.toolkits.cron.engine.connector_health import (
    ConnectorErrorCategory,
    ConnectorFailureDetail,
    classify_connector_error,
    delivery_target_key,
    redact_connector_url,
)


class TestConnectorUrlRedaction:
    def test_empty_or_none(self) -> None:
        assert redact_connector_url(None) == ""
        assert redact_connector_url("") == ""

    def test_basic_auth_redaction(self) -> None:
        url = "https://admin:mysecretpassword@api.example.com/v1/webhook"
        redacted = redact_connector_url(url)
        assert "mysecretpassword" not in redacted
        assert redacted == "https://admin:***@api.example.com/v1/webhook"

    def test_query_params_redaction(self) -> None:
        url = "https://api.example.com/webhook?token=secret123&channel=alerts&api_key=key999"
        redacted = redact_connector_url(url)
        assert "secret123" not in redacted
        assert "key999" not in redacted
        assert "token=" in redacted
        assert "api_key=" in redacted
        assert "channel=alerts" in redacted

    def test_safe_url_unchanged(self) -> None:
        url = "https://hooks.slack.com/services/T00/B00/safe"
        assert redact_connector_url(url) == url

    def test_malformed_urls_do_not_raise(self) -> None:
        assert redact_connector_url("not_a_valid_url") == "not_a_valid_url"
        assert redact_connector_url("http://user:pass@") == "http://user:***@"

    def test_an_empty_secret_parameter_stays_a_parameter(self) -> None:
        assert "token=" in redact_connector_url("https://example.com/?token=")


class TestConnectorErrorClassification:
    @pytest.mark.parametrize(
        ("text", "category"),
        [
            ("Webhook returned 401: Unauthorized", ConnectorErrorCategory.AUTH_FAILURE),
            ("Webhook returned 403: Forbidden", ConnectorErrorCategory.AUTH_FAILURE),
            ("Webhook returned 404: Not Found", ConnectorErrorCategory.HTTP_CLIENT_ERROR),
            ("Webhook returned 429: Too Many Requests", ConnectorErrorCategory.HTTP_CLIENT_ERROR),
            ("Webhook returned 502: Bad Gateway", ConnectorErrorCategory.HTTP_SERVER_ERROR),
            ("Webhook returned 503: Service Unavailable", ConnectorErrorCategory.HTTP_SERVER_ERROR),
            ("Webhook returned 504: Gateway Timeout", ConnectorErrorCategory.TIMEOUT),
            ("ConnectTimeout: connection timed out after 10s", ConnectorErrorCategory.TIMEOUT),
            ("Name or service not known (DNS failure)", ConnectorErrorCategory.NETWORK_UNREACHABLE),
            ("All connection attempts failed", ConnectorErrorCategory.NETWORK_UNREACHABLE),
            ("Invalid json response payload too large", ConnectorErrorCategory.PAYLOAD_CONTRACT),
            ("Broken pipe on stdio socket", ConnectorErrorCategory.PROCESS_ERROR),
            ("Unknown internal anomaly", ConnectorErrorCategory.UNKNOWN),
        ],
    )
    def test_error_text_patterns(self, text: str, category: ConnectorErrorCategory) -> None:
        assert classify_connector_error(text)[0] == category

    def test_an_exception_is_classified_by_its_text(self) -> None:
        class CustomNetworkError(OSError):
            pass

        category, _ = classify_connector_error(CustomNetworkError("Connection reset by peer"))
        assert category == ConnectorErrorCategory.NETWORK_UNREACHABLE

    @pytest.mark.parametrize(
        "error",
        [TimeoutError(), httpx.ReadTimeout(""), httpx.ConnectTimeout("")],
        ids=["TimeoutError", "ReadTimeout", "ConnectTimeout"],
    )
    def test_a_timeout_without_text_is_still_a_timeout(self, error: Exception) -> None:
        assert str(error) == ""
        assert classify_connector_error(error)[0] == ConnectorErrorCategory.TIMEOUT

    def test_an_exception_without_text_is_summarised_by_its_type(self) -> None:
        category, summary = classify_connector_error(RuntimeError())
        assert category == ConnectorErrorCategory.UNKNOWN
        assert summary == "RuntimeError"

    @pytest.mark.parametrize("error", [None, ""])
    def test_no_error_reads_as_unknown(self, error: str | None) -> None:
        category, summary = classify_connector_error(error)
        assert category == ConnectorErrorCategory.UNKNOWN
        assert "Unknown error" in summary


class TestDeliveryTargetKey:
    URL = "https://api.example.com/hook?token=secret123"

    @pytest.mark.parametrize("channel", ["chat", "silent", "none"])
    def test_an_in_app_channel_has_no_destination(self, channel: str) -> None:
        assert delivery_target_key(channel, self.URL) == ""

    @pytest.mark.parametrize("target", [None, "", "   "])
    def test_an_outbound_channel_without_an_address_has_no_destination(self, target: str | None) -> None:
        assert delivery_target_key("webhook", target) == ""

    def test_the_same_destination_has_the_same_key(self) -> None:
        assert delivery_target_key("webhook", self.URL) == delivery_target_key("webhook", f"  {self.URL}\n")

    def test_the_key_is_a_digest_that_does_not_expose_the_address(self) -> None:
        key = delivery_target_key("webhook", self.URL)
        assert len(key) == 32
        assert set(key) <= set(string.hexdigits.lower())
        assert "secret123" not in key

    @pytest.mark.parametrize(
        ("other_channel", "other_target"),
        [
            ("feishu", URL),
            ("webhook", "https://api.example.com/hook?token=secret124"),
            ("webhook", "https://api.example.com/hook?token=SECRET123"),
        ],
        ids=["other-channel", "other-token", "other-case"],
    )
    def test_another_destination_has_another_key(self, other_channel: str, other_target: str) -> None:
        assert delivery_target_key(other_channel, other_target) != delivery_target_key("webhook", self.URL)

    def test_the_channel_and_the_address_cannot_be_shifted_into_each_other(self) -> None:
        assert delivery_target_key("ab", "c") != delivery_target_key("a", "bc")


class TestConnectorFailureDetail:
    def test_to_dict_schema(self) -> None:
        detail = ConnectorFailureDetail(
            category=ConnectorErrorCategory.HTTP_SERVER_ERROR,
            target="https://api.example.com/hook",
            message="Bad Gateway",
        )
        d = detail.to_dict()
        assert set(d) == {"category", "target", "message", "timestamp"}
        assert d["category"] == "http_server_error"
        assert d["target"] == "https://api.example.com/hook"
        assert d["message"] == "Bad Gateway"
