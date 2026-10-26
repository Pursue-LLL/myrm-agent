"""Unit tests for NetworkLogger — network request capture and filtering."""

import time
from unittest.mock import Mock

from myrm_agent_harness.toolkits.browser.session.network.logger import (
    URL_PREVIEW_CHARS,
    NetworkLogger,
    RequestInfo,
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

    def test_get_other_failed_summary_lists_failed_non_api_requests_one_line_each_without_numbers(self):
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

        assert logger.get_other_failed_summary().splitlines() == [
            "Other failed requests (not numbered, so network_detail cannot open them):",
            "  script GET https://example.com/app.js [404]",
            "  document GET https://example.com/ [503]",
        ]

    def test_get_other_failed_summary_is_empty_when_no_non_api_request_failed(self):
        logger = NetworkLogger()
        logger._requests.extend(
            [
                RequestInfo("GET", "https://api.example.com/gone", "xhr", 0.0, status=404),
                RequestInfo("GET", "https://example.com/ok.js", "script", 1.0, status=200),
            ]
        )

        assert logger.get_other_failed_summary() == ""

    def test_get_other_failed_summary_keeps_the_latest_and_counts_the_rest(self):
        logger = NetworkLogger(max_requests=50)
        for i in range(25):
            logger._requests.append(RequestInfo("GET", f"https://example.com/{i}.js", "script", float(i), status=404))

        lines = logger.get_other_failed_summary().splitlines()

        assert lines[1] == "  (5 earlier not shown)"
        assert len(lines) == 2 + 20
        assert lines[2].endswith("/5.js [404]")
        assert lines[-1].endswith("/24.js [404]")

    def test_get_other_failed_summary_masks_a_credential_before_cutting_the_url(self):
        key = "AIza" + "S" * 35  # a bare key is recognised only whole: a fragment of it passes the mask
        prefix = "https://cdn.example.com/a.js?p=" + "x" * 100 + "&k="
        kept_by_a_cut_first = URL_PREVIEW_CHARS - 1 - len(prefix)
        assert 0 < kept_by_a_cut_first < len("AIza") + 30  # the cut would end inside the key, too early to recognise it
        logger = NetworkLogger()
        logger._requests.append(RequestInfo("GET", prefix + key + "&z=1", "script", 0.0, status=404))

        summary = logger.get_other_failed_summary()

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
