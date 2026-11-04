"""Fixtures that replay one provider answer through the whole call path, adapter included, without a network."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.transport import http
from myrm_agent_harness.toolkits.llms.transport.answer_cache import answer_cache
from myrm_agent_harness.utils.token_economics.tracker import TokenTracker, init_token_tracker, reset_token_tracker

from .provider_double import Provider


@pytest.fixture
def tracker() -> Iterator[TokenTracker]:
    """The request's token accounting, which is what a call's usage and finish reason end up in."""
    yield init_token_tracker()
    reset_token_tracker()


@pytest.fixture
def serve_answer(monkeypatch: pytest.MonkeyPatch) -> Callable[[bytes, str], None]:
    """``serve_answer(body, content_type)``: every provider request is answered with that body."""

    def arm(body: bytes, content_type: str) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": content_type}, content=body)

        monkeypatch.setattr(
            http, "_async_client", lambda proxy: httpx.AsyncClient(transport=httpx.MockTransport(respond))
        )
        monkeypatch.setattr(http, "_sync_client", lambda proxy: httpx.Client(transport=httpx.MockTransport(respond)))

    return arm


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> Provider:
    """A provider double that counts the requests reaching it, behind the sync and the async HTTP client."""
    fake = Provider()

    def respond(request: httpx.Request) -> httpx.Response:
        fake.requests.append(request)
        return fake.handler(request)

    monkeypatch.setattr(http, "_sync_client", lambda proxy: httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(http, "_async_client", lambda proxy: httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    return fake


@pytest.fixture
def cache_on() -> Iterator[None]:
    """The answer cache switched on and empty; the suites run with it off."""
    was_enabled = answer_cache.enabled
    answer_cache.enabled = True
    answer_cache.clear()
    yield
    answer_cache.clear()
    answer_cache.enabled = was_enabled
