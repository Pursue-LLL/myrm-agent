"""NetworkLogger page lifecycle: listeners follow the bound page, and a request is recorded from start to end."""

from unittest.mock import Mock, PropertyMock

from patchright.async_api import Frame, Page, Request, Response

from myrm_agent_harness.toolkits.browser.session.network.logger import NetworkLogger, RequestInfo


def _frame(parent: Frame | None) -> Mock:
    frame = Mock(spec=Frame)
    frame.parent_frame = parent
    return frame


def _request(url: str, resource_type: str, navigation_of_frame: Mock | None = None) -> Mock:
    """A driver request; a navigation request names the frame it loads a document into."""
    request = Mock(spec=Request)
    request.method = "GET"
    request.url = url
    request.resource_type = resource_type
    request.is_navigation_request.return_value = navigation_of_frame is not None
    if navigation_of_frame is not None:
        request.frame = navigation_of_frame
    return request


class TestNetworkLoggerCapture:
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

        mock_req = Mock(spec=Request)
        logger._pending[mock_req] = 0.0

        assert len(logger._pending) == 1

        logger.stop_capture()

        assert len(logger._pending) == 0

    def test_a_main_frame_navigation_starts_the_log_over(self) -> None:
        """What was recorded belongs to the page that is going away; the navigation request itself is the new page's."""
        logger = NetworkLogger()
        logger._requests.append(RequestInfo("GET", "https://app.example.com/main.js", "script", 0.0, status=404))
        stale = _request("https://app.example.com/old", "xhr")
        logger._on_request(stale)

        document = _request("https://app.example.com/next", "document", navigation_of_frame=_frame(parent=None))
        logger._on_request(document)

        assert len(logger._requests) == 0
        assert stale not in logger._pending
        assert document in logger._pending

    def test_a_sub_frame_navigation_keeps_the_log(self) -> None:
        logger = NetworkLogger()
        logger._requests.append(RequestInfo("GET", "https://app.example.com/main.js", "script", 0.0, status=404))

        logger._on_request(
            _request("https://ads.example.com/", "document", navigation_of_frame=_frame(parent=_frame(parent=None)))
        )

        assert len(logger._requests) == 1

    def test_a_navigation_whose_frame_the_driver_does_not_know_yet_is_captured_and_keeps_the_log(self) -> None:
        logger = NetworkLogger()
        logger._requests.append(RequestInfo("GET", "https://app.example.com/main.js", "script", 0.0, status=404))
        request = _request("https://ads.example.com/", "document", navigation_of_frame=_frame(parent=None))
        type(request).frame = PropertyMock(side_effect=Exception("Frame for this navigation request is not available"))

        logger._on_request(request)

        assert len(logger._requests) == 1
        assert request in logger._pending

    def test_binding_another_page_starts_the_log_over(self) -> None:
        logger = NetworkLogger()
        logger.start_capture(Mock(spec=Page))
        logger._requests.append(RequestInfo("GET", "https://app.example.com/main.js", "script", 0.0, status=404))

        logger.start_capture(Mock(spec=Page))

        assert len(logger._requests) == 0

    def test_full_request_response_cycle(self):
        """Test full request/response capture cycle."""
        logger = NetworkLogger()

        mock_request = Mock(spec=Request)
        mock_request.method = "GET"
        mock_request.url = "https://api.example.com/data"
        mock_request.resource_type = "xhr"
        mock_request.is_navigation_request.return_value = False

        logger._on_request(mock_request)
        assert mock_request in logger._pending

        mock_response = Mock(spec=Response)
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

        mock_request = Mock(spec=Request)
        mock_request.method = "POST"
        mock_request.url = "https://api.example.com/submit"
        mock_request.resource_type = "fetch"
        mock_request.is_navigation_request.return_value = False

        logger._on_request(mock_request)

        logger._on_request_failed(mock_request)

        assert len(logger._requests) == 1
        req = logger._requests[0]
        assert req.url == "https://api.example.com/submit"
        assert req.status is None
        assert req.status_text == "Request Failed"
