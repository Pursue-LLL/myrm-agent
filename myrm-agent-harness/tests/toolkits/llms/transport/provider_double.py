"""A provider double that remembers every request it was asked, for tests that count how often a provider is reached."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from .gateway_bodies import Body, sse_body

BASE = "http://gateway.test/v1"

Handler = Callable[[httpx.Request], httpx.Response]


class Provider:
    """Answers each request with the response it was told to serve and keeps the requests it saw."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.handler: Handler = lambda request: httpx.Response(500)

    def serves(self, response: httpx.Response) -> None:
        self.handler = lambda request: response


def json_response(body: Body) -> httpx.Response:
    return httpx.Response(200, json=body)


def sse_response(*frames: Body | str) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse_body(*frames))


def drain(stream: object) -> list[object]:
    """Every chunk a synchronous stream hands out."""
    return list(stream)  # type: ignore[call-overload]


async def adrain(stream: object) -> list[object]:
    """Every chunk an asynchronous stream hands out."""
    return [part async for part in stream]  # type: ignore[attr-defined]
