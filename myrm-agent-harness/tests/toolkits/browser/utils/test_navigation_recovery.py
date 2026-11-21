"""Recovery steps a failed navigation shows the Agent: one set per kind of failure, a generic set otherwise."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.browser.utils.navigation_recovery import navigation_recovery_suggestions

_GENERIC = "Verify the URL is correct and accessible"
_CERTIFICATE_REJECTIONS = [
    "net::ERR_CERT_AUTHORITY_INVALID",
    "net::ERR_CERT_COMMON_NAME_INVALID",
    "net::ERR_CERT_DATE_INVALID",
    "net::ERR_CERT_REVOKED",
]


def _goto_error(chromium_error: str) -> str:
    return f"Page.goto: {chromium_error} at https://site.example/"


class TestHttpStatus:
    @pytest.mark.parametrize(
        ("status_code", "expected"),
        [(404, "URL not found"), (403, "Access forbidden"), (500, "Server error"), (502, "HTTP 502 error")],
    )
    def test_an_error_status_gets_its_own_advice(self, status_code: int, expected: str) -> None:
        hints = navigation_recovery_suggestions(status_code, None)

        assert expected in hints[0]
        assert _GENERIC not in hints

    @pytest.mark.parametrize("status_code", [None, 0, 200, 301])
    def test_a_status_that_is_no_error_gets_the_generic_advice(self, status_code: int | None) -> None:
        assert navigation_recovery_suggestions(status_code, None)[0] == _GENERIC


class TestChromiumError:
    @pytest.mark.parametrize(
        ("chromium_error", "expected"),
        [
            ("net::ERR_NAME_NOT_RESOLVED", "DNS resolution failed"),
            ("net::ERR_CONNECTION_REFUSED", "Connection refused"),
            ("net::ERR_TIMED_OUT", "Connection timed out"),
            ("net::ERR_SOCKS_CONNECTION_FAILED", "network policy"),
        ],
    )
    def test_a_known_error_gets_its_own_advice(self, chromium_error: str, expected: str) -> None:
        hints = navigation_recovery_suggestions(None, _goto_error(chromium_error))

        assert expected in hints[0]
        assert _GENERIC not in hints

    def test_a_status_and_an_error_add_up(self) -> None:
        hints = navigation_recovery_suggestions(404, _goto_error("net::ERR_NAME_NOT_RESOLVED"))

        assert "URL not found" in hints[0]
        assert any("DNS resolution failed" in hint for hint in hints)

    @pytest.mark.parametrize("error_text", ["", "no response before the navigation deadline", "boom"])
    def test_an_error_nobody_classified_gets_the_generic_advice(self, error_text: str) -> None:
        assert navigation_recovery_suggestions(None, error_text)[0] == _GENERIC


class TestRejectedCertificate:
    @pytest.mark.parametrize("chromium_error", _CERTIFICATE_REJECTIONS)
    def test_every_certificate_rejection_gets_the_certificate_advice(self, chromium_error: str) -> None:
        hints = navigation_recovery_suggestions(None, _goto_error(chromium_error))

        assert "certificate" in hints[0]
        assert _GENERIC not in hints

    def test_the_advice_is_to_report_the_problem_not_to_work_around_the_check(self) -> None:
        hints = navigation_recovery_suggestions(None, _goto_error(_CERTIFICATE_REJECTIONS[0]))

        assert "report" in hints[-1]
        assert "user" in hints[-1]

    def test_the_advice_names_no_operator_setting(self) -> None:
        text = " ".join(navigation_recovery_suggestions(None, _goto_error(_CERTIFICATE_REJECTIONS[0])))

        assert "ignore_https_errors" not in text
        assert "MYRM_" not in text
        assert "environment variable" not in text

    @pytest.mark.parametrize(
        "chromium_error",
        [
            "net::ERR_NAME_NOT_RESOLVED",
            "net::ERR_CONNECTION_REFUSED",
            "net::ERR_TIMED_OUT",
            "net::ERR_SOCKS_CONNECTION_FAILED",
        ],
    )
    def test_other_failures_never_mention_certificates(self, chromium_error: str) -> None:
        text = " ".join(navigation_recovery_suggestions(None, _goto_error(chromium_error)))

        assert "certificate" not in text
