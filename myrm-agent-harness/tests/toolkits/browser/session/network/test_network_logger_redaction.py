"""NetworkLogger POST body and URL previews: credentials are masked before the cut, never split by it."""

from unittest.mock import Mock, PropertyMock

from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.toolkits.browser.session.network.logger import (
    POST_PREVIEW_CHARS,
    URL_PREVIEW_CHARS,
    NetworkLogger,
    safe_preview,
)


class TestNetworkLoggerRedaction:
    """POST body preview credential redaction.

    post_data_preview is credential-redacted before the preview cut (POST_PREVIEW_CHARS),
    covering both intact JSON bodies and bodies whose sensitive value crosses
    the preview boundary.
    """

    def _run(self, raw: str) -> str:
        logger = NetworkLogger()
        req = Mock()
        req.method = "POST"
        req.resource_type = "fetch"
        req.post_data = raw
        resp = Mock()
        resp.request = req
        resp.status = 200
        resp.status_text = "OK"
        logger._on_request(req)
        logger._on_response(resp)
        assert logger._requests[0].post_data_preview is not None
        return logger._requests[0].post_data_preview

    def test_intact_json_password_redacted(self):
        preview = self._run('{"op":"login","password":"mysecretvalue12345678"}')

        assert "mysecretvalue12345678" not in preview

    def test_intact_json_api_key_redacted(self):
        preview = self._run('{"token":"sk-proj-abcdefghijklmnop12345678"}')

        assert "sk-proj-abcdefghijklmnop12345678" not in preview
        assert "***" in preview

    def test_credential_crossing_preview_boundary_redacted(self):
        """A credential the preview cut would split stays masked: no fragment of it reaches the preview."""
        body = '{"op":"login","pw":"' + "x" * 32 + '","password":"mysecretvalue12345678"}'
        assert body.index("mysecret") < POST_PREVIEW_CHARS < body.index("5678")  # the cut falls inside the credential
        preview = self._run(body)

        assert "mysecretval" not in preview
        assert "mysecretvalue" not in preview

    def test_a_long_body_is_cut_to_the_preview_limit_and_says_so(self):
        preview = self._run("x" * 500)

        assert preview == "x" * (POST_PREVIEW_CHARS - 1) + "…"

    def test_a_body_that_is_not_text_keeps_the_record(self):
        """The driver raises for a body that is not UTF-8 text; the request must still be logged."""
        logger = NetworkLogger()
        req = Mock()
        req.method = "POST"
        req.resource_type = "fetch"
        type(req).post_data = PropertyMock(side_effect=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"))
        resp = Mock()
        resp.request = req
        resp.status = 200
        resp.status_text = "OK"
        logger._on_request(req)
        logger._on_response(resp)

        assert len(logger._requests) == 1
        assert logger._requests[0].post_data_preview == "<binary body>"

    def test_form_urlencoded_password_redacted(self):
        preview = self._run("grant_type=password&username=u&password=supersecretvalue123")

        assert "supersecretvalue123" not in preview

    def test_get_method_no_post_preview(self):
        logger = NetworkLogger()
        req = Mock()
        req.method = "GET"
        req.resource_type = "fetch"
        req.post_data = None
        resp = Mock()
        resp.request = req
        resp.status = 200
        resp.status_text = "OK"
        logger._on_request(req)
        logger._on_response(resp)

        assert logger._requests[0].post_data_preview is None

    def test_get_summary_redacts_post_body(self):
        logger = NetworkLogger()
        req = Mock()
        req.method = "POST"
        req.resource_type = "fetch"
        req.post_data = '{"password":"mysecretvalue12345678"}'
        resp = Mock()
        resp.request = req
        resp.status = 200
        resp.status_text = "OK"
        logger._on_request(req)
        logger._on_response(resp)

        summary = logger.get_summary()

        assert "mysecretvalue12345678" not in summary
        assert "POST body:" in summary


class TestSafePreview:
    """Credentials are masked first and the cut is made afterwards, so a credential the cut splits leaves no fragment."""

    def test_text_within_the_limit_is_returned_whole(self):
        assert safe_preview("GET /x", POST_PREVIEW_CHARS) == "GET /x"
        assert safe_preview("a" * URL_PREVIEW_CHARS, URL_PREVIEW_CHARS) == "a" * URL_PREVIEW_CHARS

    def test_a_cut_text_fills_the_limit_and_ends_with_an_ellipsis(self):
        preview = safe_preview("a" * 500, URL_PREVIEW_CHARS)

        assert preview == "a" * (URL_PREVIEW_CHARS - 1) + "…"

    def test_a_credential_split_by_the_cut_leaves_no_fragment(self):
        key = "AIza" + "S" * 35  # a bare key is recognised only whole: a fragment of it passes the mask
        prefix = "https://cdn.example.com/a.js?p=" + "x" * 100 + "&k="
        kept_by_a_cut_first = URL_PREVIEW_CHARS - 1 - len(prefix)
        assert 0 < kept_by_a_cut_first < len("AIza") + 30  # the cut would end inside the key, too early to recognise it
        url = prefix + key + "&z=" + "y" * 100

        preview = safe_preview(url, URL_PREVIEW_CHARS)

        assert preview == f"{redact_sensitive_text(url)[: URL_PREVIEW_CHARS - 1]}…"
        assert "S" * 8 not in preview
