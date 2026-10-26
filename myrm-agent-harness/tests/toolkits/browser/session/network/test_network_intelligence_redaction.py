"""NetworkIntelligence list lines and response bodies: credentials are masked before any cut."""

from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.browser.session.network.intelligence import NetworkIntelligence
from myrm_agent_harness.toolkits.browser.session.network.logger import POST_PREVIEW_CHARS, URL_PREVIEW_CHARS


class TestNetworkIntelligenceRedaction:
    """Credential redaction in CDP-tracked POST data display and response bodies.

    Raw post_data window is stored; get_summary redacts it before cutting it to the
    preview. Response bodies are redacted before the 8000-char truncation so a
    credential crossing the boundary stays masked.
    """

    def _on_post(self, ni: NetworkIntelligence, body: str) -> None:
        ni._on_request_will_be_sent(
            {
                "requestId": "req-post",
                "type": "Fetch",
                "request": {
                    "url": "https://api.example.com/login",
                    "method": "POST",
                    "postData": body,
                },
            }
        )

    def test_post_data_raw_window_kept_for_display_redaction(self):
        """The raw body (not the redacted form) is kept so get_summary can redact
        the whole window before the preview cut."""
        ni = NetworkIntelligence()
        raw = '{"op":"login","password":"mysecretvalue12345678"}'
        self._on_post(ni, raw)

        post_data = ni.get_api_requests()[0].post_data
        assert post_data == raw

    def test_get_summary_redacts_post_data(self):
        ni = NetworkIntelligence()
        self._on_post(ni, '{"op":"login","password":"mysecretvalue12345678"}')

        summary = ni.get_summary()

        assert "mysecretvalue12345678" not in summary
        assert "POST:" in summary

    def test_get_summary_crossing_preview_boundary_redacted(self):
        """A credential split by the display cut in get_summary must not
        surface as a plaintext fragment (raw window is redacted first)."""
        ni = NetworkIntelligence()
        body = '{"op":"login","pw":"' + "x" * 32 + '","password":"mysecretvalue12345678"}'
        assert body.index("mysecret") < POST_PREVIEW_CHARS < body.index("5678")  # the cut falls inside the credential
        self._on_post(ni, body)

        summary = ni.get_summary()

        assert "mysecretval" not in summary

    def test_get_summary_cuts_the_post_body_to_the_preview_limit(self):
        ni = NetworkIntelligence()
        self._on_post(ni, "x" * 500)

        assert ni.get_summary().splitlines()[1] == "     POST: " + "x" * (POST_PREVIEW_CHARS - 1) + "…"

    def test_get_summary_masks_a_url_credential_before_cutting_the_url(self):
        ni = NetworkIntelligence()
        key = "AIza" + "S" * 35  # a bare key is recognised only whole: a fragment of it passes the mask
        prefix = "https://api.example.com/data?p=" + "x" * 100 + "&k="
        kept_by_a_cut_first = URL_PREVIEW_CHARS - 1 - len(prefix)
        assert 0 < kept_by_a_cut_first < len("AIza") + 30  # the cut would end inside the key, too early to recognise it
        ni._on_request_will_be_sent(
            {"requestId": "req-1", "type": "XHR", "request": {"url": prefix + key + "&z=1", "method": "GET"}}
        )

        summary = ni.get_summary()

        assert "S" * 8 not in summary
        assert "&k=AIza" in summary

    def test_get_summary_marks_a_cut_url_and_leaves_a_short_one_whole(self):
        ni = NetworkIntelligence()
        long_url = "https://api.example.com/" + "a" * 300
        for request_id, url in (("long", long_url), ("short", "https://api.example.com/x")):
            ni._on_request_will_be_sent(
                {"requestId": request_id, "type": "XHR", "request": {"url": url, "method": "GET"}}
            )

        long_line, short_line = ni.get_summary().splitlines()

        assert long_line == f"  1. GET {long_url[: URL_PREVIEW_CHARS - 1]}… [pending]"
        assert short_line == "  2. GET https://api.example.com/x [pending]"

    def test_get_summary_plain_body_unchanged(self):
        ni = NetworkIntelligence()
        self._on_post(ni, '{"operationName":"GetIssues"}')

        summary = ni.get_summary()

        assert '{"operationName":"GetIssues"}' in summary

    @pytest.mark.asyncio
    async def test_get_response_body_truncation_crossing_redacted(self):
        """A credential in the truncated tail of a large response body must
        not surface as a plaintext fragment."""
        ni = NetworkIntelligence()
        ni._on_request_will_be_sent(
            {
                "requestId": "req-1",
                "type": "XHR",
                "request": {"url": "https://api.example.com/data", "method": "GET"},
            }
        )
        mock_cdp = AsyncMock()
        head = "x" * 7990
        tail = '"password":"mysecretvalue12345678"}'
        large_body = head + tail
        mock_cdp.send = AsyncMock(return_value={"body": large_body, "base64Encoded": False})
        ni._cdp_session = mock_cdp

        result = await ni.get_response_body(1)

        assert "truncated" in result
        assert "mysecretval" not in result
