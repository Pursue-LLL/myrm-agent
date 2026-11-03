"""Fixtures that replay one provider answer through the whole call path, adapter included, without a network."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.transport import http
from myrm_agent_harness.utils.token_economics.tracker import TokenTracker, init_token_tracker, reset_token_tracker


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
