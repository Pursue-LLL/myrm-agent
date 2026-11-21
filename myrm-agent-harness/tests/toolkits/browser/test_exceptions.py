"""Redaction guarantees for the browser exception hierarchy.

Covers credential masking at construction (str(e) is the propagation path to the
LLM) and in format_for_llm(), plus the RefNotFoundError URL-change suggestion,
which must not surface full query strings, and the recovery hints a connection
the network policy refused and a certificate the browser rejected get.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.browser.exceptions import (
    BrowserError,
    BrowserNavigationError,
    RefNotFoundError,
)


class TestBrowserErrorRedaction:
    def test_message_credential_redacted_at_construction(self) -> None:
        err = BrowserError("Navigation failed for https://app.com/callback?code=4d3f9c2a1b8e")
        assert "4d3f9c2a1b8e" not in str(err)
        assert "code=***" in str(err)

    def test_plain_message_unchanged(self) -> None:
        err = BrowserError("Element not found in snapshot")
        assert str(err) == "Element not found in snapshot"

    def test_format_for_llm_redacts_context_and_diagnostics(self) -> None:
        err = BrowserError(
            "Request failed",
            context={"url": "https://app.com/callback?code=9f8e7d6c5b4a"},
            diagnostic_info={"token": "sk-proj-abcdef123456"},
            recovery_suggestions=["verify token sk-proj-abcdef123456"],
        )
        out = err.format_for_llm()
        assert "9f8e7d6c5b4a" not in out
        assert "sk-proj-abcdef123456" not in out
        assert "Request failed" in out

    def test_format_for_llm_preserves_plain_content(self) -> None:
        err = BrowserError("Timeout after 30s", error_code="NAV_TIMEOUT")
        out = err.format_for_llm()
        assert "Timeout after 30s" in out
        assert "NAV_TIMEOUT" in out


class TestRefNotFoundErrorRedaction:
    def _build(self, current_url: str, last_url: str) -> RefNotFoundError:
        return RefNotFoundError(
            ref="e999",
            total_refs=5,
            ref_range="e0-e4",
            context_refs=[{"ref": "e0", "role": "button", "name": "Submit"}],
            last_snapshot_url=last_url,
            context={"page_url": current_url},
        )

    def test_query_credential_never_surfaces_in_message(self) -> None:
        last_url = "https://app.com/checkout"
        current_url = "https://app.com/callback?code=4d3f9c2a1b8e7f6d"
        err = self._build(current_url, last_url)
        assert "4d3f9c2a1b8e7f6d" not in str(err)
        assert "Page has navigated from" in str(err)

    def test_query_credential_redacted_in_query_change_message(self) -> None:
        last_url = "https://app.com/checkout"
        current_url = "https://app.com/checkout?code=4d3f9c2a1b8e7f6d"
        err = self._build(current_url, last_url)
        assert "4d3f9c2a1b8e7f6d" not in str(err)
        assert "code=***" in str(err)

    def test_query_change_message_redacted(self) -> None:
        last_url = "https://app.com/checkout"
        current_url = "https://app.com/checkout?session=abc123xyz789"
        err = self._build(current_url, last_url)
        assert "abc123xyz789" not in str(err)
        assert "Query params changed" in str(err)

    def test_plain_navigation_kept_readable(self) -> None:
        err = self._build(
            "https://app.com/settings",
            "https://app.com/checkout",
        )
        msg = str(err)
        assert "Page has navigated from" in msg
        assert "app.com" in msg


class TestNavigationErrorEgressRefusal:
    def test_a_refused_connection_points_at_the_network_policy(self) -> None:
        err = BrowserNavigationError(
            "Navigation failed",
            url="http://internal.example/",
            error_text="Page.goto: net::ERR_SOCKS_CONNECTION_FAILED at http://internal.example/",
        )

        hints = " ".join(err.recovery_suggestions)
        assert "network policy" in hints
        assert "private network" in hints

    def test_other_connection_failures_keep_their_own_hints(self) -> None:
        err = BrowserNavigationError("Navigation failed", error_text="net::ERR_CONNECTION_REFUSED")

        assert "network policy" not in " ".join(err.recovery_suggestions)


class TestNavigationErrorCertificateRejection:
    def test_a_rejected_certificate_gets_certificate_advice_in_what_the_agent_reads(self) -> None:
        err = BrowserNavigationError(
            "Navigation failed",
            url="https://self-signed.example/",
            error_text="Page.goto: net::ERR_CERT_AUTHORITY_INVALID at https://self-signed.example/",
        )

        assert "certificate" in err.recovery_suggestions[0]
        assert "certificate" in err.format_for_llm()

    def test_other_failures_do_not_mention_certificates(self) -> None:
        err = BrowserNavigationError("Navigation failed", error_text="net::ERR_CONNECTION_REFUSED")

        assert "certificate" not in " ".join(err.recovery_suggestions)
