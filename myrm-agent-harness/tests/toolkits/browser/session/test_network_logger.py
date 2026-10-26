"""Unit tests for NetworkLogger — network request capture and filtering."""

import time
from unittest.mock import Mock, PropertyMock

from patchright.async_api import Page

from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.toolkits.browser.session.network_logger import (
    POST_PREVIEW_CHARS,
    URL_PREVIEW_CHARS,
    NetworkLogger,
    RequestInfo,
    safe_preview,
)


class TestRequestInfo:
    """Test RequestInfo dataclass."""

    def test_is_api_request(self):
        """Test is_api_request property."""
        xhr_req = RequestInfo(
            method="GET",
            url="https://api.example.com/data",
            resource_type="xhr",
            timestamp=0.0,
        )
        assert xhr_req.is_api_request

        fetch_req = RequestInfo(
            method="POST",
            url="https://api.example.com/submit",
            resource_type="fetch",
            timestamp=0.0,
        )
        assert fetch_req.is_api_request

        doc_req = RequestInfo(
            method="GET",
            url="https://example.com",
            resource_type="document",
            timestamp=0.0,
        )
        assert not doc_req.is_api_request

    def test_is_failed(self):
        """Test is_failed property."""
        success_req = RequestInfo(
            method="GET",
            url="https://example.com",
            resource_type="xhr",
            timestamp=0.0,
            status=200,
        )
        assert not success_req.is_failed

        error_req = RequestInfo(
            method="GET",
            url="https://example.com",
            resource_type="xhr",
            timestamp=0.0,
            status=404,
        )
        assert error_req.is_failed

        server_error = RequestInfo(
            method="POST",
            url="https://example.com",
            resource_type="fetch",
            timestamp=0.0,
            status=500,
        )
        assert server_error.is_failed

        no_status = RequestInfo(
            method="GET",
            url="https://example.com",
            resource_type="xhr",
            timestamp=0.0,
        )
        assert not no_status.is_failed


class TestNetworkLogger:
    """Test NetworkLogger functionality."""

    def test_initialization(self):
        """Test logger initialization."""
        logger = NetworkLogger()
        assert len(logger._requests) == 0
        assert logger.get_pending_count() == 0
        assert logger.bound_page is None

        logger_custom = NetworkLogger(max_requests=10)
        assert len(logger_custom._requests) == 0

    def test_should_capture_filters_static_resources(self):
        """Test static resource filtering."""
        logger = NetworkLogger()

        assert not logger._should_capture("image")
        assert not logger._should_capture("stylesheet")
        assert not logger._should_capture("font")
        assert not logger._should_capture("media")

        assert logger._should_capture("xhr")
        assert logger._should_capture("fetch")
        assert logger._should_capture("document")

    def test_fifo_behavior(self):
        """Test FIFO storage with max_requests limit."""
        logger = NetworkLogger(max_requests=3)

        for i in range(5):
            info = RequestInfo(
                method="GET",
                url=f"https://example.com/{i}",
                resource_type="xhr",
                timestamp=float(i),
            )
            logger._requests.append(info)

        assert len(logger._requests) == 3
        urls = [r.url for r in logger._requests]
        assert urls == [
            "https://example.com/2",
            "https://example.com/3",
            "https://example.com/4",
        ]

    def test_get_summary_lists_only_api_requests(self):
        logger = NetworkLogger()
        for method, url, resource_type in [
            ("GET", "https://example.com/page", "document"),
            ("GET", "https://api.example.com/data", "xhr"),
            ("POST", "https://api.example.com/submit", "fetch"),
        ]:
            logger._requests.append(RequestInfo(method=method, url=url, resource_type=resource_type, timestamp=0.0))

        summary = logger.get_summary()

        assert "2 total" in summary
        assert "GET https://api.example.com/data" in summary
        assert "POST https://api.example.com/submit" in summary
        assert "https://example.com/page" not in summary

    def test_get_failed_summary_lists_failed_non_api_requests_one_line_each_without_numbers(self):
        logger = NetworkLogger()
        logger._requests.extend(
            [
                RequestInfo("GET", "https://example.com/app.js", "script", 0.0, status=404),
                RequestInfo("GET", "https://example.com/ok.js", "script", 1.0, status=200),
                RequestInfo("GET", "https://api.example.com/gone", "xhr", 2.0, status=404),
                RequestInfo("GET", "https://example.com/", "document", 3.0, status=503),
                RequestInfo("GET", "https://example.com/dead.js", "script", 4.0, status_text="Request Failed"),
            ]
        )

        assert logger.get_failed_summary().splitlines() == [
            "Other failed requests (not numbered, so network_detail cannot open them):",
            "  script GET https://example.com/app.js [404]",
            "  document GET https://example.com/ [503]",
        ]

    def test_get_failed_summary_is_empty_when_no_non_api_request_failed(self):
        logger = NetworkLogger()
        logger._requests.extend(
            [
                RequestInfo("GET", "https://api.example.com/gone", "xhr", 0.0, status=404),
                RequestInfo("GET", "https://example.com/ok.js", "script", 1.0, status=200),
            ]
        )

        assert logger.get_failed_summary() == ""

    def test_get_failed_summary_keeps_the_latest_and_counts_the_rest(self):
        logger = NetworkLogger(max_requests=50)
        for i in range(25):
            logger._requests.append(RequestInfo("GET", f"https://example.com/{i}.js", "script", float(i), status=404))

        lines = logger.get_failed_summary().splitlines()

        assert lines[1] == "  (5 earlier not shown)"
        assert len(lines) == 2 + 20
        assert lines[2].endswith("/5.js [404]")
        assert lines[-1].endswith("/24.js [404]")

    def test_get_failed_summary_masks_a_credential_before_cutting_the_url(self):
        key = "AIza" + "S" * 35  # a bare key is recognised only whole: a fragment of it passes the mask
        prefix = "https://cdn.example.com/a.js?p=" + "x" * 100 + "&k="
        kept_by_a_cut_first = URL_PREVIEW_CHARS - 1 - len(prefix)
        assert 0 < kept_by_a_cut_first < len("AIza") + 30  # the cut would end inside the key, too early to recognise it
        logger = NetworkLogger()
        logger._requests.append(RequestInfo("GET", prefix + key + "&z=1", "script", 0.0, status=404))

        summary = logger.get_failed_summary()

        assert "S" * 8 not in summary
        assert "&k=AIza" in summary

    def test_get_summary_empty(self):
        """Test get_summary with no requests."""
        logger = NetworkLogger()
        summary = logger.get_summary()
        assert summary == "No API requests captured."

    def test_get_summary_with_requests(self):
        """Test get_summary formatting."""
        logger = NetworkLogger()

        logger._requests.append(
            RequestInfo(
                method="GET",
                url="https://api.example.com/data",
                resource_type="xhr",
                timestamp=0.0,
                status=200,
                status_text="OK",
                duration_ms=123.5,
            )
        )
        logger._requests.append(
            RequestInfo(
                method="POST",
                url="https://api.example.com/error",
                resource_type="fetch",
                timestamp=1.0,
                status=404,
                status_text="Not Found",
                duration_ms=89.2,
            )
        )

        summary = logger.get_summary()

        assert "Network Log" in summary
        assert "GET https://api.example.com/data" in summary
        assert "[OK]" in summary
        assert "200 OK" in summary
        assert "124ms" in summary

        assert "POST https://api.example.com/error" in summary
        assert "[FAIL]" in summary
        assert "404 Not Found" in summary
        assert "89ms" in summary

    def test_get_summary_limits_output(self):
        """Test get_summary limits to last 20 requests."""
        logger = NetworkLogger(max_requests=50)

        for i in range(30):
            logger._requests.append(
                RequestInfo(
                    method="GET",
                    url=f"https://api.example.com/{i}",
                    resource_type="xhr",
                    timestamp=float(i),
                )
            )

        summary = logger.get_summary()

        assert "30 total" in summary
        assert "showing last 20" in summary

        assert "https://api.example.com/29" in summary
        assert "https://api.example.com/10" in summary
        assert "https://api.example.com/0" not in summary
        assert "https://api.example.com/9" not in summary

    def test_clear(self):
        """Test clear method."""
        logger = NetworkLogger()

        logger._requests.append(
            RequestInfo(
                method="GET",
                url="https://example.com",
                resource_type="xhr",
                timestamp=0.0,
            )
        )

        mock_request = Mock()
        logger._pending[mock_request] = 0.0

        assert len(logger._requests) == 1
        assert len(logger._pending) == 1

        logger.clear()

        assert len(logger._requests) == 0
        assert len(logger._pending) == 0

    def test_get_pending_count(self):
        """Test get_pending_count method."""
        logger = NetworkLogger()

        mock_req1 = Mock()
        mock_req2 = Mock()
        logger._pending[mock_req1] = 0.0
        logger._pending[mock_req2] = 1.0

        assert logger.get_pending_count() == 2

    def test_on_request_captures_xhr(self):
        """Test _on_request captures XHR requests."""
        logger = NetworkLogger()

        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.url = "https://api.example.com/data"
        mock_request.resource_type = "xhr"

        logger._on_request(mock_request)

        assert mock_request in logger._pending

    def test_on_request_filters_static_resources(self):
        """Test _on_request filters static resources."""
        logger = NetworkLogger()

        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.url = "https://example.com/image.png"
        mock_request.resource_type = "image"

        logger._on_request(mock_request)

        assert mock_request not in logger._pending

    def test_on_request_failed_captures_failure(self):
        """Test _on_request_failed captures failed requests."""
        logger = NetworkLogger()

        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.url = "https://example.com/fail"
        mock_request.resource_type = "xhr"

        logger._pending[mock_request] = 0.0

        logger._on_request_failed(mock_request)

        assert len(logger._requests) == 1
        req = logger._requests[0]
        assert req.url == "https://example.com/fail"
        assert req.status is None
        assert req.status_text == "Request Failed"

    def test_concurrent_same_url_requests(self):
        """Test handling concurrent requests to the same URL."""
        logger = NetworkLogger()

        mock_req1 = Mock()
        mock_req1.method = "GET"
        mock_req1.url = "https://api.example.com/data"
        mock_req1.resource_type = "xhr"

        mock_req2 = Mock()
        mock_req2.method = "GET"
        mock_req2.url = "https://api.example.com/data"
        mock_req2.resource_type = "xhr"

        mock_req3 = Mock()
        mock_req3.method = "GET"
        mock_req3.url = "https://api.example.com/data"
        mock_req3.resource_type = "xhr"

        logger._on_request(mock_req1)
        logger._on_request(mock_req2)
        logger._on_request(mock_req3)

        assert logger.get_pending_count() == 3

        mock_resp1 = Mock()
        mock_resp1.request = mock_req1
        mock_resp1.status = 200
        mock_resp1.status_text = "OK"

        mock_resp2 = Mock()
        mock_resp2.request = mock_req2
        mock_resp2.status = 200
        mock_resp2.status_text = "OK"

        logger._on_response(mock_resp1)
        logger._on_response(mock_resp2)

        assert len(logger._requests) == 2
        assert logger.get_pending_count() == 1


class TestNetworkLoggerIntegration:
    """NetworkLogger against a page with the real Page API (attribute names are checked, not just calls)."""

    def test_start_capture_registers_handlers(self):
        """Test start_capture registers event handlers."""
        logger = NetworkLogger()
        mock_page = Mock(spec=Page)

        logger.start_capture(mock_page)

        assert mock_page.on.call_count == 3
        event_names = [call[0][0] for call in mock_page.on.call_args_list]
        assert "request" in event_names
        assert "response" in event_names
        assert "requestfailed" in event_names

    def test_start_capture_idempotent_same_page(self) -> None:
        """Second start_capture on same page must not stack listeners."""
        logger = NetworkLogger()
        mock_page = Mock(spec=Page)
        logger.start_capture(mock_page)
        logger.start_capture(mock_page)
        assert mock_page.on.call_count == 3
        assert mock_page.remove_listener.call_count == 0

    def test_start_capture_switches_page_detaches_previous(self) -> None:
        """Binding a new page removes listeners from the previous page."""
        logger = NetworkLogger()
        page_a = Mock(spec=Page)
        page_b = Mock(spec=Page)
        logger.start_capture(page_a)
        logger.start_capture(page_b)
        assert page_a.remove_listener.call_count == 3
        assert page_b.on.call_count == 3
        assert logger.bound_page is page_b

    def test_stop_capture_detaches_when_bound(self) -> None:
        """stop_capture removes listeners from the bound page."""
        logger = NetworkLogger()
        mock_page = Mock(spec=Page)
        logger.start_capture(mock_page)
        logger.stop_capture()
        assert mock_page.remove_listener.call_count == 3
        assert logger.bound_page is None

    def test_detach_page_ignores_non_bound(self) -> None:
        """detach_page no-op when page is not the bound instance."""
        logger = NetworkLogger()
        page_a = Mock(spec=Page)
        page_b = Mock(spec=Page)
        logger.start_capture(page_a)
        logger.detach_page(page_b)
        assert page_a.remove_listener.call_count == 0
        assert logger.bound_page is page_a

    def test_stop_capture_clears_pending(self):
        """Test stop_capture clears pending state."""
        logger = NetworkLogger()

        mock_req = Mock(spec=Page)
        logger._pending[mock_req] = 0.0

        assert len(logger._pending) == 1

        logger.stop_capture()

        assert len(logger._pending) == 0

    def test_full_request_response_cycle(self):
        """Test full request/response capture cycle."""
        logger = NetworkLogger()

        mock_request = Mock(spec=Page)
        mock_request.method = "GET"
        mock_request.url = "https://api.example.com/data"
        mock_request.resource_type = "xhr"

        logger._on_request(mock_request)
        assert mock_request in logger._pending

        mock_response = Mock(spec=Page)
        mock_response.request = mock_request
        mock_response.status = 200
        mock_response.status_text = "OK"

        logger._on_response(mock_response)

        assert len(logger._requests) == 1
        req = logger._requests[0]
        assert req.method == "GET"
        assert req.url == "https://api.example.com/data"
        assert req.status == 200
        assert req.status_text == "OK"

    def test_request_failed_handling(self):
        """Test request failure handling."""
        logger = NetworkLogger()

        mock_request = Mock(spec=Page)
        mock_request.method = "POST"
        mock_request.url = "https://api.example.com/submit"
        mock_request.resource_type = "fetch"

        logger._on_request(mock_request)

        logger._on_request_failed(mock_request)

        assert len(logger._requests) == 1
        req = logger._requests[0]
        assert req.url == "https://api.example.com/submit"
        assert req.status is None
        assert req.status_text == "Request Failed"


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
        """The leak: a JSON value split by the preview cut previously
        surfaced as a plaintext fragment (JSON structure broken by the cut)."""
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


class TestNetworkLoggerEdgeCases:
    """Test edge cases and error handling."""

    def test_on_request_exception_handling(self):
        """Test _on_request handles exceptions gracefully."""
        logger = NetworkLogger()

        mock_request = Mock()
        type(mock_request).resource_type = property(lambda self: (_ for _ in ()).throw(Exception("Test error")))

        logger._on_request(mock_request)

        assert len(logger._pending) == 0

    def test_on_response_exception_handling(self):
        """Test _on_response handles exceptions gracefully."""
        logger = NetworkLogger()

        mock_response = Mock()
        mock_response.request = Mock(side_effect=Exception("Test error"))

        logger._on_response(mock_response)

        assert len(logger._requests) == 0

    def test_on_response_request_not_in_pending(self):
        """Test _on_response when request is not in pending."""
        logger = NetworkLogger()

        mock_request = Mock()
        mock_response = Mock()
        mock_response.request = mock_request

        logger._on_response(mock_response)

        assert len(logger._requests) == 0

    def test_on_request_failed_exception_handling(self):
        """Test _on_request_failed handles exceptions gracefully."""
        logger = NetworkLogger()

        mock_request = Mock()
        mock_request.method = Mock(side_effect=Exception("Test error"))

        logger._on_request_failed(mock_request)

        assert len(logger._requests) == 0

    def test_on_request_failed_request_not_in_pending(self):
        """Test _on_request_failed when request is not in pending."""
        logger = NetworkLogger()

        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.url = "https://example.com"
        mock_request.resource_type = "xhr"

        logger._on_request_failed(mock_request)

        assert len(logger._requests) == 0

    def test_format_request_with_status_text_only(self):
        """Test _format_request when status is None but status_text exists."""
        logger = NetworkLogger()

        req = RequestInfo(
            method="GET",
            url="https://example.com",
            resource_type="xhr",
            timestamp=time.time(),
            status=None,
            status_text="Network Error",
            duration_ms=50.0,
        )

        parts = logger._format_request(req, 1)

        assert "[FAIL] Network Error" in " ".join(parts)
