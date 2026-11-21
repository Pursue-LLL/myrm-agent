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

    def test_host_port_and_path_stay_as_written(self) -> None:
        url = "https://hooks.slack.com:443/services/T00/B00/looks-like-a-secret?channel=alerts"
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
            ("Feishu bot webhook returned 400: Bad Request", ConnectorErrorCategory.HTTP_CLIENT_ERROR),
            ("Feishu bot webhook error code=19024: Key Words Not Found", ConnectorErrorCategory.HTTP_CLIENT_ERROR),
            ("WeCom bot webhook errcode=93000: invalid webhook url", ConnectorErrorCategory.HTTP_CLIENT_ERROR),
            ("Too many redirects (limit: 5) for https://hooks.example.com/a", ConnectorErrorCategory.HTTP_CLIENT_ERROR),
            ("Webhook returned 502: Bad Gateway", ConnectorErrorCategory.HTTP_SERVER_ERROR),
            ("Webhook returned 503: Service Unavailable", ConnectorErrorCategory.HTTP_SERVER_ERROR),
            ("Webhook returned 504: Gateway Timeout", ConnectorErrorCategory.TIMEOUT),
            ("ConnectTimeout: connection timed out after 10s", ConnectorErrorCategory.TIMEOUT),
            ("Name or service not known (DNS failure)", ConnectorErrorCategory.NETWORK_UNREACHABLE),
            ("DNS resolution failed for hooks.example.com", ConnectorErrorCategory.NETWORK_UNREACHABLE),
            ("All connection attempts failed", ConnectorErrorCategory.NETWORK_UNREACHABLE),
            ("[Errno 32] Broken pipe", ConnectorErrorCategory.NETWORK_UNREACHABLE),
            ("Server disconnected without sending a response.", ConnectorErrorCategory.NETWORK_UNREACHABLE),
            (
                "peer closed connection without sending complete message body (received 7 bytes, expected 100)",
                ConnectorErrorCategory.NETWORK_UNREACHABLE,
            ),
            ("Invalid json response payload too large", ConnectorErrorCategory.PAYLOAD_CONTRACT),
            ("Content too large", ConnectorErrorCategory.PAYLOAD_CONTRACT),
            (
                "Webhook response body too large: Response body exceeds 1048576 byte limit",
                ConnectorErrorCategory.PAYLOAD_CONTRACT,
            ),
            ("illegal status line: bytearray(b'not http at all')", ConnectorErrorCategory.PAYLOAD_CONTRACT),
            ("illegal status line: bytearray(b'* OK ssl dns ready')", ConnectorErrorCategory.PAYLOAD_CONTRACT),
            ("Blocked URL scheme: ftp", ConnectorErrorCategory.ADDRESS_REJECTED),
            ("Blocked URL scheme: ", ConnectorErrorCategory.ADDRESS_REJECTED),
            ("Blocked hostname: localhost", ConnectorErrorCategory.ADDRESS_REJECTED),
            ("Blocked hostname suffix: printer.local", ConnectorErrorCategory.ADDRESS_REJECTED),
            ("Missing hostname", ConnectorErrorCategory.ADDRESS_REJECTED),
            ("Malformed URL", ConnectorErrorCategory.ADDRESS_REJECTED),
            ("Hostname contains percent-encoding", ConnectorErrorCategory.ADDRESS_REJECTED),
            ("Invalid hostname", ConnectorErrorCategory.ADDRESS_REJECTED),
            ("Invalid port", ConnectorErrorCategory.ADDRESS_REJECTED),
            ("URL contains parser-confusing characters", ConnectorErrorCategory.ADDRESS_REJECTED),
            (
                "Access to internal network is blocked for security reasons. "
                "Blocked IP: 192.168.1.20 is a non-public IP address",
                ConnectorErrorCategory.ADDRESS_REJECTED,
            ),
            ("ReadError", ConnectorErrorCategory.NETWORK_UNREACHABLE),
            ("WriteError", ConnectorErrorCategory.NETWORK_UNREACHABLE),
            ("ConnectError", ConnectorErrorCategory.NETWORK_UNREACHABLE),
            ("ThreadError", ConnectorErrorCategory.UNKNOWN),
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

    @pytest.mark.parametrize(
        "error",
        [httpx.ReadError(""), httpx.WriteError(""), httpx.ConnectError("")],
        ids=["ReadError", "WriteError", "ConnectError"],
    )
    def test_a_network_error_without_text_is_still_a_network_error(self, error: Exception) -> None:
        assert str(error) == ""
        assert classify_connector_error(error)[0] == ConnectorErrorCategory.NETWORK_UNREACHABLE

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

    @pytest.mark.parametrize("channel", ["webhook", "chat", "silent", "none"])
    @pytest.mark.parametrize("target", [None, "", "   "])
    def test_a_delivery_without_an_address_has_no_destination(self, channel: str, target: str | None) -> None:
        assert delivery_target_key(channel, target) == ""

    @pytest.mark.parametrize("channel", ["chat", "silent", "none"])
    def test_which_channels_leave_the_application_is_not_decided_here(self, channel: str) -> None:
        assert delivery_target_key(channel, self.URL) != ""

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
        )
        assert detail.to_dict() == {"category": "http_server_error", "target": "https://api.example.com/hook"}
