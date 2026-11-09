"""Fetch results shared by the HttpFetcher HTTP/3 and request-layer tests."""

from __future__ import annotations

from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetcherType, FetchResult


def blocked_result(*, status: int = 403) -> FetchResult:
    return FetchResult(
        html="<html><body>Access Denied</body></html>",
        url="https://blocked.example/article",
        status_code=status,
        fetcher_type=FetcherType.HTTP,
    )


def success_result() -> FetchResult:
    body = (
        "<html><body><article>"
        "<p>Real article content here with enough text to pass has_content checks. "
        "Additional paragraph padding to exceed the two-hundred character minimum "
        "required by FetchResult.has_content for L1 success detection.</p>"
        "</article></body></html>"
    )
    return FetchResult(
        html=body,
        url="https://blocked.example/article",
        status_code=200,
        fetcher_type=FetcherType.HTTP,
    )
